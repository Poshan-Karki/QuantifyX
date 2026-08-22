"""The six experimental arms (design section 4.1).

    A0        buy and hold
    A1:<name> one fixed strategy, no regime conditioning
    A2        rule-based regime labels (market_regime's thresholds)
    B1        HMM fitted on the entire series, smoothed Viterbi decode
    B2        HMM fitted on the entire series, filtered decode
    B3        HMM fitted on the training fold only, filtered decode

B1 reproduces what the /hmm endpoint does today. B3 is the only arm that could
have been traded. The differences between them are the study:

    B1 - B2   the smoothing leak   (future observations inform past labels)
    B2 - B3   the fitting leak     (future observations inform the parameters)

Everything except the regime signal is held fixed across arms -- same strategy
pool, same selection rule, same costs, same folds -- so a difference between two
arms can only come from the labelling.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import (
    ARM_BUY_HOLD,
    ARM_HMM_FIT_LEAKED,
    ARM_HMM_HONEST,
    ARM_HMM_LEAKED,
    ARM_RULE,
    StudyConfig,
    derive_seed,
)
from .execution import STRATEGY_NAMES, RunCache, buy_and_hold_returns
from .features import RETURN_FEATURE, FeaturePipeline, build_features, usable_range
from .hmm_regime import (
    HmmFit,
    canonical_order,
    canonical_params,
    decode_filtered,
    decode_smoothed,
    label_churn,
    order_to_relabel,
    relabel_states,
    select_n_components,
)
from .metrics import masked_sharpe
from .rule_regime import rule_regime_series
from .walkforward import Fold, assert_folds_sound, generate_folds

#: Below this many bars carrying the current label, in-fold Sharpe is too noisy
#: to select on and the selector falls back to the whole training window. The
#: fallback is recorded per fold so its frequency can be reported.
MIN_REGIME_BARS = 30


@dataclass
class SymbolContext:
    """Everything derived once per symbol and shared across every arm."""

    symbol: str
    df: pd.DataFrame
    features: pd.DataFrame
    x_raw: np.ndarray
    valid_from: int
    folds: list[Fold]
    cache: RunCache
    cfg: StudyConfig
    bh_returns: pd.Series
    return_feature_index: int

    @property
    def n_bars(self) -> int:
        return len(self.df)


def build_context(symbol: str, df: pd.DataFrame, cfg: StudyConfig) -> SymbolContext:
    features = build_features(df, tuple(cfg.features), vol_window=cfg.vol_window)
    if RETURN_FEATURE not in cfg.features:
        raise ValueError(
            f"feature set must include {RETURN_FEATURE!r}: canonical state ordering is "
            "defined by mean return, and without it states cannot be aligned across refits"
        )
    folds = generate_folds(
        n_bars=len(df),
        scheme=cfg.scheme,
        train_bars=cfg.train_bars,
        test_bars=cfg.test_bars,
        embargo_bars=cfg.embargo_bars,
        step=cfg.step,
    )
    assert_folds_sound(folds)
    return SymbolContext(
        symbol=symbol,
        df=df,
        features=features,
        x_raw=features.to_numpy(dtype=float),
        valid_from=usable_range(features),
        folds=folds,
        cache=RunCache(cfg.trade_params),
        cfg=cfg,
        bh_returns=buy_and_hold_returns(df),
        return_feature_index=list(cfg.features).index(RETURN_FEATURE),
    )


# --------------------------------------------------------------------------
# Regime labelling
# --------------------------------------------------------------------------


def _empty_labels(n: int) -> np.ndarray:
    return np.full(n, None, dtype=object)


def rule_labels(ctx: SymbolContext) -> np.ndarray:
    """Arm A2. No fitting happens, so one pass over the series is leak-free."""
    series = rule_regime_series(ctx.df)
    labels = _empty_labels(ctx.n_bars)
    values = series.to_numpy(dtype=object)
    known = series.notna().to_numpy()
    labels[known] = values[known]
    return labels


@dataclass
class FullFitLabels:
    """Arms B1 and B2 -- one model fitted across the entire series.

    Deliberately leaked. Both decodes come from the same fit, which also yields
    the filtered-vs-smoothed disagreement rate straight away.
    """

    smoothed: np.ndarray
    filtered: np.ndarray
    fit: HmmFit
    disagreement: float


def full_fit_labels(ctx: SymbolContext) -> FullFitLabels:
    cfg = ctx.cfg
    span = slice(ctx.valid_from, ctx.n_bars)
    rows = ctx.x_raw[span]
    bar_index = np.arange(ctx.valid_from, ctx.n_bars)

    # Fitted on everything, including the test periods. That is the point.
    pipeline = FeaturePipeline(cfg.winsor_lower, cfg.winsor_upper)
    x = pipeline.fit_transform(rows)

    fit = select_n_components(
        x,
        tuple(cfg.n_components),
        seed=derive_seed(cfg.seed, ctx.symbol, "full_fit"),
        bar_indices=bar_index,
        **cfg.hmm_kwargs,
    )
    relabel = order_to_relabel(canonical_order(fit.model, ctx.return_feature_index))

    smoothed_states = relabel_states(decode_smoothed(fit.model, x), relabel)
    filtered_states = relabel_states(decode_filtered(fit.model, x), relabel)

    smoothed = _empty_labels(ctx.n_bars)
    filtered = _empty_labels(ctx.n_bars)
    smoothed[span] = smoothed_states
    filtered[span] = filtered_states

    return FullFitLabels(
        smoothed=smoothed,
        filtered=filtered,
        fit=fit,
        disagreement=float(np.mean(smoothed_states != filtered_states)),
    )


@dataclass
class FoldFitLabels:
    """Arm B3 -- fitted on this fold's training window only."""

    labels: np.ndarray
    fit: HmmFit
    diagnostic_disagreement: float


def fold_fit_labels(ctx: SymbolContext, fold: Fold) -> FoldFitLabels:
    cfg = ctx.cfg
    start = max(fold.train_start, ctx.valid_from)

    train_rows = ctx.x_raw[start : fold.train_end]
    train_index = np.arange(start, fold.train_end)

    # Fitted on training rows only -- and the standardiser too, which the /hmm
    # endpoint gets wrong by fitting StandardScaler across everything.
    pipeline = FeaturePipeline(cfg.winsor_lower, cfg.winsor_upper).fit(train_rows)
    x_train = pipeline.transform(train_rows)

    fit = select_n_components(
        x_train,
        tuple(cfg.n_components),
        seed=derive_seed(cfg.seed, ctx.symbol, "fold_fit", fold.index),
        bar_indices=train_index,
        **cfg.hmm_kwargs,
    )
    relabel = order_to_relabel(canonical_order(fit.model, ctx.return_feature_index))

    # Decode forward across training, embargo and test. Row t of the forward
    # recursion sees observations up to t and no further, so extending the span
    # past train_end adds no information about the future to any earlier bar.
    span = slice(start, fold.test_end)
    x_span = pipeline.transform(ctx.x_raw[span])
    filtered_states = relabel_states(decode_filtered(fit.model, x_span), relabel)

    labels = _empty_labels(ctx.n_bars)
    labels[span] = filtered_states

    # Diagnostic only. Never reaches selection; recorded so the per-fold
    # disagreement rate can be reported alongside the full-fit figure.
    smoothed_states = relabel_states(decode_smoothed(fit.model, x_span), relabel)

    return FoldFitLabels(
        labels=labels,
        fit=fit,
        diagnostic_disagreement=float(np.mean(smoothed_states != filtered_states)),
    )


# --------------------------------------------------------------------------
# Strategy selection
# --------------------------------------------------------------------------


@dataclass
class Selection:
    strategy: str
    label: object
    in_fold_sharpe: float
    basis: str
    regime_bars: int
    trial_returns: list[np.ndarray] = field(default_factory=list, repr=False)


def select_strategy(ctx: SymbolContext, fold: Fold, labels: np.ndarray) -> Selection:
    """Pick the strategy with the best in-fold Sharpe on bars in the current regime.

    Identical for every regime-conditioned arm, so only the labels differ. This
    departs from the application, which reads REGIME_STRATEGY_MAP[regime][0] --
    that hand-authored map has no HMM equivalent, and using it for A2 alone would
    confound the labelling scheme with the mapping. A2 here is therefore a
    stronger baseline than the app's behaviour, which is noted in the paper.

    The regime is read at the last training bar and held for the whole test
    window. Re-reading it each test bar would be closer to live trading, but
    switching strategies mid-run is not expressible in backtesting.py; with a
    60-bar test window and a refit every fold, this is the practical
    approximation. It is a stated limitation, not an oversight.
    """
    current = labels[fold.train_end - 1]
    train_df = ctx.df.iloc[fold.train_slice]
    train_labels = labels[fold.train_slice]

    if current is None:
        mask = np.ones(len(train_labels), dtype=bool)
        basis, regime_bars = "unlabelled", int(mask.sum())
    else:
        mask = np.array([value == current for value in train_labels], dtype=bool)
        regime_bars = int(mask.sum())
        basis = "regime"
        if regime_bars < MIN_REGIME_BARS:
            mask = np.ones(len(train_labels), dtype=bool)
            basis = "regime_too_sparse"

    best_name, best_sharpe = None, -np.inf
    trial_returns: list[np.ndarray] = []
    for name in STRATEGY_NAMES:
        run = ctx.cache.get(train_df, name, ("train", fold.index))
        trial_returns.append(run.returns.to_numpy())
        sharpe = masked_sharpe(run.returns, mask)
        if np.isfinite(sharpe) and sharpe > best_sharpe:
            best_name, best_sharpe = name, sharpe

    if best_name is None:
        # No strategy traded at all in this window. Record the fallback rather
        # than dropping the fold, so the frequency is visible in the results.
        best_name, basis = STRATEGY_NAMES[0], f"{basis}+no_signal"
        best_sharpe = float("nan")

    return Selection(
        strategy=best_name,
        label=current,
        in_fold_sharpe=float(best_sharpe),
        basis=basis,
        regime_bars=regime_bars,
        trial_returns=trial_returns,
    )


# --------------------------------------------------------------------------
# Fold execution
# --------------------------------------------------------------------------


@dataclass
class FoldOutcome:
    """One (symbol, arm, fold) result row, plus the returns behind it."""

    symbol: str
    arm: str
    fold_index: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    strategy: str | None
    regime_label: object
    selection_basis: str | None
    in_fold_sharpe: float
    regime_bars: int
    n_trades: int
    ok: bool
    error: str | None
    # HMM diagnostics, None for A arms
    fit_bar_min: int | None = None
    fit_bar_max: int | None = None
    n_components: int | None = None
    bic: float | None = None
    converged: bool | None = None
    restarts_converged: int | None = None
    state_persistence: float | None = None
    smoothed_disagreement: float | None = None
    label_churn: float | None = None
    test_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float), repr=False)

    def row(self) -> dict:
        """Flat mapping for the results CSV -- returns are written separately."""
        data = {k: v for k, v in self.__dict__.items() if k != "test_returns"}
        data["regime_label"] = None if self.regime_label is None else str(self.regime_label)
        return data


def _execute(ctx: SymbolContext, fold: Fold, strategy: str) -> tuple[pd.Series, int, bool, str | None]:
    """Run the chosen strategy across the test window, warmed up through the embargo."""
    warmup = ctx.cfg.warmup_bars
    exec_df = ctx.df.iloc[fold.execution_slice(warmup)]
    run = ctx.cache.get(exec_df, strategy, ("test", fold.index))
    test_returns = run.returns.iloc[warmup:]
    n_trades = run.trades_from(ctx.df.index[fold.test_start])
    return test_returns, n_trades, run.ok, run.error


def _outcome(ctx: SymbolContext, arm: str, fold: Fold, **kwargs) -> FoldOutcome:
    return FoldOutcome(
        symbol=ctx.symbol,
        arm=arm,
        fold_index=fold.index,
        train_start=fold.train_start,
        train_end=fold.train_end,
        test_start=fold.test_start,
        test_end=fold.test_end,
        **kwargs,
    )


def run_arm(ctx: SymbolContext, arm: str) -> list[FoldOutcome]:
    """Every fold of one arm for one symbol."""
    if arm == ARM_BUY_HOLD:
        return _run_buy_and_hold(ctx)
    if arm.startswith("A1:"):
        return _run_fixed(ctx, arm, arm.split(":", 1)[1])
    if arm == ARM_RULE:
        return _run_labelled(ctx, arm, lambda: (rule_labels(ctx), None))
    if arm in (ARM_HMM_LEAKED, ARM_HMM_FIT_LEAKED):
        full = full_fit_labels(ctx)
        labels = full.smoothed if arm == ARM_HMM_LEAKED else full.filtered
        return _run_labelled(ctx, arm, lambda: (labels, (full.fit, full.disagreement)))
    if arm == ARM_HMM_HONEST:
        return _run_fold_fitted(ctx, arm)
    raise ValueError(f"unknown arm {arm!r}")


def _run_buy_and_hold(ctx: SymbolContext) -> list[FoldOutcome]:
    outcomes = []
    for fold in ctx.folds:
        outcomes.append(
            _outcome(
                ctx,
                ARM_BUY_HOLD,
                fold,
                strategy=None,
                regime_label=None,
                selection_basis=None,
                in_fold_sharpe=float("nan"),
                regime_bars=0,
                n_trades=1,
                ok=True,
                error=None,
                test_returns=ctx.bh_returns.iloc[fold.test_slice],
            )
        )
    return outcomes


def _run_fixed(ctx: SymbolContext, arm: str, strategy: str) -> list[FoldOutcome]:
    outcomes = []
    for fold in ctx.folds:
        returns, n_trades, ok, error = _execute(ctx, fold, strategy)
        outcomes.append(
            _outcome(
                ctx,
                arm,
                fold,
                strategy=strategy,
                regime_label=None,
                selection_basis="fixed",
                in_fold_sharpe=float("nan"),
                regime_bars=0,
                n_trades=n_trades,
                ok=ok,
                error=error,
                test_returns=returns,
            )
        )
    return outcomes


def _run_labelled(ctx: SymbolContext, arm: str, label_source) -> list[FoldOutcome]:
    """Arms whose labels are computed once for the whole series (A2, B1, B2)."""
    labels, hmm = label_source()
    fit, disagreement = hmm if hmm else (None, None)

    outcomes = []
    for fold in ctx.folds:
        selection = select_strategy(ctx, fold, labels)
        returns, n_trades, ok, error = _execute(ctx, fold, selection.strategy)
        params = canonical_params(fit.model, canonical_order(fit.model, ctx.return_feature_index)) if fit else None
        outcomes.append(
            _outcome(
                ctx,
                arm,
                fold,
                strategy=selection.strategy,
                regime_label=selection.label,
                selection_basis=selection.basis,
                in_fold_sharpe=selection.in_fold_sharpe,
                regime_bars=selection.regime_bars,
                n_trades=n_trades,
                ok=ok,
                error=error,
                fit_bar_min=fit.fitted_bar_min if fit else None,
                fit_bar_max=fit.fitted_bar_max if fit else None,
                n_components=fit.n_components if fit else None,
                bic=fit.bic if fit else None,
                converged=fit.converged if fit else None,
                restarts_converged=fit.restarts_converged if fit else None,
                state_persistence=params["persistence"] if params else None,
                smoothed_disagreement=disagreement,
                test_returns=returns,
            )
        )
    return outcomes


def _run_fold_fitted(ctx: SymbolContext, arm: str) -> list[FoldOutcome]:
    """Arm B3 -- a fresh fit every fold, with labels aligned between them."""
    outcomes = []
    previous_labels = None

    for fold in ctx.folds:
        fitted = fold_fit_labels(ctx, fold)
        selection = select_strategy(ctx, fold, fitted.labels)
        returns, n_trades, ok, error = _execute(ctx, fold, selection.strategy)

        churn = float("nan")
        if previous_labels is not None:
            overlap = slice(max(fold.train_start, ctx.valid_from), fold.train_end)
            churn = label_churn(
                np.array([v for v in previous_labels[overlap] if v is not None]),
                np.array([v for v in fitted.labels[overlap] if v is not None]),
            )
        previous_labels = fitted.labels

        params = canonical_params(
            fitted.fit.model, canonical_order(fitted.fit.model, ctx.return_feature_index)
        )
        outcomes.append(
            _outcome(
                ctx,
                arm,
                fold,
                strategy=selection.strategy,
                regime_label=selection.label,
                selection_basis=selection.basis,
                in_fold_sharpe=selection.in_fold_sharpe,
                regime_bars=selection.regime_bars,
                n_trades=n_trades,
                ok=ok,
                error=error,
                fit_bar_min=fitted.fit.fitted_bar_min,
                fit_bar_max=fitted.fit.fitted_bar_max,
                n_components=fitted.fit.n_components,
                bic=fitted.fit.bic,
                converged=fitted.fit.converged,
                restarts_converged=fitted.fit.restarts_converged,
                state_persistence=params["persistence"],
                smoothed_disagreement=fitted.diagnostic_disagreement,
                label_churn=churn,
                test_returns=returns,
            )
        )
    return outcomes


def stitch(outcomes: list[FoldOutcome]) -> pd.Series:
    """Concatenate per-fold test returns into one continuous out-of-sample series.

    Folds are non-overlapping by construction (walkforward.assert_folds_sound),
    so this never double-counts a bar.
    """
    parts = [o.test_returns for o in outcomes if len(o.test_returns)]
    if not parts:
        return pd.Series(dtype=float)
    return pd.concat(parts).sort_index()
