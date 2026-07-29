import unittest

import numpy as np
import pandas as pd

from market_regime import (
    REGIME_STRATEGY_MAP,
    STRATEGY_DESCRIPTIONS,
    detect_regime,
)


def ohlcv_from_close(close):
    """Build a minimal OHLCV frame around a close series."""
    return pd.DataFrame(
        {
            "Open": close.shift(1).fillna(close.iloc[0]),
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": pd.Series(1000, index=close.index),
        }
    )


def steady_uptrend(n=120):
    index = pd.date_range("2024-01-01", periods=n, freq="D")
    return ohlcv_from_close(pd.Series(np.linspace(100, 160, n), index=index))


class StrategyMapTests(unittest.TestCase):
    """Guards against a regime recommending a strategy that has no description.

    detect_regime builds strategy_descriptions by direct lookup, so any gap
    here would raise KeyError at request time rather than degrading gracefully.
    """

    def test_every_recommended_strategy_has_a_description(self):
        for regime, strategies in REGIME_STRATEGY_MAP.items():
            for strategy in strategies:
                with self.subTest(regime=regime, strategy=strategy):
                    self.assertIn(strategy, STRATEGY_DESCRIPTIONS)

    def test_strategy_descriptions_are_non_empty(self):
        for strategy, description in STRATEGY_DESCRIPTIONS.items():
            with self.subTest(strategy=strategy):
                self.assertTrue(description.strip())


class DetectRegimeTests(unittest.TestCase):
    def test_sustained_uptrend_is_classified_as_trending_up(self):
        result = detect_regime(steady_uptrend())

        self.assertEqual(result["regime"], "Trending Up")

    def test_returns_all_expected_keys(self):
        result = detect_regime(steady_uptrend())

        for key in (
            "regime",
            "confidence",
            "indicators",
            "recommended_strategies",
            "strategy_descriptions",
            "reasoning",
        ):
            with self.subTest(key=key):
                self.assertIn(key, result)

    def test_regime_is_always_a_known_label(self):
        result = detect_regime(steady_uptrend())

        self.assertIn(result["regime"], REGIME_STRATEGY_MAP)

    def test_confidence_is_clamped_between_30_and_100(self):
        result = detect_regime(steady_uptrend())

        self.assertGreaterEqual(result["confidence"], 30)
        self.assertLessEqual(result["confidence"], 100)

    def test_recommendations_match_the_regime_map(self):
        result = detect_regime(steady_uptrend())

        self.assertEqual(
            result["recommended_strategies"],
            REGIME_STRATEGY_MAP[result["regime"]],
        )

    def test_descriptions_are_provided_for_every_recommendation(self):
        result = detect_regime(steady_uptrend())

        self.assertEqual(
            sorted(result["strategy_descriptions"]),
            sorted(result["recommended_strategies"]),
        )

    def test_indicators_are_json_safe_floats(self):
        indicators = detect_regime(steady_uptrend())["indicators"]

        for name, value in indicators.items():
            with self.subTest(indicator=name):
                self.assertIsInstance(value, float)
                self.assertFalse(np.isnan(value))

    def test_reasoning_is_human_readable_text(self):
        reasoning = detect_regime(steady_uptrend())["reasoning"]

        self.assertIsInstance(reasoning, str)
        self.assertIn("ADX", reasoning)
        self.assertIn("RSI", reasoning)


if __name__ == "__main__":
    unittest.main()
