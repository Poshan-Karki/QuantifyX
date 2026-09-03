import unittest

from research.walkforward import (
    ANCHORED,
    ROLLING,
    Fold,
    assert_folds_sound,
    generate_folds,
    required_bars,
)


class GenerateFoldsTests(unittest.TestCase):
    def test_anchored_training_window_expands_from_a_fixed_origin(self):
        folds = generate_folds(1200, ANCHORED, train_bars=300, test_bars=60, embargo_bars=60)

        self.assertTrue(all(fold.train_start == 0 for fold in folds))
        self.assertEqual([fold.train_bars for fold in folds][:3], [300, 360, 420])

    def test_rolling_training_window_keeps_a_constant_width(self):
        folds = generate_folds(1200, ROLLING, train_bars=300, test_bars=60, embargo_bars=60)

        self.assertTrue(all(fold.train_bars == 300 for fold in folds))
        self.assertEqual([fold.train_start for fold in folds][:3], [0, 60, 120])

    def test_embargo_separates_every_training_window_from_its_test_window(self):
        folds = generate_folds(1500, ANCHORED, train_bars=300, test_bars=60, embargo_bars=45)

        for fold in folds:
            with self.subTest(fold=fold.index):
                self.assertEqual(fold.embargo_bars, 45)
                self.assertGreater(fold.test_start, fold.train_end)

    def test_default_step_produces_contiguous_non_overlapping_test_windows(self):
        """Stitched out-of-sample returns must not double-count any bar."""
        folds = generate_folds(1500, ANCHORED, train_bars=300, test_bars=60, embargo_bars=60)

        for previous, current in zip(folds, folds[1:]):
            with self.subTest(fold=current.index):
                self.assertEqual(current.test_start, previous.test_end)

    def test_no_fold_extends_past_the_end_of_the_series(self):
        folds = generate_folds(1000, ANCHORED, train_bars=300, test_bars=60, embargo_bars=60)

        self.assertTrue(all(fold.test_end <= 1000 for fold in folds))

    def test_series_too_short_yields_no_folds(self):
        self.assertEqual(generate_folds(200, train_bars=300, test_bars=60, embargo_bars=60), [])

    def test_rejects_an_unknown_scheme(self):
        with self.assertRaises(ValueError):
            generate_folds(1000, scheme="sliding")


class ExecutionSliceTests(unittest.TestCase):
    """Warm-up runs backwards from the test window and may cross into training.

    Reading a bar's own past is causal. Warm-up bars are neither fitted on nor
    scored, so the old rule that warm-up had to fit inside the embargo bought
    nothing and forced the embargo -- and the regime staleness -- to exist.
    """

    def test_execution_slice_starts_warmup_bars_before_the_test_window(self):
        fold = Fold(0, 0, 300, 360, 420)

        self.assertEqual(fold.execution_slice(60), slice(300, 420))

    def test_warmup_may_reach_into_training_bars(self):
        """Contiguous fold: warm-up has nowhere to go but the training window."""
        fold = Fold(0, 0, 300, 300, 360)

        self.assertEqual(fold.execution_slice(60), slice(240, 360))

    def test_warmup_longer_than_the_embargo_is_allowed(self):
        fold = Fold(0, 0, 300, 330, 390)

        self.assertEqual(fold.execution_slice(60), slice(270, 390))

    def test_warmup_running_off_the_start_of_the_series_is_rejected(self):
        fold = Fold(0, 0, 40, 40, 100)

        with self.assertRaises(ValueError) as ctx:
            fold.execution_slice(60)

        self.assertIn("start of the series", str(ctx.exception))

    def test_negative_warmup_is_rejected(self):
        with self.assertRaises(ValueError):
            Fold(0, 0, 300, 300, 360).execution_slice(-1)


class RegimeReadBarTests(unittest.TestCase):
    """The regime is read at the last bar before the test window."""

    def test_contiguous_fold_reads_the_last_training_bar(self):
        fold = Fold(0, 0, 300, 300, 360)

        self.assertEqual(fold.regime_read_bar, 299)
        self.assertEqual(fold.embargo_bars, 0)

    def test_an_embargo_moves_the_read_bar_forward_not_backward(self):
        """The old code read train_end - 1 = 299 here, throwing away 60 bars."""
        fold = Fold(0, 0, 300, 360, 420)

        self.assertEqual(fold.regime_read_bar, 359)

    def test_max_regime_age_is_the_window_length_on_a_contiguous_fold(self):
        fold = Fold(0, 0, 300, 300, 360)

        self.assertEqual(fold.max_regime_age_bars, 60)

    def test_an_embargo_adds_its_own_width_to_the_staleness(self):
        fold = Fold(0, 0, 300, 360, 420)

        # Read at 359, held through 419.
        self.assertEqual(fold.max_regime_age_bars, 60)

    def test_reading_at_the_old_bar_would_have_been_120_bars_stale(self):
        """What the previous design actually cost, stated as a number."""
        fold = Fold(0, 0, 300, 360, 420)
        old_read_bar = fold.train_end - 1

        self.assertEqual(fold.test_end - 1 - old_read_bar, 120)
        self.assertEqual(fold.max_regime_age_bars, 60)


class SoundnessTests(unittest.TestCase):
    def test_empty_fold_list_is_rejected_with_an_actionable_message(self):
        with self.assertRaises(ValueError) as ctx:
            assert_folds_sound([])

        self.assertIn("train_bars", str(ctx.exception))

    def test_overlapping_test_windows_are_rejected(self):
        folds = [Fold(0, 0, 100, 160, 260), Fold(1, 0, 160, 220, 320)]

        with self.assertRaises(ValueError) as ctx:
            assert_folds_sound(folds)

        self.assertIn("overlaps", str(ctx.exception))

    def test_test_window_starting_before_training_ends_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            assert_folds_sound([Fold(0, 0, 300, 250, 310)])

        self.assertIn("leakage", str(ctx.exception))

    def test_generated_folds_are_always_sound(self):
        for scheme in (ANCHORED, ROLLING):
            with self.subTest(scheme=scheme):
                assert_folds_sound(generate_folds(2000, scheme, 500, 60, 60))


class RequiredBarsTests(unittest.TestCase):
    def test_required_bars_matches_what_generate_folds_actually_needs(self):
        needed = required_bars(train_bars=300, test_bars=60, embargo_bars=60, min_folds=3)

        self.assertEqual(len(generate_folds(needed, train_bars=300, test_bars=60, embargo_bars=60)), 3)
        self.assertEqual(
            len(generate_folds(needed - 1, train_bars=300, test_bars=60, embargo_bars=60)), 2
        )


if __name__ == "__main__":
    unittest.main()
