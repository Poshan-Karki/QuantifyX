"""Keeps the study's copy of the rule-based classifier honest.

research.rule_regime restates market_regime.detect_regime's thresholds as a
vectorised series, because the study needs a label on every bar and the endpoint
only reports the latest one. Two copies of the same logic drift. detect_regime
is the live implementation and stays authoritative, so these tests assert the
copy still agrees with it.
"""

import unittest

import numpy as np
import pandas as pd

from market_regime import detect_regime
from research.rule_regime import REGIMES, rule_regime_series


def ohlcv_from_close(close):
    return pd.DataFrame(
        {
            "Open": close.shift(1).fillna(close.iloc[0]),
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": pd.Series(1000.0, index=close.index),
        }
    )


def steady_uptrend(n=200):
    index = pd.date_range("2024-01-01", periods=n, freq="D")
    return ohlcv_from_close(pd.Series(np.linspace(100, 190, n), index=index))


def steady_downtrend(n=200):
    index = pd.date_range("2024-01-01", periods=n, freq="D")
    return ohlcv_from_close(pd.Series(np.linspace(190, 100, n), index=index))


def choppy(n=200, seed=0):
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-01-01", periods=n, freq="D")
    close = 100 + np.cumsum(rng.normal(0, 0.4, n))
    return ohlcv_from_close(pd.Series(close, index=index))


def volatile(n=200, seed=1):
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-01-01", periods=n, freq="D")
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.05, n)))
    return ohlcv_from_close(pd.Series(close, index=index))


class AgreementWithDetectRegimeTests(unittest.TestCase):
    """The final bar of the series is the one detect_regime reports on."""

    def test_agrees_on_the_last_bar_across_market_shapes(self):
        for name, frame in (
            ("uptrend", steady_uptrend()),
            ("downtrend", steady_downtrend()),
            ("choppy", choppy()),
            ("volatile", volatile()),
        ):
            with self.subTest(market=name):
                self.assertEqual(rule_regime_series(frame).iloc[-1], detect_regime(frame)["regime"])

    def test_agrees_on_the_last_bar_of_progressively_truncated_series(self):
        """Each truncation is a different 'now', which exercises the rolling windows."""
        frame = volatile(n=240, seed=5)

        for end in (150, 180, 210, 240):
            with self.subTest(end=end):
                window = frame.iloc[:end]
                self.assertEqual(
                    rule_regime_series(window).iloc[-1], detect_regime(window)["regime"]
                )


class LabelSeriesTests(unittest.TestCase):
    def test_every_label_is_a_known_regime(self):
        labels = rule_regime_series(volatile()).dropna()

        self.assertTrue(set(labels).issubset(set(REGIMES)))

    def test_labels_are_indexed_like_the_input(self):
        frame = choppy()

        pd.testing.assert_index_equal(rule_regime_series(frame).index, frame.index)

    def test_warmup_bars_are_unlabelled_rather_than_guessed(self):
        """The 50-bar EMA read 10 bars back cannot produce a label before bar 60."""
        labels = rule_regime_series(steady_uptrend())

        self.assertTrue(labels.iloc[:55].isna().all())

    def test_a_sustained_uptrend_is_labelled_trending_up_at_the_end(self):
        self.assertEqual(rule_regime_series(steady_uptrend()).iloc[-1], "Trending Up")


if __name__ == "__main__":
    unittest.main()
