"""The HTTP contract, exercised through the real app.

The other suites call handlers as plain functions, which is fast but cannot see
routing, dependency wiring, status codes or rate limiting. Every endpoint used
to answer 200 with {"status": "fail"} in the body; these tests pin the codes so
that cannot quietly come back.

The database is replaced with a fake session, so nothing here connects anywhere.
"""

import math
import os
import unittest
from datetime import datetime, timedelta

os.environ.setdefault("RATE_LIMIT_ENABLED", "0")

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import ratelimit  # noqa: E402
from costs import DEFAULT_TRADE_PARAMS  # noqa: E402


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeDatabase:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, _query, _params=None):
        return FakeResult(self.rows)


def oscillating_rows(size=260):
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


def client_with(rows):
    main.app.dependency_overrides[main.get_db] = lambda: FakeDatabase(rows)
    return TestClient(main.app)


class ContractTests(unittest.TestCase):
    def setUp(self):
        ratelimit._ENABLED = False
        main._symbol_cache["day"] = None
        main._symbol_cache["symbols"] = None

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_root_is_alive(self):
        with client_with([]) as client:
            self.assertEqual(client.get("/").status_code, 200)

    def test_defaults_match_the_backend_declaration(self):
        with client_with([]) as client:
            response = client.get("/defaults")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), DEFAULT_TRADE_PARAMS)

    def test_missing_symbols_is_404_not_200(self):
        with client_with([]) as client:
            response = client.get("/hydroname")

        self.assertEqual(response.status_code, 404)
        self.assertIn("detail", response.json())

    def test_symbol_list_is_a_list(self):
        with client_with([("NTC",), ("GBIME",)]) as client:
            response = client.get("/hydroname")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [{"Symbol": "NTC"}, {"Symbol": "GBIME"}])

    def test_candles_moved_to_a_get_route(self):
        # This route selects Symbol first and Date last, unlike the backtest query.
        rows = [
            ("NTC", 100.0, 101.0, 99.0, 100.5, 1000.0, datetime(2024, 1, 1)),
            ("NTC", 100.5, 102.0, 100.0, 101.5, 1200.0, datetime(2024, 1, 2)),
        ]
        with client_with(rows) as client:
            response = client.get("/symbols/NTC/candles")
            self.assertEqual(response.status_code, 200)
            # Title-cased consistently; "low" used to come back lowercase.
            self.assertIn("Low", response.json()[0])
            self.assertNotIn("low", response.json()[0])

            # The old POST /gethydro is gone.
            self.assertEqual(client.post("/gethydro?sym=NTC").status_code, 404)

    def test_regime_rejects_a_window_too_short_to_classify(self):
        """This combination used to raise IndexError and return a bare 500."""
        with client_with(oscillating_rows(25)) as client:
            response = client.post(
                "/regime", json={"sym": "NTC", "startdate": "2024-01-01T00:00:00"}
            )

        self.assertEqual(response.status_code, 422)
        self.assertIn("at least", response.json()["detail"])

    def test_regime_no_longer_demands_investment_and_strategy(self):
        with client_with(oscillating_rows()) as client:
            response = client.post(
                "/regime", json={"sym": "NTC", "startdate": "2024-01-01T00:00:00"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("regime", response.json())

    def test_backtest_reports_the_costs_it_charged(self):
        with client_with(oscillating_rows()) as client:
            response = client.post(
                "/bbband",
                json={
                    "investment": 100000,
                    "sym": "NTC",
                    "stra": "Bollinger Band",
                    "startdate": "2024-01-01T00:00:00",
                    "fee_pct": 0.25,
                    "slippage_pct": 0.15,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertAlmostEqual(response.json()["costs"]["total_cost_pct"], 0.40, places=6)

    def test_invalid_investment_is_a_422_with_a_usable_detail(self):
        with client_with(oscillating_rows()) as client:
            response = client.post(
                "/bbband",
                json={
                    "investment": -5,
                    "sym": "NTC",
                    "stra": "Bollinger Band",
                    "startdate": "2024-01-01T00:00:00",
                },
            )

        self.assertEqual(response.status_code, 422)
        self.assertIsInstance(response.json()["detail"], list)

    def test_missing_data_is_404(self):
        with client_with([]) as client:
            response = client.post(
                "/bbband",
                json={
                    "investment": 100000,
                    "sym": "ZZZZ",
                    "stra": "Bollinger Band",
                    "startdate": "2024-01-01T00:00:00",
                },
            )

        self.assertEqual(response.status_code, 404)


class RateLimitTests(unittest.TestCase):
    def tearDown(self):
        ratelimit._ENABLED = False
        main.app.dependency_overrides.clear()

    def test_the_expensive_endpoint_starts_refusing(self):
        ratelimit._ENABLED = True
        ratelimit._storage.reset()

        with client_with([]) as client:
            statuses = [
                client.post("/hmm", json={"sym": "NTC"}).status_code for _ in range(12)
            ]

        # /hmm is capped at 10/minute; the data is empty so allowed calls 404.
        self.assertIn(429, statuses)
        self.assertEqual(statuses.count(404), 10)

    def test_limiting_can_be_switched_off(self):
        ratelimit._ENABLED = False

        with client_with([]) as client:
            statuses = [
                client.post("/hmm", json={"sym": "NTC"}).status_code for _ in range(12)
            ]

        self.assertNotIn(429, statuses)


if __name__ == "__main__":
    unittest.main()
