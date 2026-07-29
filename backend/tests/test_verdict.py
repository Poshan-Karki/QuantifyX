import unittest

from verdict import generate_verdict


class GenerateVerdictTests(unittest.TestCase):
    @staticmethod
    def stats(ret=0.0, win_rate=0.0, n_trades=0, dd=0.0):
        return {
            "Return [%]": ret,
            "Win Rate [%]": win_rate,
            "# Trades": n_trades,
            "Max. Drawdown [%]": dd,
        }

    def test_no_trades_results_in_hold(self):
        result = generate_verdict(self.stats(n_trades=0), "Bollinger Band")

        self.assertEqual(result["action"], "HOLD")
        self.assertIn("no trade signals", result["message"])

    def test_strong_return_and_win_rate_results_in_buy(self):
        result = generate_verdict(
            self.stats(ret=12.0, win_rate=60.0, n_trades=10), "Bollinger Band"
        )

        self.assertEqual(result["action"], "BUY")
        self.assertIn("12.0%", result["message"])

    def test_negative_return_results_in_avoid(self):
        result = generate_verdict(
            self.stats(ret=-8.0, win_rate=30.0, n_trades=10, dd=15.0), "Bollinger Band"
        )

        self.assertEqual(result["action"], "AVOID")
        self.assertIn("8.0%", result["message"])

    def test_mixed_result_falls_back_to_hold_caution(self):
        result = generate_verdict(
            self.stats(ret=2.0, win_rate=40.0, n_trades=10), "Bollinger Band"
        )

        self.assertEqual(result["action"], "HOLD/CAUTION")

    def test_high_return_with_low_win_rate_is_not_buy(self):
        result = generate_verdict(
            self.stats(ret=12.0, win_rate=20.0, n_trades=10), "Bollinger Band"
        )

        self.assertNotEqual(result["action"], "BUY")

    def test_appends_regime_note_when_strategy_not_recommended(self):
        regime_data = {
            "regime": "Trending Up",
            "recommended_strategies": ["MACD Cross", "ATR Breakout"],
        }

        result = generate_verdict(
            self.stats(ret=12.0, win_rate=60.0, n_trades=10),
            "Bollinger Band",
            regime_data,
        )

        self.assertIn("Trending Up", result["message"])
        self.assertIn("MACD Cross", result["message"])

    def test_small_sample_caution_appended_below_ten_trades(self):
        result = generate_verdict(
            self.stats(ret=12.0, win_rate=100.0, n_trades=2), "Bollinger Band"
        )

        self.assertIn("only 2 trades", result["message"])

    def test_small_sample_caution_uses_singular_for_one_trade(self):
        result = generate_verdict(
            self.stats(ret=12.0, win_rate=100.0, n_trades=1), "Bollinger Band"
        )

        self.assertIn("only 1 trade ", result["message"])

    def test_no_small_sample_caution_at_ten_or_more_trades(self):
        result = generate_verdict(
            self.stats(ret=12.0, win_rate=60.0, n_trades=10), "Bollinger Band"
        )

        self.assertNotIn("Caution:", result["message"])

    def test_no_small_sample_caution_when_zero_trades(self):
        result = generate_verdict(self.stats(n_trades=0), "Bollinger Band")

        self.assertNotIn("Caution:", result["message"])

    def test_no_regime_note_when_strategy_is_recommended(self):
        regime_data = {
            "regime": "Low Volatility",
            "recommended_strategies": ["Bollinger Band", "Mean Reversion"],
        }

        result = generate_verdict(
            self.stats(ret=12.0, win_rate=60.0, n_trades=10),
            "Bollinger Band",
            regime_data,
        )

        self.assertNotIn("Note:", result["message"])


if __name__ == "__main__":
    unittest.main()
