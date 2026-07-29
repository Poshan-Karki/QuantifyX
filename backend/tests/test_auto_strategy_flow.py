import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from main import run_backtest
from schema import BacktestRequest


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class FakeDatabase:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, _query, _params):
        return FakeResult(self.rows)


class AutoStrategyFlowTests(unittest.TestCase):
    @staticmethod
    def market_rows(size=200):
        start = datetime(2024, 1, 1)
        rows = []
        for index in range(size):
            close = 100 + index * 0.25 + ((index % 10) - 5) * 0.15
            rows.append(
                (
                    start + timedelta(days=index),
                    close - 0.25,
                    close + 0.75,
                    close - 0.75,
                    close,
                    100_000 + index * 100,
                )
            )
        return rows

    @staticmethod
    def trending_regime(_df):
        return {
            "regime": "Trending Up",
            "confidence": 80,
            "indicators": {},
            "recommended_strategies": ["Moving Average Crossover"],
            "strategy_descriptions": {},
            "reasoning": "Test regime",
        }

    @patch("main.detect_regime")
    def test_auto_strategy_selects_on_training_and_backtests_only_holdout(
        self, detect_regime
    ):
        detect_regime.side_effect = self.trending_regime
        request = BacktestRequest(
            investment=100_000,
            sym="TEST",
            stra="Bollinger Band",
            startdate=datetime(2024, 1, 1),
            auto_strategy=True,
        )

        response = run_backtest(request, FakeDatabase(self.market_rows()))

        self.assertEqual(
            [len(call.args[0]) for call in detect_regime.call_args_list],
            [200, 140],
        )
        self.assertEqual(response["evaluation"]["mode"], "out_of_sample")
        self.assertEqual(
            response["evaluation"]["selected_strategy"],
            "Moving Average Crossover",
        )
        self.assertEqual(response["evaluation"]["training_period"]["bars"], 140)
        self.assertEqual(response["evaluation"]["evaluation_period"]["bars"], 60)
        self.assertEqual(len(response["ohlc"]), 60)
        self.assertEqual(response["ohlc"][0]["time"], "2024-05-20")


if __name__ == "__main__":
    unittest.main()
