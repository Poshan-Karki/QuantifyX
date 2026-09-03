"""Trade parameters must stay inside the request that supplied them, and cost
parameters must actually cost something.

main.configure_strategy replaced a version that wrote parameters straight onto
the strategy class. Those classes are module-level singletons and /bbband runs
in a threadpool, so the old code let two overlapping requests run each other's
parameters, and left the class permanently off its declared defaults afterwards.

The second half of this file pins the execution model. Slippage used to be
expressed as a limit price above the market, which backtesting.py fills at
min(open, limit) -- a cap that can only improve the fill. At slippage 0 entries
filled *below* the bar's open, dodging every gap up; at high slippage they
filled exactly at the open with no penalty; and widening the cap changed which
orders filled at all. Fees and slippage are now charged together as commission.
"""

import math
import unittest
from datetime import datetime, timedelta

from fastapi import HTTPException

from Backtest import BaseStrategy, bollinger_band, macrossover
from costs import commission_fraction, total_cost_pct
from main import configure_strategy, run_backtest
from schema import BacktestRequest

#: The parameters that legitimately live on the strategy class. Fees and
#: slippage are deliberately absent -- they are charged as commission on the
#: Backtest constructor, so putting them here would be dead weight that reads
#: like costs are applied twice.
TRADE_PARAMS = ("max_pos_pct", "cooldown_bars")
COST_PARAMS = ("fee_pct", "slippage_pct")


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


def gapping_rows(size=260):
    """Like oscillating_rows, but every bar opens above the previous close.

    The gap is what exposed the old limit-order entry: a limit set just above
    yesterday's close fills at min(open, limit), so a gap up filled below the
    open at a price no real order could have reached.
    """
    start = datetime(2024, 1, 1)
    rows = []
    previous_close = None
    for index in range(size):
        close = 100 + index * 0.05 + 9 * math.sin(index / 6.0)
        open_price = (previous_close * 1.03) if previous_close is not None else close
        high = max(open_price, close) + 0.90
        low = min(open_price, close) - 0.90
        rows.append((start + timedelta(days=index), open_price, high, low, close, 100_000 + index * 100))
        previous_close = close
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
        configured = configure_strategy(bollinger_band, request(max_pos_pct=55.0))

        self.assertIsNot(configured, bollinger_band)
        self.assertTrue(issubclass(configured, bollinger_band))

    def test_configured_subclass_carries_the_request_values(self):
        configured = configure_strategy(
            bollinger_band,
            request(max_pos_pct=55.0, cooldown_bars=9),
        )

        self.assertEqual(configured.max_pos_pct, 55.0)
        self.assertEqual(configured.cooldown_bars, 9)

    def test_cost_parameters_do_not_live_on_the_strategy(self):
        """They are charged as commission; a copy here would be dead weight."""
        configured = configure_strategy(
            bollinger_band,
            request(fee_pct=1.5, slippage_pct=0.7),
        )

        for name in COST_PARAMS:
            with self.subTest(param=name):
                self.assertFalse(hasattr(configured, name))
                self.assertFalse(hasattr(BaseStrategy, name))

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
        first = configure_strategy(bollinger_band, request(max_pos_pct=10.0))
        second = configure_strategy(bollinger_band, request(max_pos_pct=90.0))

        self.assertEqual(first.max_pos_pct, 10.0)
        self.assertEqual(second.max_pos_pct, 90.0)

    def test_interleaved_configuration_does_not_cross_contaminate(self):
        """Order of construction against order of use, as a threadpool would."""
        request_a = request(cooldown_bars=1, max_pos_pct=10.0)
        request_b = request(cooldown_bars=8, max_pos_pct=90.0)

        strategy_a = configure_strategy(bollinger_band, request_a)
        strategy_b = configure_strategy(bollinger_band, request_b)
        # B configured last; A must still see its own values.
        self.assertEqual((strategy_a.cooldown_bars, strategy_a.max_pos_pct), (1, 10.0))
        self.assertEqual((strategy_b.cooldown_bars, strategy_b.max_pos_pct), (8, 90.0))

    def test_subclass_keeps_the_original_name_for_readable_output(self):
        configured = configure_strategy(macrossover, request(stra="Moving Average Crossover"))

        self.assertEqual(configured.__name__, macrossover.__name__)

    def test_strategy_specific_attributes_survive_subclassing(self):
        """Indicators and thresholds live on the strategy, not on BaseStrategy."""
        configured = configure_strategy(bollinger_band, request())

        self.assertTrue(hasattr(configured, "init"))
        self.assertTrue(hasattr(configured, "next"))


class CostModelTests(unittest.TestCase):
    """Fees and slippage combine into one round-trip commission."""

    def test_costs_add(self):
        self.assertAlmostEqual(total_cost_pct(0.2, 0.1), 0.3)
        self.assertAlmostEqual(commission_fraction(0.2, 0.1), 0.003)

    def test_zero_costs_are_allowed(self):
        self.assertEqual(total_cost_pct(0.0, 0.0), 0.0)

    def test_absurd_combined_cost_is_rejected(self):
        with self.assertRaises(ValueError):
            total_cost_pct(60.0, 10.0)


class ExecutionModelTests(unittest.TestCase):
    """The half of the old code that quietly flattered every result."""

    def test_entries_never_fill_below_the_bar_open(self):
        """A fill below the open is a price no order could have obtained.

        The old limit-order entry produced exactly that on gap ups.
        """
        response = run_backtest(
            request(slippage_pct=0.0, fee_pct=0.0, cooldown_bars=0),
            FakeDatabase(gapping_rows()),
        )

        self.assertGreater(response["summary"]["Total Trades"], 0)
        opens = {row["time"]: row["open"] for row in response["ohlc"]}
        for trade in response["trades"]:
            with self.subTest(entry=trade["EntryTime"]):
                bar_open = opens[trade["EntryTime"]]
                self.assertGreaterEqual(trade["EntryPrice"], bar_open - 1e-9)

    def test_slippage_costs_money(self):
        rows = oscillating_rows()

        free = run_backtest(request(fee_pct=0.0, slippage_pct=0.0), FakeDatabase(rows))
        slipped = run_backtest(request(fee_pct=0.0, slippage_pct=2.0), FakeDatabase(rows))

        self.assertGreater(free["summary"]["Total Trades"], 0)
        self.assertLess(
            slipped["summary"]["Final Equity"], free["summary"]["Final Equity"]
        )

    def test_slippage_does_not_change_which_trades_happen(self):
        """The old cap changed fill eligibility, so the trade set moved with it."""
        rows = oscillating_rows()

        free = run_backtest(request(fee_pct=0.0, slippage_pct=0.0), FakeDatabase(rows))
        slipped = run_backtest(request(fee_pct=0.0, slippage_pct=2.0), FakeDatabase(rows))

        self.assertEqual(
            free["summary"]["Total Trades"], slipped["summary"]["Total Trades"]
        )
        self.assertEqual(
            [t["EntryTime"] for t in free["trades"]],
            [t["EntryTime"] for t in slipped["trades"]],
        )

    def test_fee_and_slippage_are_interchangeable_as_cost(self):
        """Both are charged the same way, so equal totals must price the same."""
        rows = oscillating_rows()

        as_fee = run_backtest(request(fee_pct=1.0, slippage_pct=0.0), FakeDatabase(rows))
        as_slippage = run_backtest(request(fee_pct=0.0, slippage_pct=1.0), FakeDatabase(rows))

        self.assertAlmostEqual(
            as_fee["summary"]["Final Equity"],
            as_slippage["summary"]["Final Equity"],
            places=6,
        )

    def test_reported_costs_describe_what_was_charged(self):
        response = run_backtest(
            request(fee_pct=0.25, slippage_pct=0.15), FakeDatabase(oscillating_rows())
        )

        self.assertAlmostEqual(response["costs"]["total_cost_pct"], 0.40, places=6)
        self.assertEqual(response["costs"]["fee_pct"], 0.25)
        self.assertEqual(response["costs"]["slippage_pct"], 0.15)


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

    def test_missing_data_returns_404(self):
        with self.assertRaises(HTTPException) as caught:
            run_backtest(request(), FakeDatabase([]))

        self.assertEqual(caught.exception.status_code, 404)

    def test_unknown_strategy_returns_422(self):
        with self.assertRaises(HTTPException) as caught:
            run_backtest(request(stra="Astrology"), FakeDatabase(oscillating_rows()))

        self.assertEqual(caught.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
