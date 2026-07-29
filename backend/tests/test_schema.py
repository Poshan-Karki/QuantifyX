import unittest
from datetime import datetime

from pydantic import ValidationError

from schema import BacktestRequest


BASE = {
    "investment": 100_000,
    "sym": "ADBL",
    "stra": "Bollinger Band",
    "startdate": datetime(2024, 1, 1),
}


class BacktestRequestValidationTests(unittest.TestCase):
    """Guards the request boundary. Without these constraints the backtesting
    engine raises deep inside the run and FastAPI surfaces a bare HTTP 500;
    rejecting here turns those into actionable 422 validation messages.
    """

    def test_accepts_a_valid_request(self):
        request = BacktestRequest(**BASE)

        self.assertEqual(request.investment, 100_000)
        self.assertEqual(request.max_pos_pct, 20.0)

    def test_rejects_zero_or_negative_investment(self):
        for amount in (0, -5000):
            with self.subTest(investment=amount):
                with self.assertRaises(ValidationError):
                    BacktestRequest(**{**BASE, "investment": amount})

    def test_rejects_negative_fee_and_slippage(self):
        for field in ("fee_pct", "slippage_pct"):
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    BacktestRequest(**{**BASE, field: -1})

    def test_rejects_position_size_outside_one_to_hundred_percent(self):
        for size in (0, 500):
            with self.subTest(max_pos_pct=size):
                with self.assertRaises(ValidationError):
                    BacktestRequest(**{**BASE, "max_pos_pct": size})

    def test_rejects_negative_cooldown(self):
        with self.assertRaises(ValidationError):
            BacktestRequest(**{**BASE, "cooldown_bars": -1})


if __name__ == "__main__":
    unittest.main()
