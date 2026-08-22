"""Synthetic data with known regime structure (design section 4.4).

The filtered decode cannot be validated against market data, because the true
state sequence there is unobservable -- that is the whole reason for the model.
It can be validated against data sampled from a generating HMM whose states are
known, which is what the tests do and what the paper's validation subsection
should report.

Also builds the snapshot the smoke config runs against, so the pipeline can be
exercised end to end without a database.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM


def make_generating_hmm(
    means: np.ndarray | None = None,
    covariance_scale: float = 1.0,
    persistence: float = 0.95,
    seed: int = 0,
) -> GaussianHMM:
    """A fully specified HMM to sample from.

    Parameters are set directly rather than fitted, so the state labels are
    ground truth and decoding accuracy is measurable.
    """
    if means is None:
        # Three regimes in (return, spread) space: bear, quiet, bull. Deliberately
        # overlapping, so smoothing has something to add over filtering.
        means = np.array([[-1.2, 0.9], [0.0, -0.6], [1.1, 0.4]])
    means = np.asarray(means, dtype=float)
    n_states, n_features = means.shape

    off = (1.0 - persistence) / (n_states - 1)
    transmat = np.full((n_states, n_states), off)
    np.fill_diagonal(transmat, persistence)

    model = GaussianHMM(n_components=n_states, covariance_type="full", random_state=seed)
    model.startprob_ = np.full(n_states, 1.0 / n_states)
    model.transmat_ = transmat
    model.means_ = means
    model.covars_ = np.array([np.eye(n_features) * covariance_scale for _ in range(n_states)])
    return model


def sample_states(model: GaussianHMM, n_samples: int, seed: int = 0):
    """Draw observations and their true hidden states."""
    x, z = model.sample(n_samples, random_state=seed)
    return np.asarray(x), np.asarray(z, dtype=int)


def synthetic_ohlcv(
    n_bars: int = 900,
    seed: int = 0,
    start: str = "2018-01-01",
    persistence: float = 0.97,
) -> pd.DataFrame:
    """OHLCV bars driven by a hidden regime process.

    Returns switch between a falling, a flat and a rising state, with volatility
    tied to the state, so a regime model has something real to find. Business-day
    index, strictly positive prices, non-zero volume.
    """
    rng = np.random.default_rng(seed)
    n_states = 3
    drift = np.array([-0.0015, 0.0000, 0.0015])
    vol = np.array([0.022, 0.009, 0.014])

    off = (1.0 - persistence) / (n_states - 1)
    transmat = np.full((n_states, n_states), off)
    np.fill_diagonal(transmat, persistence)

    states = np.empty(n_bars, dtype=int)
    states[0] = rng.integers(n_states)
    for t in range(1, n_bars):
        states[t] = rng.choice(n_states, p=transmat[states[t - 1]])

    returns = drift[states] + vol[states] * rng.standard_normal(n_bars)
    close = 100.0 * np.exp(np.cumsum(returns))

    index = pd.bdate_range(start, periods=n_bars)
    open_ = np.empty(n_bars)
    open_[0] = close[0]
    open_[1:] = close[:-1]
    spread = np.abs(rng.normal(0.008, 0.003, n_bars)) * close
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    volume = rng.lognormal(mean=10.0, sigma=0.6, size=n_bars).round()

    return pd.DataFrame(
        {
            "Open": open_,
            "High": high,
            "Low": np.maximum(low, 0.01),
            "Close": close,
            "Volume": volume,
        },
        index=index,
    )


def write_smoke_snapshot(
    path: str | Path = "research/data/smoke_snapshot.csv",
    symbols: tuple[str, ...] = ("SYNTH1", "SYNTH2"),
    n_bars: int = 700,
) -> Path:
    """Snapshot in the same shape as the real one, for the smoke config."""
    frames = []
    for offset, symbol in enumerate(symbols):
        frame = synthetic_ohlcv(n_bars=n_bars, seed=offset).reset_index(names="Date")
        frame.insert(1, "Symbol", symbol)
        frames.append(frame)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.concat(frames).to_csv(path, index=False)
    return path


if __name__ == "__main__":
    print(f"wrote {write_smoke_snapshot()}")
