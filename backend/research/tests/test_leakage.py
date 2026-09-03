"""The regression test that protects the study's central claim.

Arm B3 must never fit on a bar it would not have had, and arms B1 and B2 must
keep leaking exactly as designed -- if someone "fixes" them, the study stops
measuring anything and the paper's headline number silently becomes zero.

Both directions are asserted here, mechanically, from the bar indices fit_hmm
records at the moment of fitting. Neither rests on code review.
"""

import unittest

import numpy as np
import pandas as pd

from research.arms import build_context, fold_fit_labels, full_fit_labels, run_arm, stitch
from research.config import (
    ARM_HMM_FIT_LEAKED,
    ARM_HMM_HONEST,
    ARM_HMM_LEAKED,
    StudyConfig,
)
from regime.features import FeaturePipeline
from regime.synthetic import synthetic_ohlcv

N_BARS = 450


def fast_config(**overrides) -> StudyConfig:
    """A deliberately tiny specification -- fast, and not a research result."""
    settings = dict(
        run_id="test",
        train_bars=200,
        test_bars=50,
        embargo_bars=60,
        warmup_bars=60,
        vol_window=30,
        n_components=[2],
        covariance_type="diag",
        n_iter=20,
        restarts=1,
        min_bars=300,
        min_folds=1,
        seed=7,
    )
    settings.update(overrides)
    return StudyConfig(**settings)


class FitProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = fast_config()
        cls.df = synthetic_ohlcv(n_bars=N_BARS, seed=2)
        cls.ctx = build_context("SYNTH", cls.df, cls.cfg)

    def test_honest_arm_never_fits_on_a_test_bar(self):
        for fold in self.ctx.folds:
            with self.subTest(fold=fold.index):
                fitted = fold_fit_labels(self.ctx, fold)

                self.assertLess(fitted.fit.fitted_bar_max, fold.test_start)

    def test_honest_arm_never_fits_past_the_training_window(self):
        """The invariant that survived removing the embargo.

        Folds are contiguous now, so train_end is the test window's first bar
        and this is the only thing standing between B3 and the leak it exists to
        measure against. It holds with or without a gap.
        """
        for fold in self.ctx.folds:
            with self.subTest(fold=fold.index):
                fitted = fold_fit_labels(self.ctx, fold)

                self.assertLessEqual(fitted.fit.fitted_bar_max, fold.train_end - 1)

    def test_honest_arm_never_fits_past_training_without_an_embargo_either(self):
        """Same assertion on the protocol the baseline actually runs."""
        cfg = fast_config(embargo_bars=0)
        ctx = build_context("SYNTH", self.df, cfg)

        for fold in ctx.folds:
            with self.subTest(fold=fold.index):
                fitted = fold_fit_labels(ctx, fold)

                self.assertEqual(fold.embargo_bars, 0)
                self.assertLessEqual(fitted.fit.fitted_bar_max, fold.train_end - 1)
                self.assertLess(fitted.fit.fitted_bar_max, fold.test_start)

    def test_the_regime_read_bar_is_never_a_test_bar(self):
        """Reading at test_start - 1 is fresh, but it must stay out of the window."""
        for fold in self.ctx.folds:
            with self.subTest(fold=fold.index):
                self.assertLess(fold.regime_read_bar, fold.test_start)

    def test_the_honest_arm_labels_the_regime_read_bar(self):
        """A fresher read point is only usable if the forward decode reaches it."""
        for fold in self.ctx.folds:
            with self.subTest(fold=fold.index):
                labels = fold_fit_labels(self.ctx, fold).labels

                self.assertIsNotNone(labels[fold.regime_read_bar])

    def test_honest_arm_labels_every_test_bar(self):
        for fold in self.ctx.folds:
            with self.subTest(fold=fold.index):
                labels = fold_fit_labels(self.ctx, fold).labels

                self.assertTrue(all(v is not None for v in labels[fold.test_slice]))

    def test_leaked_arms_are_still_leaking(self):
        """Guards the experiment itself: B1 and B2 must see the whole series."""
        full = full_fit_labels(self.ctx)

        self.assertEqual(full.fit.fitted_bar_max, N_BARS - 1)

    def test_the_two_full_fit_decodes_disagree(self):
        """B1 minus B2 is the smoothing leak; a zero disagreement means no effect."""
        full = full_fit_labels(self.ctx)

        self.assertGreater(full.disagreement, 0.0)


class ArmOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = fast_config()
        cls.df = synthetic_ohlcv(n_bars=N_BARS, seed=3)
        cls.ctx = build_context("SYNTH", cls.df, cls.cfg)

    def test_recorded_fit_bounds_match_the_fold_for_the_honest_arm(self):
        for outcome in run_arm(self.ctx, ARM_HMM_HONEST):
            with self.subTest(fold=outcome.fold_index):
                self.assertIsNotNone(outcome.fit_bar_max)
                self.assertLess(outcome.fit_bar_max, outcome.test_start)

    def test_recorded_fit_bounds_span_the_series_for_the_leaked_arms(self):
        for arm in (ARM_HMM_LEAKED, ARM_HMM_FIT_LEAKED):
            for outcome in run_arm(self.ctx, arm):
                with self.subTest(arm=arm, fold=outcome.fold_index):
                    self.assertEqual(outcome.fit_bar_max, N_BARS - 1)

    def test_stitched_returns_never_double_count_a_bar(self):
        stitched = stitch(run_arm(self.ctx, ARM_HMM_HONEST))

        self.assertTrue(stitched.index.is_unique)
        self.assertTrue(stitched.index.is_monotonic_increasing)

    def test_stitched_returns_cover_exactly_the_test_windows(self):
        outcomes = run_arm(self.ctx, ARM_HMM_HONEST)
        stitched = stitch(outcomes)

        expected = sum(fold.test_bars for fold in self.ctx.folds)
        self.assertEqual(len(stitched), expected)

    def test_stitched_returns_contain_no_training_dates(self):
        stitched = stitch(run_arm(self.ctx, ARM_HMM_HONEST))
        test_dates = set()
        for fold in self.ctx.folds:
            test_dates.update(self.df.index[fold.test_slice])

        self.assertTrue(set(stitched.index).issubset(test_dates))

    def test_every_arm_selects_a_strategy_from_the_pool(self):
        from research.execution import STRATEGY_NAMES

        for outcome in run_arm(self.ctx, ARM_HMM_HONEST):
            with self.subTest(fold=outcome.fold_index):
                self.assertIn(outcome.strategy, STRATEGY_NAMES)


class FeaturePipelineLeakageTests(unittest.TestCase):
    """The standardiser is a leak surface too, and a quiet one.

    main.py's /hmm fits StandardScaler across the entire series, so test-period
    scale reaches the training representation. Fitting on training rows only has
    to be enforced, not assumed.
    """

    def setUp(self):
        rng = np.random.default_rng(0)
        self.train = rng.normal(0.0, 1.0, size=(300, 2))
        self.test = rng.normal(50.0, 10.0, size=(100, 2))  # wildly different scale

    def test_statistics_come_from_training_rows_only(self):
        pipeline = FeaturePipeline().fit(self.train)
        before = pipeline.transform(self.train).mean(axis=0).copy()

        pipeline.transform(self.test)

        np.testing.assert_allclose(pipeline.transform(self.train).mean(axis=0), before)

    def test_transformed_test_rows_reflect_the_training_scale(self):
        """A test row far outside the training distribution must look far out.

        Winsorisation caps how far: test rows are clipped to the *training*
        quantile limits before scaling, so they land near that ceiling rather
        than at their raw distance. That capping is the point -- it stops a
        single circuit-limit day from dominating the emission estimates -- but it
        means the assertion here is about ordering, not magnitude.
        """
        pipeline = FeaturePipeline().fit(self.train)

        train_scale = float(np.abs(pipeline.transform(self.train)).mean())
        test_scale = float(np.abs(pipeline.transform(self.test)).mean())

        self.assertGreater(test_scale, 2.0)
        self.assertGreater(test_scale, train_scale * 2)

    def test_transform_before_fit_is_an_error_rather_than_silent_identity(self):
        with self.assertRaises(RuntimeError):
            FeaturePipeline().transform(self.train)


class ConfigGuardTests(unittest.TestCase):
    def test_warmup_longer_than_embargo_is_now_allowed(self):
        """Warm-up crossing into training is causal, so this is no longer an error."""
        cfg = fast_config(warmup_bars=90, embargo_bars=0)

        self.assertEqual(cfg.warmup_bars, 90)
        self.assertEqual(cfg.embargo_bars, 0)

    def test_warmup_that_cannot_fit_before_the_first_test_window_is_rejected(self):
        """The guard that replaced it: warm-up must not run off the series."""
        with self.assertRaises(ValueError) as ctx:
            fast_config(warmup_bars=200, train_bars=200)

        self.assertIn("train_bars", str(ctx.exception))

    def test_feature_set_without_a_return_feature_is_rejected(self):
        cfg = fast_config(features=["hl_spread", "log_vol_rel"])

        with self.assertRaises(ValueError) as ctx:
            build_context("SYNTH", synthetic_ohlcv(n_bars=N_BARS, seed=1), cfg)

        self.assertIn("aligned", str(ctx.exception))

    def test_config_hash_changes_when_any_parameter_changes(self):
        self.assertNotEqual(fast_config().config_hash(), fast_config(seed=8).config_hash())

    def test_config_hash_is_stable_across_calls(self):
        self.assertEqual(fast_config().config_hash(), fast_config().config_hash())

    def test_unknown_arm_is_rejected(self):
        with self.assertRaises(ValueError):
            fast_config(arms=["B9"])


class DeterminismTests(unittest.TestCase):
    """Reproducibility is a stated deliverable, so it gets a test."""

    def test_same_seed_gives_identical_out_of_sample_returns(self):
        df = synthetic_ohlcv(n_bars=N_BARS, seed=4)

        first = stitch(run_arm(build_context("S", df, fast_config()), ARM_HMM_HONEST))
        second = stitch(run_arm(build_context("S", df, fast_config()), ARM_HMM_HONEST))

        pd.testing.assert_series_equal(first, second)


if __name__ == "__main__":
    unittest.main()
