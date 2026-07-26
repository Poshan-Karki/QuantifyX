import unittest

import pandas as pd

from analysis_split import chronological_holdout, period_details


class ChronologicalHoldoutTests(unittest.TestCase):
    @staticmethod
    def frame(size):
        index = pd.date_range("2024-01-01", periods=size, freq="D")
        return pd.DataFrame({"Close": range(size)}, index=index)

    def test_uses_seventy_percent_training_when_both_sides_are_large_enough(self):
        training, holdout = chronological_holdout(self.frame(300))

        self.assertEqual(len(training), 210)
        self.assertEqual(len(holdout), 90)
        self.assertLess(training.index[-1], holdout.index[0])

    def test_preserves_minimum_holdout_size(self):
        training, holdout = chronological_holdout(self.frame(120))

        self.assertEqual(len(training), 60)
        self.assertEqual(len(holdout), 60)

    def test_rejects_insufficient_data_with_actionable_message(self):
        with self.assertRaisesRegex(ValueError, "Choose an earlier start date"):
            chronological_holdout(self.frame(119))

    def test_period_details_are_json_ready(self):
        details = period_details(self.frame(60))

        self.assertEqual(
            details,
            {"start": "2024-01-01", "end": "2024-02-29", "bars": 60},
        )


if __name__ == "__main__":
    unittest.main()
