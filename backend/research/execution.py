"""Running strategies over bar ranges, with a per-fold cache.

configure() makes a throwaway subclass per parameter set rather than writing
onto the strategy class, which is global and permanent -- a cost sweep built on
class mutation would silently compare a strategy against itself.

Costs come from `costs.commission_fraction`, the same function the API uses, so
the study and the application cannot drift into measuring different execution
models.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from backtesting import Backtest

from Backtest import (
    ATRBreakout,
    BollingerRsi,
    MACDCross,
    MeanReversion,
    RSIMeanReversion,
    VolumeBreakout,
    bollinger_band,
    macrossover,
)
from costs import (
    DEFAULT_COOLDOWN_BARS,
    DEFAULT_FEE_PCT,
    DEFAULT_MAX_POS_PCT,
    DEFAULT_SLIPPAGE_PCT,
    commission_fraction,
)

#: The strategy pool, matching main.run_backtest so the study evaluates exactly
#: what the application offers.
STRATEGIES = {
    "Bollinger Band": bollinger_band,
    "Moving Average Crossover": macrossover,
    "Mean Reversion": MeanReversion,
    "Bollinger+Rsi": BollingerRsi,
    "VolumeBreakout": VolumeBreakout,
    "MACD Cross": MACDCross,
    "RSI Mean Reversion": RSIMeanReversion,
    "ATR Breakout": ATRBreakout,
}

STRATEGY_NAMES = tuple(STRATEGIES)

#: Longest indicator lookback in the pool (ATRBreakout's 50-bar EMA), which sets
#: the warm-up the embargo has to cover.
MAX_LOOKBACK_BARS = 50


@dataclass
class TradeParams:
    cash: float = 100_000.0
    fee_pct: float = DEFAULT_FEE_PCT
    slippage_pct: float = DEFAULT_SLIPPAGE_PCT
    max_pos_pct: float = DEFAULT_MAX_POS_PCT
    cooldown_bars: int = DEFAULT_COOLDOWN_BARS

    def key(self) -> tuple:
        return (self.cash, self.fee_pct, self.slippage_pct, self.max_pos_pct, self.cooldown_bars)


@dataclass
class StrategyRun:
    """Outcome of one backtest over one bar range."""

    name: str
    returns: pd.Series  # per-bar equity returns, indexed like the executed range
    equity: pd.Series
    n_trades: int
    trades: pd.DataFrame | None = None
    ok: bool = True
    error: str | None = None

    @property
    def exposure(self) -> float:
        """Fraction of bars where equity moved -- a cheap proxy for time in market."""
        if len(self.returns) == 0:
            return float("nan")
        return float(np.mean(self.returns.to_numpy() != 0.0))

    def trades_from(self, start) -> int:
        """Trades entered at or after `start`.

        A run over an execution slice includes warm-up bars, and a position
        opened during warm-up carries into the test window -- realistic, but its
        entry does not belong to the test window's trade count.
        """
        if self.trades is None or len(self.trades) == 0:
            return 0
        if "EntryTime" not in self.trades.columns:
            return int(self.n_trades)
        return int((self.trades["EntryTime"] >= start).sum())


def configure(base, params: TradeParams):
    """Fresh subclass carrying these sizing parameters, leaving the base untouched.

    Fees and slippage are not set here: they are charged together as the
    Backtest commission, matching the API.
    """
    return type(
        base.__name__,
        (base,),
        {
            "max_pos_pct": params.max_pos_pct,
            "cooldown_bars": params.cooldown_bars,
        },
    )


def run_strategy(df: pd.DataFrame, name: str, params: TradeParams) -> StrategyRun:
    """Backtest one strategy over the bars given.

    A failure here is recorded rather than raised: a strategy that cannot trade a
    particular window (too few bars for its indicators, no signals at all) is a
    legitimate outcome that should show up as a flat curve in the results, not
    abort a twelve-hour sweep.
    """
    if name not in STRATEGIES:
        raise KeyError(f"unknown strategy {name!r}; known: {sorted(STRATEGIES)}")

    empty = pd.Series(0.0, index=df.index, dtype=float)
    try:
        backtest = Backtest(
            df,
            configure(STRATEGIES[name], params),
            cash=params.cash,
            commission=commission_fraction(params.fee_pct, params.slippage_pct),
            finalize_trades=True,
        )
        stats = backtest.run()
    except Exception as exc:  # noqa: BLE001 - recorded, see docstring
        return StrategyRun(name, empty, empty, 0, ok=False, error=f"{type(exc).__name__}: {exc}")

    equity = stats["_equity_curve"]["Equity"].astype(float)
    returns = equity.pct_change().fillna(0.0)
    n_trades = int(stats.get("# Trades", 0) or 0)
    trades = stats["_trades"] if "_trades" in stats else None
    return StrategyRun(name, returns, equity, n_trades, trades=trades)


@dataclass
class RunCache:
    """Memoises backtests within one symbol.

    Arms A2, B1, B2 and B3 all evaluate the same eight strategies over the same
    training folds -- only the regime mask applied afterwards differs. Without
    this, four arms times eight strategies times every fold is four times the
    backtests actually needed.
    """

    params: TradeParams
    _store: dict[tuple, StrategyRun] = field(default_factory=dict, repr=False)

    def get(self, df: pd.DataFrame, name: str, tag: tuple) -> StrategyRun:
        key = (name, tag, self.params.key())
        if key not in self._store:
            self._store[key] = run_strategy(df, name, self.params)
        return self._store[key]

    def clear(self) -> None:
        self._store.clear()


def buy_and_hold_returns(df: pd.DataFrame) -> pd.Series:
    """Per-bar returns of holding the underlying, for arm A0."""
    return df["Close"].astype(float).pct_change().fillna(0.0)
