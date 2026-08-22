"""Gaussian HMM regime model: fitting, canonicalisation, and decoding.

Design sections 4.2 to 4.4. Three things here matter more than the fitting:

1. Filtered vs smoothed decoding. hmmlearn's predict() runs Viterbi over the
   whole observation sequence, so the state it assigns to bar t is informed by
   bars after t. That label is unobtainable in real time. decode_filtered runs
   the forward recursion only, which is what you would actually have known.

2. Canonicalisation. HMM states are identified only up to permutation, so
   state 2 in one fold has no relationship to state 2 in the next. Under a
   protocol that refits every fold, unaligned labels silently turn the regime
   signal into noise.

3. Fit provenance. fit_hmm records the bar indices it was given, so the
   leakage regression test can assert mechanically that arm B3 never saw a test
   bar -- rather than that assertion resting on code review.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from hmmlearn.hmm import GaussianHMM
from scipy.optimize import linear_sum_assignment
from scipy.special import logsumexp

_TINY = 1e-300

DEFAULT_N_COMPONENTS = (2, 3, 4, 5)


@dataclass
class HmmFit:
    """A fitted model plus everything the paper needs to report about the fit."""

    model: GaussianHMM
    n_components: int
    loglik: float
    bic: float
    converged: bool
    restarts: int
    restarts_converged: int
    seed: int
    #: Bar indices of the rows this model was fitted on. None when the caller did
    #: not supply them. The leakage test reads these.
    fitted_bar_min: int | None = None
    fitted_bar_max: int | None = None
    bic_by_n_components: dict[int, float] = field(default_factory=dict)


def free_parameters(n_components: int, n_features: int, covariance_type: str) -> int:
    """Free parameter count for BIC.

    Computed here rather than taken from hmmlearn so the number is explicit and
    auditable -- a referee may well ask how it was counted.

    startprob (K-1) + transmat K(K-1) + means K*d + covariance parameters.
    """
    k, d = n_components, n_features
    if covariance_type == "full":
        covar = k * d * (d + 1) // 2
    elif covariance_type == "diag":
        covar = k * d
    elif covariance_type == "spherical":
        covar = k
    elif covariance_type == "tied":
        covar = d * (d + 1) // 2
    else:
        raise ValueError(f"unsupported covariance_type {covariance_type!r}")
    return (k - 1) + k * (k - 1) + k * d + covar


def bayesian_information_criterion(loglik: float, n_params: int, n_samples: int) -> float:
    """BIC = -2 log L + k ln(n). Lower is better."""
    return -2.0 * loglik + n_params * np.log(n_samples)


def fit_hmm(
    x: np.ndarray,
    n_components: int,
    seed: int = 0,
    restarts: int = 10,
    covariance_type: str = "full",
    n_iter: int = 200,
    tol: float = 1e-4,
    bar_indices: np.ndarray | None = None,
) -> HmmFit:
    """Fit with several random restarts, keeping the highest log-likelihood.

    EM converges only to a local maximum, so a single fit is a coin flip on a
    series this short. Restarts are seeded deterministically from `seed` so the
    whole thing stays reproducible.
    """
    x = np.asarray(x, dtype=float)
    if x.ndim != 2 or len(x) == 0:
        raise ValueError(f"expected a non-empty 2-D array, got shape {x.shape}")
    if restarts < 1:
        raise ValueError(f"restarts must be at least 1, got {restarts}")

    best: GaussianHMM | None = None
    best_loglik = -np.inf
    n_converged = 0

    for attempt in range(restarts):
        model = GaussianHMM(
            n_components=n_components,
            covariance_type=covariance_type,
            n_iter=n_iter,
            tol=tol,
            random_state=seed + attempt,
        )
        try:
            model.fit(x)
            loglik = float(model.score(x))
        except (ValueError, np.linalg.LinAlgError):
            # Degenerate restart -- a state collapsed onto near-zero variance.
            # Skip it; if every restart fails the error below is raised instead.
            continue
        if model.monitor_.converged:
            n_converged += 1
        if np.isfinite(loglik) and loglik > best_loglik:
            best, best_loglik = model, loglik

    if best is None:
        raise RuntimeError(
            f"all {restarts} restarts failed for n_components={n_components}. "
            "The training window is probably too short or degenerate for this many states."
        )

    n_params = free_parameters(n_components, x.shape[1], covariance_type)
    fit = HmmFit(
        model=best,
        n_components=n_components,
        loglik=best_loglik,
        bic=bayesian_information_criterion(best_loglik, n_params, len(x)),
        converged=bool(best.monitor_.converged),
        restarts=restarts,
        restarts_converged=n_converged,
        seed=seed,
    )
    if bar_indices is not None:
        bar_indices = np.asarray(bar_indices)
        if len(bar_indices) != len(x):
            raise ValueError("bar_indices must have one entry per row of x")
        fit.fitted_bar_min = int(bar_indices.min())
        fit.fitted_bar_max = int(bar_indices.max())
    return fit


def select_n_components(
    x: np.ndarray,
    candidates: tuple[int, ...] = DEFAULT_N_COMPONENTS,
    **fit_kwargs,
) -> HmmFit:
    """Choose K by BIC on the data given, then return that fit.

    Callers must pass training-fold rows only. Selecting K on the full series
    would be a fitting leak in its own right, and a subtle one, because the
    chosen K is a single integer that looks harmless in a results table.
    """
    scores: dict[int, float] = {}
    best: HmmFit | None = None
    for k in candidates:
        try:
            fit = fit_hmm(x, n_components=k, **fit_kwargs)
        except RuntimeError:
            continue
        scores[k] = fit.bic
        if best is None or fit.bic < best.bic:
            best = fit
    if best is None:
        raise RuntimeError(
            f"no candidate in {candidates} could be fitted. Check the training window length."
        )
    best.bic_by_n_components = scores
    return best


# --------------------------------------------------------------------------
# Decoding
# --------------------------------------------------------------------------


def frame_loglik(model: GaussianHMM, x: np.ndarray) -> np.ndarray:
    """Per-bar, per-state emission log-likelihood, shape (T, K).

    Uses hmmlearn's own routine when available -- it is a private method, but it
    is the definition the library itself decodes with, so matching it exactly
    matters more than API tidiness. The fallback reconstructs it from the public
    means_/covars_ attributes. test_hmm_regime asserts the forward recursion
    built on this reproduces model.score(), which catches either path breaking.
    """
    compute = getattr(model, "_compute_log_likelihood", None)
    if callable(compute):
        return np.asarray(compute(np.asarray(x, dtype=float)))

    from scipy.stats import multivariate_normal

    x = np.asarray(x, dtype=float)
    covars = np.asarray(model.covars_)  # hmmlearn returns (K, d, d) for every type
    out = np.empty((len(x), model.n_components))
    for state in range(model.n_components):
        out[:, state] = multivariate_normal.logpdf(
            x, mean=model.means_[state], cov=covars[state], allow_singular=True
        )
    return out


def forward_log_alpha(model: GaussianHMM, x: np.ndarray) -> np.ndarray:
    """Forward recursion in log space, shape (T, K).

    log_alpha[t, i] = log P(observations 1..t, state_t = i)

    Only observations up to and including t enter row t. That is the whole
    point: this is the estimate that exists in real time.
    """
    fl = frame_loglik(model, x)
    log_start = np.log(np.maximum(model.startprob_, _TINY))
    log_trans = np.log(np.maximum(model.transmat_, _TINY))

    log_alpha = np.empty_like(fl)
    log_alpha[0] = log_start + fl[0]
    for t in range(1, len(fl)):
        log_alpha[t] = logsumexp(log_alpha[t - 1][:, None] + log_trans, axis=0) + fl[t]
    return log_alpha


def total_loglik(log_alpha: np.ndarray) -> float:
    """Sequence log-likelihood implied by a forward pass.

    Equals model.score(x) when the recursion is correct, which is exactly how
    the test validates it.
    """
    return float(logsumexp(log_alpha[-1]))


def filtered_posteriors(model: GaussianHMM, x: np.ndarray) -> np.ndarray:
    """P(state_t = i | observations 1..t), shape (T, K)."""
    log_alpha = forward_log_alpha(model, x)
    return np.exp(log_alpha - logsumexp(log_alpha, axis=1, keepdims=True))


def decode_filtered(model: GaussianHMM, x: np.ndarray) -> np.ndarray:
    """Most likely state at each bar given only that bar and earlier ones.

    This is the honest decode. Use it for anything that feeds a trading decision.
    """
    return np.asarray(forward_log_alpha(model, x).argmax(axis=1), dtype=int)


def decode_smoothed(model: GaussianHMM, x: np.ndarray) -> np.ndarray:
    """Viterbi path over the whole sequence -- uses future observations.

    Arm B1 only. Never reachable from a trading decision, by construction.
    """
    return np.asarray(model.predict(np.asarray(x, dtype=float)), dtype=int)


# --------------------------------------------------------------------------
# Canonicalisation (design section 4.3)
# --------------------------------------------------------------------------


def canonical_order(model: GaussianHMM, return_feature: int = 0) -> np.ndarray:
    """State ordering by mean return, most bearish first.

    Returns `order` such that old state order[j] becomes new state j.
    """
    return np.argsort(np.asarray(model.means_)[:, return_feature], kind="stable")


def order_to_relabel(order: np.ndarray) -> np.ndarray:
    """Invert an ordering into a lookup table: relabel[old_state] -> new_state."""
    relabel = np.empty(len(order), dtype=int)
    relabel[np.asarray(order)] = np.arange(len(order))
    return relabel


def relabel_states(states: np.ndarray, relabel: np.ndarray) -> np.ndarray:
    """Apply a relabelling table to a decoded state sequence."""
    return np.asarray(relabel)[np.asarray(states, dtype=int)]


def canonical_params(model: GaussianHMM, order: np.ndarray) -> dict:
    """Model parameters permuted into canonical order, for reporting.

    The fitted model itself is left untouched -- decoding uses raw state ids and
    the sequence is relabelled afterwards, which avoids fighting hmmlearn's
    attribute setters.
    """
    order = np.asarray(order)
    return {
        "startprob": np.asarray(model.startprob_)[order],
        "transmat": np.asarray(model.transmat_)[np.ix_(order, order)],
        "means": np.asarray(model.means_)[order],
        "persistence": float(np.mean(np.diag(np.asarray(model.transmat_)[np.ix_(order, order)]))),
    }


def match_to_reference(model: GaussianHMM, reference_means: np.ndarray) -> np.ndarray:
    """Alternative alignment: Hungarian matching on emission-mean distance.

    Reported as a robustness check against the mean-return ordering. Requires
    the same number of states as the reference; when K changed between folds,
    fall back to canonical_order.
    """
    means = np.asarray(model.means_)
    reference_means = np.asarray(reference_means)
    if means.shape != reference_means.shape:
        raise ValueError(
            f"state count changed ({means.shape[0]} vs {reference_means.shape[0]}); "
            "Hungarian matching needs a like-for-like model"
        )
    cost = np.linalg.norm(means[:, None, :] - reference_means[None, :, :], axis=2)
    rows, cols = linear_sum_assignment(cost)
    relabel = np.empty(len(means), dtype=int)
    relabel[rows] = cols
    return relabel


def label_churn(previous: np.ndarray, current: np.ndarray) -> float:
    """Fraction of overlapping bars whose canonical label changed between refits.

    High churn means the states are not tracking anything stable, which is a
    finding in its own right rather than merely a nuisance.
    """
    previous = np.asarray(previous)
    current = np.asarray(current)
    n = min(len(previous), len(current))
    if n == 0:
        return float("nan")
    return float(np.mean(previous[-n:] != current[-n:]))
