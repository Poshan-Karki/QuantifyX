"""Performance metrics for stitched out-of-sample curves (design sections 5 and 6).

Everything takes a per-bar return series. Nothing here should ever be handed
training-fold returns.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import kurtosis as _kurtosis
from scipy.stats import norm
from scipy.stats import skew as _skew

TRADING_DAYS = 252
_EULER_MASCHERONI = 0.5772156649015329


def per_period_sharpe(returns: pd.Series | np.ndarray) -> float:
    """Mean over standard deviation, not annualised.

    The deflated Sharpe ratio is defined on this, not the annualised figure --
    mixing the two is the most common way to get that calculation wrong.
    """
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 2:
        return float("nan")
    sd = r.std(ddof=1)
    if sd == 0:
        return float("nan")
    return float(r.mean() / sd)


def annualised_sharpe(returns: pd.Series | np.ndarray, periods: int = TRADING_DAYS) -> float:
    sharpe = per_period_sharpe(returns)
    return float(sharpe * np.sqrt(periods)) if np.isfinite(sharpe) else float("nan")


def total_return(returns: pd.Series | np.ndarray) -> float:
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    return float(np.prod(1.0 + r) - 1.0) if len(r) else float("nan")


def equity_curve(returns: pd.Series) -> pd.Series:
    """Compound a return series into a curve starting at 1.0."""
    return (1.0 + returns.fillna(0.0)).cumprod()


def max_drawdown(returns: pd.Series) -> float:
    """Largest peak-to-trough fall, as a negative fraction."""
    if len(returns) == 0:
        return float("nan")
    curve = equity_curve(returns)
    return float((curve / curve.cummax() - 1.0).min())


def cagr(returns: pd.Series, periods: int = TRADING_DAYS) -> float:
    r = returns.dropna()
    if len(r) < 2:
        return float("nan")
    growth = float(np.prod(1.0 + r.to_numpy()))
    if growth <= 0:
        return float("nan")
    return float(growth ** (periods / len(r)) - 1.0)


def calmar(returns: pd.Series, periods: int = TRADING_DAYS) -> float:
    drawdown = max_drawdown(returns)
    if not np.isfinite(drawdown) or drawdown == 0:
        return float("nan")
    return float(cagr(returns, periods) / abs(drawdown))


def hit_rate(returns: pd.Series | np.ndarray) -> float:
    """Share of non-flat bars that were positive."""
    r = np.asarray(returns, dtype=float)
    active = r[np.isfinite(r) & (r != 0.0)]
    if len(active) == 0:
        return float("nan")
    return float(np.mean(active > 0))


def summarise(
    returns: pd.Series,
    n_trades: int = 0,
    periods: int = TRADING_DAYS,
) -> dict:
    """The metric block recorded for every (symbol, arm) row."""
    returns = pd.Series(returns).dropna()
    n_bars = len(returns)
    return {
        "n_bars": n_bars,
        "sharpe_annualised": annualised_sharpe(returns, periods),
        "sharpe_per_period": per_period_sharpe(returns),
        "total_return": total_return(returns),
        "cagr": cagr(returns, periods),
        "max_drawdown": max_drawdown(returns),
        "calmar": calmar(returns, periods),
        "hit_rate": hit_rate(returns),
        "time_in_market": float(np.mean(returns.to_numpy() != 0.0)) if n_bars else float("nan"),
        "n_trades": int(n_trades),
        "trades_per_year": float(n_trades * periods / n_bars) if n_bars else float("nan"),
    }


def masked_sharpe(returns: pd.Series, mask: pd.Series | np.ndarray) -> float:
    """Per-period Sharpe over the subset of bars the mask selects.

    This is how strategy selection scores a candidate: run it across the whole
    training fold, then score it only on bars carrying the regime label in
    question. Restricting the backtest itself to non-contiguous bars is not
    possible, and would misprice entries and exits even if it were.
    """
    mask = np.asarray(mask, dtype=bool)
    values = np.asarray(returns, dtype=float)
    if len(mask) != len(values):
        raise ValueError(f"mask length {len(mask)} does not match returns length {len(values)}")
    selected = values[mask]
    if len(selected) < 2:
        return float("nan")
    return per_period_sharpe(selected)


# --------------------------------------------------------------------------
# Multiple-testing correction (design section 6)
# --------------------------------------------------------------------------


def expected_max_sharpe(n_trials: int, sharpe_variance: float) -> float:
    """Expected maximum per-period Sharpe across n_trials under the null of no skill.

    The order-statistic approximation from the Deflated Sharpe Ratio paper.
    """
    if n_trials < 2 or not np.isfinite(sharpe_variance) or sharpe_variance <= 0:
        return 0.0
    z1 = norm.ppf(1.0 - 1.0 / n_trials)
    z2 = norm.ppf(1.0 - 1.0 / (n_trials * np.e))
    return float(np.sqrt(sharpe_variance) * ((1.0 - _EULER_MASCHERONI) * z1 + _EULER_MASCHERONI * z2))


def deflated_sharpe_ratio(
    returns: pd.Series | np.ndarray,
    n_trials: int,
    sharpe_variance: float,
) -> float:
    """Probability the observed Sharpe reflects skill rather than selection.

    You pick the best of eight strategies every fold, so the reported Sharpe is a
    maximum over trials and is biased upward by construction. This deflates it.

    `sharpe_variance` is the variance of the per-period Sharpes across the trials
    actually run -- collect them with trial_sharpe_variance().

    Verify this formula against Bailey & Lopez de Prado before publishing any
    number it produces. It is transcribed from memory, and the skew/kurtosis
    convention in particular is easy to get wrong: the fourth standardised
    moment is wanted here, not excess kurtosis, which is why fisher=False is set
    below.
    """
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    n_obs = len(r)
    if n_obs < 3:
        return float("nan")

    sharpe = per_period_sharpe(r)
    if not np.isfinite(sharpe):
        return float("nan")

    skewness = float(_skew(r, bias=False))
    kurt = float(_kurtosis(r, fisher=False, bias=False))

    threshold = expected_max_sharpe(n_trials, sharpe_variance)
    variance_term = 1.0 - skewness * sharpe + ((kurt - 1.0) / 4.0) * sharpe**2
    if not np.isfinite(variance_term) or variance_term <= 0:
        return float("nan")

    statistic = (sharpe - threshold) * np.sqrt(n_obs - 1) / np.sqrt(variance_term)
    return float(norm.cdf(statistic))


def trial_sharpe_variance(trial_returns: list[pd.Series | np.ndarray]) -> float:
    """Variance of per-period Sharpe across the candidate strategies tried."""
    sharpes = [per_period_sharpe(r) for r in trial_returns]
    sharpes = [s for s in sharpes if np.isfinite(s)]
    if len(sharpes) < 2:
        return float("nan")
    return float(np.var(sharpes, ddof=1))


def stationary_bootstrap_pvalue(
    difference: pd.Series | np.ndarray,
    n_resamples: int = 2000,
    mean_block: float = 20.0,
    seed: int = 0,
) -> float:
    """Two-sided p-value that a paired per-bar return difference has zero mean.

    Politis-Romano stationary bootstrap, with geometric block lengths, because
    daily strategy returns are autocorrelated and a plain t-test would assume
    independence the data does not have.
    """
    d = np.asarray(difference, dtype=float)
    d = d[np.isfinite(d)]
    n = len(d)
    if n < 10:
        return float("nan")

    observed = d.mean()
    centred = d - observed
    rng = np.random.default_rng(seed)
    p_restart = 1.0 / max(mean_block, 1.0)

    means = np.empty(n_resamples)
    for i in range(n_resamples):
        idx = np.empty(n, dtype=int)
        idx[0] = rng.integers(n)
        restart = rng.random(n) < p_restart
        for t in range(1, n):
            idx[t] = rng.integers(n) if restart[t] else (idx[t - 1] + 1) % n
        means[i] = centred[idx].mean()

    return float(np.mean(np.abs(means) >= abs(observed)))
