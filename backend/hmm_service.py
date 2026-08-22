"""Regime inference for the /hmm endpoint.

Distinct from backend/research/, which exists to measure how misleading the
previous implementation was when used for backtesting. This is the corrected
production path.

A note on what was and was not wrong before, because the distinction matters:

Fitting on all history up to today is *not* look-ahead for a live query. Today
is the present; all of it is the past. What the old endpoint got wrong was
returning `model.predict(X)` as a historical label series -- Viterbi conditions
on the whole sequence, so the label it gives bar 200 is informed by bar 900, and
no one could have known it at the time. Backtests built on that series are
fiction. The final element is a different matter: at the last bar there is no
future to leak from.

So the history returned here is decoded with the forward recursion only, and the
current state comes from the filtered posterior, which also yields a calibrated
confidence rather than a bare integer.

The other fixes are unglamorous and matter more day to day: a fixed seed and
canonical state ordering so "state 2" means the same thing between calls, BIC
instead of a hardcoded three states, a volume feature that survives zero-volume
days, and a cache so a request does not refit from scratch.

Inference primitives are shared with research.hmm_regime -- the forward
recursion, canonical ordering, BIC selection. Those are generic and tested, and
duplicating them so the API could avoid an import would only create two versions
to drift apart. The study machinery (arms, folds, runner) is not imported here
and must never be reachable from a request.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

from market_regime import REGIME_STRATEGY_MAP, STRATEGY_DESCRIPTIONS
from research.features import LOG_RETURN, RETURN_FEATURE, FeaturePipeline, build_features, usable_range
from research.hmm_regime import (
    canonical_order,
    canonical_params,
    decode_filtered,
    filtered_posteriors,
    order_to_relabel,
    relabel_states,
    select_n_components,
)
from research.rule_regime import (
    HIGH_VOLATILITY,
    LOW_VOLATILITY,
    RANGING,
    TRENDING_DOWN,
    TRENDING_UP,
)

#: Bump when anything that changes a fitted model changes. Part of the cache key,
#: so a deploy cannot serve models built by the previous version.
MODEL_VERSION = "1"

#: Mean daily log return past which a state is called trending rather than
#: ranging. 0.05%/day compounds to roughly 13% a year.
TREND_THRESHOLD = 0.0005

#: A state is volatile (or quiet) when its return dispersion is this far from the
#: median across states of the same model.
HIGH_VOL_RATIO = 1.3
LOW_VOL_RATIO = 0.7

#: Enough bars for the trailing volume median to warm up and for EM to have
#: something to work with. Well short of what the study requires -- this is a
#: floor for answering at all, not for answering well.
MIN_BARS = 250

#: How much labelled history to return. The old endpoint returned every bar,
#: so the payload grew without bound as the database filled up.
HISTORY_BARS = 250

CACHE_SIZE = 64


@dataclass(frozen=True)
class HmmSettings:
    n_components: tuple[int, ...] = (2, 3, 4, 5)
    covariance_type: str = "full"
    n_iter: int = 200
    tol: float = 1e-4
    restarts: int = 8
    seed: int = 20260822
    vol_window: int = 60

    def cache_token(self) -> tuple:
        return (
            MODEL_VERSION,
            self.n_components,
            self.covariance_type,
            self.n_iter,
            self.restarts,
            self.seed,
            self.vol_window,
        )


DEFAULT_SETTINGS = HmmSettings()


@dataclass
class StateProfile:
    """What one hidden state looks like in units a person can read."""

    state: int
    label: str
    mean_daily_return_pct: float
    volatility_pct: float
    persistence: float
    share_of_history: float

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "label": self.label,
            "mean_daily_return_pct": round(self.mean_daily_return_pct, 4),
            "volatility_pct": round(self.volatility_pct, 4),
            "persistence": round(self.persistence, 4),
            "share_of_history": round(self.share_of_history, 4),
        }


@dataclass
class RegimeModel:
    """A fitted model plus everything the endpoint answers from."""

    symbol: str
    as_of: pd.Timestamp
    n_states: int
    profiles: list[StateProfile]
    transmat: np.ndarray
    states: np.ndarray
    dates: pd.DatetimeIndex
    posterior: np.ndarray
    bic: float
    converged: bool
    fitted_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def current_state(self) -> int:
        return int(self.states[-1])

    def label_for(self, state: int) -> str:
        return self.profiles[state].label


def _label_states(mean_returns: np.ndarray, volatilities: np.ndarray) -> list[str]:
    """Name each state using market_regime's vocabulary.

    Precedence follows detect_regime's if/elif chain -- trend first, then
    volatility -- so the two endpoints describe the market the same way and the
    HMM's answer can feed REGIME_STRATEGY_MAP.

    Two states may well earn the same name; that is not a bug. Several distinct
    hidden states can be recognisably the same kind of market, and the raw state
    id is reported alongside so nothing is lost.
    """
    finite = volatilities[np.isfinite(volatilities)]
    median_vol = float(np.median(finite)) if len(finite) else float("nan")

    labels = []
    for mean_return, volatility in zip(mean_returns, volatilities):
        if mean_return > TREND_THRESHOLD:
            labels.append(TRENDING_UP)
        elif mean_return < -TREND_THRESHOLD:
            labels.append(TRENDING_DOWN)
        elif np.isfinite(median_vol) and median_vol > 0 and volatility > median_vol * HIGH_VOL_RATIO:
            labels.append(HIGH_VOLATILITY)
        elif np.isfinite(median_vol) and median_vol > 0 and volatility < median_vol * LOW_VOL_RATIO:
            labels.append(LOW_VOLATILITY)
        else:
            labels.append(RANGING)
    return labels


def fit_regime_model(
    symbol: str,
    df: pd.DataFrame,
    settings: HmmSettings = DEFAULT_SETTINGS,
) -> RegimeModel:
    """Fit on all history available up to the last bar, then decode it honestly."""
    if len(df) < MIN_BARS:
        raise ValueError(
            f"{symbol} has {len(df)} bars; regime detection needs at least {MIN_BARS}."
        )

    features = build_features(df, vol_window=settings.vol_window)
    start = usable_range(features)
    raw = features.to_numpy(dtype=float)[start:]
    if len(raw) < MIN_BARS // 2:
        raise ValueError(
            f"{symbol} has too few usable bars after indicator warm-up ({len(raw)})."
        )

    x = FeaturePipeline().fit_transform(raw)
    fit = select_n_components(
        x,
        candidates=tuple(settings.n_components),
        seed=settings.seed,
        restarts=settings.restarts,
        covariance_type=settings.covariance_type,
        n_iter=settings.n_iter,
        tol=settings.tol,
    )

    return_index = list(features.columns).index(RETURN_FEATURE)
    order = canonical_order(fit.model, return_index)
    relabel = order_to_relabel(order)
    params = canonical_params(fit.model, order)

    states = relabel_states(decode_filtered(fit.model, x), relabel)
    posterior = filtered_posteriors(fit.model, x)[:, order]

    log_returns = features[LOG_RETURN].to_numpy(dtype=float)[start:]
    transmat = np.asarray(params["transmat"])

    profiles = []
    mean_returns = np.full(fit.n_components, np.nan)
    volatilities = np.full(fit.n_components, np.nan)
    for state in range(fit.n_components):
        mask = states == state
        sample = log_returns[mask]
        mean_returns[state] = float(np.mean(sample)) if len(sample) else np.nan
        volatilities[state] = float(np.std(sample, ddof=1)) if len(sample) > 1 else np.nan

    labels = _label_states(mean_returns, volatilities)
    for state in range(fit.n_components):
        mask = states == state
        profiles.append(
            StateProfile(
                state=state,
                label=labels[state],
                mean_daily_return_pct=float(mean_returns[state] * 100),
                volatility_pct=float(volatilities[state] * 100),
                persistence=float(transmat[state, state]),
                share_of_history=float(np.mean(mask)),
            )
        )

    return RegimeModel(
        symbol=symbol,
        as_of=df.index[-1],
        n_states=fit.n_components,
        profiles=profiles,
        transmat=transmat,
        states=states,
        dates=features.index[start:],
        posterior=posterior,
        bic=float(fit.bic),
        converged=bool(fit.converged),
    )


# --------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------

_cache: "OrderedDict[tuple, RegimeModel]" = OrderedDict()
_cache_lock = threading.Lock()


def _cache_key(symbol: str, df: pd.DataFrame, settings: HmmSettings) -> tuple:
    """Keyed on the last bar, so a new day's data invalidates it by itself.

    No time-based expiry: a TTL would either serve stale regimes after an
    update or refit pointlessly on a quiet day. The data is the clock.
    """
    return (symbol, str(df.index[-1].date()), len(df), settings.cache_token())


def get_regime_model(
    symbol: str,
    df: pd.DataFrame,
    settings: HmmSettings = DEFAULT_SETTINGS,
) -> tuple[RegimeModel, bool]:
    """Return a fitted model and whether it came from cache.

    The lock is held across the fit rather than only around the dictionary. It
    means two concurrent first-requests for the same symbol queue instead of
    fitting twice, which is the behaviour worth having when a fit costs seconds.
    """
    key = _cache_key(symbol, df, settings)
    with _cache_lock:
        cached = _cache.get(key)
        if cached is not None:
            _cache.move_to_end(key)
            return cached, True

        model = fit_regime_model(symbol, df, settings)
        _cache[key] = model
        _cache.move_to_end(key)
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
        return model, False


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


# --------------------------------------------------------------------------
# Response
# --------------------------------------------------------------------------


def describe_regime(
    symbol: str,
    df: pd.DataFrame,
    settings: HmmSettings = DEFAULT_SETTINGS,
    history_bars: int = HISTORY_BARS,
) -> dict:
    """The /hmm response.

    Shaped to match /regime's keys -- regime, confidence, recommended_strategies,
    strategy_descriptions, reasoning -- so the two can be rendered by the same
    component and compared directly, which is the whole point of having both.
    """
    model, from_cache = get_regime_model(symbol, df, settings)

    current = model.current_state
    label = model.label_for(current)

    next_distribution = model.posterior[-1] @ model.transmat
    next_state = int(np.argmax(next_distribution))

    # Several states can carry the same name -- two distinct hidden states are
    # often recognisably the same kind of market. Probabilities a person reads
    # have to be summed over the name, or the UI shows a 64% "transition" between
    # two states that are both called Trending Up.
    by_label = _aggregate_by_label(model.posterior[-1], model.profiles)
    next_by_label = _aggregate_by_label(next_distribution, model.profiles)

    confidence = float(by_label.get(label, 0.0))
    next_label = max(next_by_label, key=next_by_label.get)

    recommended = REGIME_STRATEGY_MAP.get(label, [])
    history = min(history_bars, len(model.states))

    return {
        "status": "success",
        "symbol": symbol,
        "as_of": str(model.as_of.date()),
        "regime": label,
        "confidence": round(confidence, 4),
        "next_regime": next_label,
        "next_regime_probability": round(float(next_by_label[next_label]), 4),
        "regime_change_expected": next_label != label,
        "regime_probabilities": {name: round(p, 4) for name, p in by_label.items()},
        "next_regime_probabilities": {name: round(p, 4) for name, p in next_by_label.items()},
        "state": current,
        "next_state": next_state,
        "state_probabilities": [round(float(p), 4) for p in model.posterior[-1]],
        "next_state_probabilities": [round(float(p), 4) for p in next_distribution],
        "n_states": model.n_states,
        "states": [profile.to_dict() for profile in model.profiles],
        "transition_matrix": [[round(float(v), 4) for v in row] for row in model.transmat],
        "recommended_strategies": recommended,
        "strategy_descriptions": {
            name: STRATEGY_DESCRIPTIONS[name] for name in recommended if name in STRATEGY_DESCRIPTIONS
        },
        "reasoning": _build_reasoning(model, label, confidence, next_label, next_by_label),
        "history": {
            "dates": [str(d.date()) for d in model.dates[-history:]],
            "states": [int(s) for s in model.states[-history:]],
            "labels": [model.label_for(int(s)) for s in model.states[-history:]],
            "bars": history,
            "decode": "filtered",
            "note": (
                "Filtered decoding: each label uses only that bar and earlier ones, "
                "so it is what would have been known at the time. Do not substitute "
                "smoothed/Viterbi labels here -- they use later bars and inflate any "
                "backtest built on them."
            ),
        },
        "model": {
            "n_states_selected_by": "BIC",
            "bic": round(model.bic, 2),
            "converged": model.converged,
            "seed": settings.seed,
            "version": MODEL_VERSION,
            "fitted_at": model.fitted_at.isoformat(timespec="seconds") + "Z",
            "cached": from_cache,
        },
    }


def _aggregate_by_label(probabilities: np.ndarray, profiles: list[StateProfile]) -> dict:
    """Sum state probabilities over the names those states carry.

    The model reasons in states; a person reads names. When two states share a
    name, only the summed figure answers "how likely is this kind of market".
    """
    totals: dict[str, float] = {}
    for probability, profile in zip(probabilities, profiles):
        totals[profile.label] = totals.get(profile.label, 0.0) + float(probability)
    return totals


def _build_reasoning(
    model: RegimeModel,
    label: str,
    confidence: float,
    next_label: str,
    next_by_label: dict,
) -> str:
    profile = model.profiles[model.current_state]
    sharing = [p.state for p in model.profiles if p.label == label]

    lines = [
        f"A {model.n_states}-state model was selected by BIC.",
        f"The current state averages {profile.mean_daily_return_pct:+.2f}% a day with "
        f"{profile.volatility_pct:.2f}% daily volatility, which reads as {label.lower()}.",
    ]
    if len(sharing) > 1:
        lines.append(
            f"States {', '.join(str(s) for s in sharing)} all describe that same kind of "
            f"market, so the {confidence * 100:.0f}% confidence is their combined "
            "filtered probability."
        )
    else:
        lines.append(f"Filtered posterior confidence in that regime is {confidence * 100:.0f}%.")

    lines.append(
        f"It persists {profile.persistence * 100:.0f}% of the time and covers "
        f"{profile.share_of_history * 100:.0f}% of the sample."
    )
    probability = next_by_label.get(next_label, 0.0) * 100
    if next_label == label:
        lines.append(f"Tomorrow is most likely the same regime ({probability:.0f}%).")
    else:
        lines.append(f"Tomorrow most likely shifts to {next_label.lower()} ({probability:.0f}%).")
    return " ".join(lines)
