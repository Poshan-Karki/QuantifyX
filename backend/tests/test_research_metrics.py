import unittest

import numpy as np
import pandas as pd

from research.metrics import (
    annualised_sharpe,
    deflated_sharpe_ratio,
    expected_max_sharpe,
    hit_rate,
    masked_sharpe,
    max_drawdown,
    per_period_sharpe,
    stationary_bootstrap_pvalue,
    summarise,
    total_return,
    trial_sharpe_variance,
)


def returns(values, start="2024-01-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="B"), dtype=float)


class SharpeTests(unittest.TestCase):
    def test_annualisation_scales_by_root_periods(self):
        r = returns(np.random.default_rng(0).normal(0.001, 0.01, 500))

        self.assertAlmostEqual(annualised_sharpe(r), per_period_sharpe(r) * np.sqrt(252), places=9)

    def test_zero_volatility_is_undefined_rather_than_infinite(self):
        self.assertTrue(np.isnan(per_period_sharpe(returns([0.01] * 50))))

    def test_too_few_observations_is_undefined(self):
        self.assertTrue(np.isnan(per_period_sharpe(returns([0.01]))))


class DrawdownTests(unittest.TestCase):
    def test_a_monotonic_rise_has_no_drawdown(self):
        self.assertAlmostEqual(max_drawdown(returns([0.01] * 30)), 0.0, places=12)

    def test_drawdown_is_measured_peak_to_trough(self):
        # up 10%, then down 50% from that peak
        self.assertAlmostEqual(max_drawdown(returns([0.10, -0.50])), -0.50, places=12)

    def test_drawdown_is_never_positive(self):
        r = returns(np.random.default_rng(1).normal(0, 0.02, 400))

        self.assertLessEqual(max_drawdown(r), 0.0)


class TotalReturnTests(unittest.TestCase):
    def test_returns_compound_rather_than_sum(self):
        self.assertAlmostEqual(total_return(returns([0.5, 0.5])), 1.25, places=12)


class MaskedSharpeTests(unittest.TestCase):
    """Selection scores a strategy only on bars carrying the regime label."""

    def test_only_masked_bars_contribute(self):
        r = returns([0.01, -0.05, 0.02, -0.05, 0.03, -0.05])
        mask = np.array([True, False, True, False, True, False])

        self.assertAlmostEqual(masked_sharpe(r, mask), per_period_sharpe(r[mask]), places=12)

    def test_masking_out_losses_raises_the_score(self):
        r = returns([0.01, -0.05, 0.02, -0.05, 0.03, -0.05])
        mask = np.array([True, False, True, False, True, False])

        self.assertGreater(masked_sharpe(r, mask), per_period_sharpe(r))

    def test_mismatched_mask_length_is_an_error(self):
        with self.assertRaises(ValueError):
            masked_sharpe(returns([0.01, 0.02]), np.array([True]))

    def test_a_mask_selecting_one_bar_is_undefined(self):
        r = returns([0.01, 0.02, 0.03])

        self.assertTrue(np.isnan(masked_sharpe(r, np.array([True, False, False]))))


class HitRateTests(unittest.TestCase):
    def test_flat_bars_are_excluded_from_the_denominator(self):
        self.assertAlmostEqual(hit_rate(returns([0.01, 0.0, 0.0, -0.01])), 0.5, places=12)

    def test_no_active_bars_is_undefined(self):
        self.assertTrue(np.isnan(hit_rate(returns([0.0, 0.0]))))


class DeflatedSharpeTests(unittest.TestCase):
    """The correction for having searched a strategy pool (design section 6)."""

    def test_more_trials_raise_the_bar(self):
        few = expected_max_sharpe(2, 0.01)
        many = expected_max_sharpe(200, 0.01)

        self.assertGreater(many, few)

    def test_a_single_trial_needs_no_deflation(self):
        self.assertEqual(expected_max_sharpe(1, 0.01), 0.0)

    def test_deflation_lowers_confidence_as_the_search_widens(self):
        r = returns(np.random.default_rng(2).normal(0.0008, 0.01, 800))

        narrow = deflated_sharpe_ratio(r, n_trials=2, sharpe_variance=0.005)
        wide = deflated_sharpe_ratio(r, n_trials=500, sharpe_variance=0.005)

        self.assertGreater(narrow, wide)

    def test_result_is_a_probability(self):
        r = returns(np.random.default_rng(3).normal(0.001, 0.01, 600))

        value = deflated_sharpe_ratio(r, n_trials=8, sharpe_variance=0.01)

        self.assertGreaterEqual(value, 0.0)
        self.assertLessEqual(value, 1.0)

    def test_trial_variance_needs_at_least_two_trials(self):
        self.assertTrue(np.isnan(trial_sharpe_variance([returns([0.01, 0.02, 0.03])])))


class BootstrapTests(unittest.TestCase):
    """Daily strategy returns are autocorrelated, so blocks are resampled."""

    def test_a_clear_difference_is_significant(self):
        difference = returns(np.random.default_rng(4).normal(0.01, 0.002, 300))

        self.assertLess(stationary_bootstrap_pvalue(difference, n_resamples=200, seed=1), 0.05)

    def test_pure_noise_is_not_significant(self):
        difference = returns(np.random.default_rng(5).normal(0.0, 0.01, 300))

        self.assertGreater(stationary_bootstrap_pvalue(difference, n_resamples=200, seed=1), 0.05)

    def test_too_short_a_series_is_undefined(self):
        self.assertTrue(np.isnan(stationary_bootstrap_pvalue(returns([0.01, 0.02]))))

    def test_result_is_reproducible_for_a_fixed_seed(self):
        difference = returns(np.random.default_rng(6).normal(0.001, 0.01, 200))

        first = stationary_bootstrap_pvalue(difference, n_resamples=100, seed=3)
        second = stationary_bootstrap_pvalue(difference, n_resamples=100, seed=3)

        self.assertEqual(first, second)


class SummariseTests(unittest.TestCase):
    def test_summary_reports_every_metric_the_results_table_needs(self):
        summary = summarise(returns(np.random.default_rng(7).normal(0.0005, 0.01, 300)), n_trades=12)

        for key in (
            "sharpe_annualised",
            "sharpe_per_period",
            "total_return",
            "cagr",
            "max_drawdown",
            "calmar",
            "hit_rate",
            "time_in_market",
            "trades_per_year",
        ):
            with self.subTest(metric=key):
                self.assertIn(key, summary)

    def test_an_empty_series_summarises_without_raising(self):
        summary = summarise(pd.Series(dtype=float))

        self.assertEqual(summary["n_bars"], 0)


if __name__ == "__main__":
    unittest.main()
