import unittest

import numpy as np
from hmmlearn.hmm import GaussianHMM

from regime.hmm_regime import (
    canonical_order,
    decode_filtered,
    decode_smoothed,
    fit_hmm,
    forward_log_alpha,
    free_parameters,
    order_to_relabel,
    relabel_states,
    select_n_components,
    total_loglik,
)
from regime.synthetic import make_generating_hmm, sample_states


class ForwardRecursionTests(unittest.TestCase):
    """The forward pass is hand-rolled, so it needs an independent check.

    hmmlearn's score() is the sequence log-likelihood computed by the library's
    own forward-backward. If our recursion agrees with it to floating point, the
    recursion is right -- and if a future hmmlearn changes the private method
    frame_loglik depends on, this is the test that catches it.
    """

    def test_forward_total_matches_hmmlearn_score(self):
        model = make_generating_hmm()
        x, _ = sample_states(model, 400, seed=3)

        self.assertAlmostEqual(total_loglik(forward_log_alpha(model, x)), float(model.score(x)), places=6)

    def test_forward_alpha_has_one_row_per_observation(self):
        model = make_generating_hmm()
        x, _ = sample_states(model, 250, seed=4)

        self.assertEqual(forward_log_alpha(model, x).shape, (250, model.n_components))


class FilteredVersusSmoothedTests(unittest.TestCase):
    """The central claim of the study, verified on data whose states are known.

    Decoding uses the generating model itself, so state labels are ground truth
    and no fitting noise enters. Smoothed decoding sees the whole sequence and
    must therefore recover the true states at least as often as filtered
    decoding, which sees only the past. If this ever inverts, the filtered
    implementation is wrong and every B3 result is meaningless.
    """

    def setUp(self):
        self.model = make_generating_hmm(covariance_scale=1.0)
        self.x, self.z = sample_states(self.model, 1500, seed=11)

    def test_smoothed_recovers_the_true_states_at_least_as_often_as_filtered(self):
        smoothed = decode_smoothed(self.model, self.x)
        filtered = decode_filtered(self.model, self.x)

        smoothed_accuracy = float(np.mean(smoothed == self.z))
        filtered_accuracy = float(np.mean(filtered == self.z))

        self.assertGreaterEqual(smoothed_accuracy + 1e-12, filtered_accuracy)

    def test_the_two_decodes_actually_disagree_on_overlapping_regimes(self):
        """A tie would mean the test above passes vacuously."""
        smoothed = decode_smoothed(self.model, self.x)
        filtered = decode_filtered(self.model, self.x)

        self.assertGreater(float(np.mean(smoothed != filtered)), 0.0)

    def test_filtered_label_at_t_ignores_everything_after_t(self):
        """The property that makes filtered decoding tradeable.

        Rewriting the tail of the observation sequence must not change any label
        at or before the cut. Viterbi over the full sequence does change them,
        which is exactly why it cannot be used.
        """
        cut = 900
        mutated = self.x.copy()
        mutated[cut:] = mutated[cut:][::-1] * 3.0

        original = decode_filtered(self.model, self.x)[:cut]
        perturbed = decode_filtered(self.model, mutated)[:cut]

        np.testing.assert_array_equal(original, perturbed)


class CanonicalisationTests(unittest.TestCase):
    """State ids are arbitrary; canonical labels must not be.

    Two models that differ only by a permutation of their states have to produce
    identical label sequences after canonicalisation. Without this, refitting
    every fold silently renames the regimes and the signal becomes noise.
    """

    def _permuted(self, model, order):
        permuted = GaussianHMM(n_components=model.n_components, covariance_type="full")
        permuted.startprob_ = np.asarray(model.startprob_)[order]
        permuted.transmat_ = np.asarray(model.transmat_)[np.ix_(order, order)]
        permuted.means_ = np.asarray(model.means_)[order]
        permuted.covars_ = np.asarray(model.covars_)[order]
        return permuted

    def test_permuting_states_leaves_canonical_labels_unchanged(self):
        model = make_generating_hmm()
        x, _ = sample_states(model, 600, seed=7)
        order = np.array([2, 0, 1])

        def canonical(candidate):
            states = decode_filtered(candidate, x)
            return relabel_states(states, order_to_relabel(canonical_order(candidate)))

        np.testing.assert_array_equal(canonical(model), canonical(self._permuted(model, order)))

    def test_canonical_order_sorts_states_from_most_bearish_to_most_bullish(self):
        model = make_generating_hmm(means=np.array([[0.5, 0.0], [-1.5, 0.0], [2.0, 0.0]]))

        order = canonical_order(model, return_feature=0)

        np.testing.assert_array_equal(order, [1, 0, 2])

    def test_relabelling_is_a_bijection(self):
        relabel = order_to_relabel(np.array([2, 0, 1]))

        self.assertCountEqual(relabel.tolist(), [0, 1, 2])


class FittingTests(unittest.TestCase):
    def test_fit_records_the_bars_it_was_given(self):
        """Fit provenance is what the leakage test reads; it must be recorded."""
        model = make_generating_hmm()
        x, _ = sample_states(model, 300, seed=5)

        fit = fit_hmm(x, n_components=2, seed=0, restarts=1, n_iter=20, bar_indices=np.arange(40, 340))

        self.assertEqual((fit.fitted_bar_min, fit.fitted_bar_max), (40, 339))

    def test_bar_indices_must_match_the_data_length(self):
        model = make_generating_hmm()
        x, _ = sample_states(model, 100, seed=5)

        with self.assertRaises(ValueError):
            fit_hmm(x, n_components=2, restarts=1, n_iter=10, bar_indices=np.arange(50))

    def test_restarts_are_deterministic_for_a_fixed_seed(self):
        model = make_generating_hmm()
        x, _ = sample_states(model, 400, seed=6)

        first = fit_hmm(x, n_components=3, seed=42, restarts=3, n_iter=25)
        second = fit_hmm(x, n_components=3, seed=42, restarts=3, n_iter=25)

        self.assertAlmostEqual(first.loglik, second.loglik, places=9)

    def test_bic_selection_records_every_candidate_it_scored(self):
        model = make_generating_hmm()
        x, _ = sample_states(model, 800, seed=8)

        fit = select_n_components(x, candidates=(2, 3), seed=1, restarts=2, n_iter=40)

        self.assertEqual(sorted(fit.bic_by_n_components), [2, 3])
        self.assertEqual(fit.bic, min(fit.bic_by_n_components.values()))


class FreeParameterTests(unittest.TestCase):
    """BIC is only as trustworthy as its parameter count."""

    def test_full_covariance_has_more_parameters_than_diagonal(self):
        full = free_parameters(3, 4, "full")
        diag = free_parameters(3, 4, "diag")

        self.assertGreater(full, diag)

    def test_counts_transitions_means_and_covariances(self):
        # K=2, d=2, full: startprob 1 + transmat 2 + means 4 + covars 6 = 13
        self.assertEqual(free_parameters(2, 2, "full"), 13)

    def test_unsupported_covariance_type_is_rejected(self):
        with self.assertRaises(ValueError):
            free_parameters(2, 2, "banded")


if __name__ == "__main__":
    unittest.main()
