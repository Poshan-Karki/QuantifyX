"""HMM observation features (design section 4.2).

Every feature here is a function of bar t and earlier bars only, so building the
whole frame up front introduces no look-ahead. What must stay fold-local are the
winsorisation limits and the standardiser -- both are estimated on training rows
only, by FeaturePipeline.

Note the volume feature. The /hmm endpoint uses Vol.pct_change(), which is
unbounded above and undefined on zero-volume days; thin NEPSE names have plenty
of those. This uses log volume relative to its own trailing median instead,
which stays finite when volume is zero and is comparable across symbols.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

LOG_RETURN = "log_return"
HL_SPREAD = "hl_spread"
LOG_VOL_REL = "log_vol_rel"

DEFAULT_FEATURES = (LOG_RETURN, HL_SPREAD, LOG_VOL_REL)

#: Index of the feature that state ordering is defined against. Canonicalisation
#: sorts states by their mean log return, so this must stay the return feature.
RETURN_FEATURE = LOG_RETURN


def build_features(
    df: pd.DataFrame,
    columns: tuple[str, ...] = DEFAULT_FEATURES,
    vol_window: int = 60,
) -> pd.DataFrame:
    """Per-bar observation frame, indexed like df.

    Leading rows are NaN wherever a feature needs history it does not have.
    Callers drop or mask them; nothing here forward-fills, because filling a
    return series is itself a quiet form of fabrication.
    """
    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    open_ = df["Open"].astype(float)
    volume = df["Volume"].astype(float)

    available = {
        LOG_RETURN: np.log(close / close.shift(1)),
        HL_SPREAD: (high - low) / open_,
        LOG_VOL_REL: (
            np.log1p(volume)
            - np.log1p(volume.rolling(vol_window, min_periods=max(2, vol_window // 2)).median())
        ),
    }

    unknown = set(columns) - set(available)
    if unknown:
        raise ValueError(f"unknown feature(s): {sorted(unknown)}")

    out = pd.DataFrame({name: available[name] for name in columns}, index=df.index)
    return out.replace([np.inf, -np.inf], np.nan)


@dataclass
class FeaturePipeline:
    """Winsorise, then standardise -- every statistic estimated on train rows only.

    The /hmm endpoint fits StandardScaler across the entire series, which leaks
    test-period scale into the training representation. Arm B3 must not, so the
    fit/transform split is enforced here rather than left to the caller.
    """

    lower_quantile: float = 0.01
    upper_quantile: float = 0.99
    _lower: np.ndarray | None = field(default=None, init=False, repr=False)
    _upper: np.ndarray | None = field(default=None, init=False, repr=False)
    _scaler: StandardScaler | None = field(default=None, init=False, repr=False)

    def fit(self, x_train: np.ndarray) -> "FeaturePipeline":
        x_train = np.asarray(x_train, dtype=float)
        if x_train.ndim != 2 or len(x_train) == 0:
            raise ValueError(f"expected a non-empty 2-D array, got shape {x_train.shape}")
        self._lower = np.quantile(x_train, self.lower_quantile, axis=0)
        self._upper = np.quantile(x_train, self.upper_quantile, axis=0)
        self._scaler = StandardScaler().fit(np.clip(x_train, self._lower, self._upper))
        return self

    def transform(self, x: np.ndarray) -> np.ndarray:
        if self._scaler is None:
            raise RuntimeError("FeaturePipeline.transform called before fit")
        x = np.asarray(x, dtype=float)
        return self._scaler.transform(np.clip(x, self._lower, self._upper))

    def fit_transform(self, x_train: np.ndarray) -> np.ndarray:
        return self.fit(x_train).transform(x_train)


def usable_range(features: pd.DataFrame) -> int:
    """First row index from which every feature is finite.

    Feature warm-up (the trailing volume median in particular) makes the opening
    rows unusable. Folds must start after this or the HMM sees NaNs.
    """
    finite = features.notna().all(axis=1)
    if not finite.any():
        raise ValueError("no rows have all features finite -- check the input data")
    return int(np.argmax(finite.to_numpy()))
