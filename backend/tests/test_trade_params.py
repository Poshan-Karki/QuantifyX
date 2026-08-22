"""Trade parameters must stay inside the request that supplied them.

main.configure_strategy replaced a version that wrote fee_pct and friends
straight onto the strategy class. Those classes are module-level singletons and
/bbband runs in a threadpool, so the old code let two overlapping requests run
each other's parameters, and left the class permanently off its declared
defaults afterwards.

These tests pin both halves: nothing leaks onto the shared class, and the
parameters still actually reach the backtest.
"""

import math
import unittest
from datetime import datetime, timedelta

from Backtest import BaseStrategy, bollinger_band, macrossover
from main import configure_strategy, run_backtest
from schema import BacktestRequest

TRADE_PARAMS = ("fee_pct", "slippage_pct", "max_pos_pct", "cooldown_bars")


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


def oscillating_rows(size=260):
    """A series that swings far enough to trigger Bollinger entries and exits."""
    start = datetime(2024, 1, 1)
    rows = []
    for index in range(size):
        close = 100 + index * 0.05 + 9 * math.sin(index / 6.0)
        rows.append(
            (
                start + timedelta(days=index),
                close - 0.30,
                close + 0.90,
                close - 0.90,
                close,
                100_000 + index * 100,
            )
        )
    return rows


def request(**overrides):
    settings = dict(
        investment=100_000,
        sym="TEST",
        stra="Bollinger Band",
        startdate=datetime(2024, 1, 1),
        auto_strategy=False,
    )
    settings.update(overrides)
    return BacktestRequest(**settings)


class ConfigureStrategyTests(unittest.TestCase):
    def test_returns_a_subclass_rather_than_the_original(self):
        configured = configure_strategy(bollinger_band, request(fee_pct=1.5))

        self.assertIsNot(configured, bollinger_band)
        self.assertTrue(issubclass(configured, bollinger_band))

    def test_configured_subclass_carries_the_request_values(self):
        configured = configure_strategy(
            bollinger_band,
            request(fee_pct=1.5, slippage_pct=0.7, max_pos_pct=55.0, cooldown_bars=9),
        )

        self.assertEqual(configured.fee_pct, 1.5)
        self.assertEqual(configured.slippage_pct, 0.7)
        self.assertEqual(configured.max_pos_pct, 55.0)
        self.assertEqual(configured.cooldown_bars, 9)

    def test_the_shared_class_gains_no_attributes_of_its_own(self):
        """The precise failure mode of the old code: an own attribute appears."""
        configure_strategy(
            bollinger_band,
            request(fee_pct=1.5, slippage_pct=0.7, max_pos_pct=55.0, cooldown_bars=9),
        )

        for name in TRADE_PARAMS:
            with self.subTest(param=name):
                self.assertNotIn(name, vars(bollinger_band))

    def test_the_shared_class_keeps_its_declared_defaults(self):
        before = {name: getattr(bollinger_band, name) for name in TRADE_PARAMS}

        configure_strategy(bollinger_band, request(fee_pct=9.0, max_pos_pct=99.0))

        for name, value in before.items():
            with self.subTest(param=name):
                self.assertEqual(getattr(bollinger_band, name), value)
                self.assertEqual(getattr(BaseStrategy, name), value)

    def test_two_configurations_of_the_same_class_are_independent(self):
        """This is the interleaving that the old code got wrong."""
        first = configure_strategy(bollinger_band, request(fee_pct=0.2))
        second = configure_strategy(bollinger_band, request(fee_pct=0.8))

        self.assertEqual(first.fee_pct, 0.2)
        self.assertEqual(second.fee_pct, 0.8)

    def test_interleaved_configuration_does_not_cross_contaminate(self):
        """Order of construction against order of use, as a threadpool would."""
        request_a = request(fee_pct=0.2, max_pos_pct=10.0)
        request_b = request(fee_pct=0.8, max_pos_pct=90.0)

        strategy_a = configure_strategy(bollinger_band, request_a)
        strategy_b = configure_strategy(bollinger_band, request_b)
        # B configured last; A must still see its own values.
        self.assertEqual((strategy_a.fee_pct, strategy_a.max_pos_pct), (0.2, 10.0))
        self.assertEqual((strategy_b.fee_pct, strategy_b.max_pos_pct), (0.8, 90.0))

    def test_subclass_keeps_the_original_name_for_readable_output(self):
        configured = configure_strategy(macrossover, request(stra="Moving Average Crossover"))

        self.assertEqual(configured.__name__, macrossover.__name__)

    def test_strategy_specific_attributes_survive_subclassing(self):
        """Indicators and thresholds live on the strategy, not on BaseStrategy."""
        configured = configure_strategy(bollinger_band, request())

        self.assertTrue(hasattr(configured, "init"))
        self.assertTrue(hasattr(configured, "next"))


class RequestIsolationTests(unittest.TestCase):
    """End to end through /bbband, which is the only endpoint that backtests."""

    def test_a_request_leaves_the_shared_class_untouched(self):
        before = {name: getattr(bollinger_band, name) for name in TRADE_PARAMS}

        response = run_backtest(
            request(fee_pct=3.0, slippage_pct=1.2, max_pos_pct=75.0, cooldown_bars=11),
            FakeDatabase(oscillating_rows()),
        )

        self.assertIn("summary", response)
        for name, value in before.items():
            with self.subTest(param=name):
                self.assertEqual(getattr(bollinger_band, name), value)
                self.assertNotIn(name, vars(bollinger_band))

    def test_back_to_back_requests_do_not_inherit_each_others_parameters(self):
        rows = oscillating_rows()

        cheap = run_backtest(request(fee_pct=0.0), FakeDatabase(rows))
        expensive = run_backtest(request(fee_pct=5.0), FakeDatabase(rows))
        cheap_again = run_backtest(request(fee_pct=0.0), FakeDatabase(rows))

        self.assertEqual(
            cheap["summary"]["Final Equity"], cheap_again["summary"]["Final Equity"]
        )
        self.assertNotEqual(
            cheap["summary"]["Final Equity"], expensive["summary"]["Final Equity"]
        )

    def test_higher_fees_reduce_final_equity(self):
        """Guards against the parameters being isolated but never applied."""
        rows = oscillating_rows()

        cheap = run_backtest(request(fee_pct=0.0), FakeDatabase(rows))
        expensive = run_backtest(request(fee_pct=5.0), FakeDatabase(rows))

        self.assertGreater(cheap["summary"]["Total Trades"], 0)
        self.assertLess(
            expensive["summary"]["Final Equity"], cheap["summary"]["Final Equity"]
        )

    def test_auto_strategy_path_also_isolates_parameters(self):
        """configure_strategy runs after auto-selection, so that path needs cover too."""
        before = {name: getattr(bollinger_band, name) for name in TRADE_PARAMS}

        run_backtest(
            request(auto_strategy=True, fee_pct=4.0, max_pos_pct=88.0),
            FakeDatabase(oscillating_rows()),
        )

        for name, value in before.items():
            with self.subTest(param=name):
                self.assertEqual(getattr(bollinger_band, name), value)


if __name__ == "__main__":
    unittest.main()
