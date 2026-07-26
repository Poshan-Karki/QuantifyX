import unittest
from datetime import date

from market_context import build_contextual_verdict, select_active_context


class MarketContextTests(unittest.TestCase):
    def setUp(self):
        self.as_of = date(2026, 7, 27)
        self.base_entry = {
            "id": "market-1",
            "scope": "MARKET",
            "headline": "Market notice",
            "message": "Reviewed market context.",
            "impact": "HIGH",
            "verdict_label": "CAUTION",
            "verdict_message": "Reduce confidence in the technical result.",
            "published_at": "2026-07-20",
            "expires_at": "2026-08-01",
            "status": "PUBLISHED",
        }

    def test_market_entry_applies_to_every_symbol(self):
        selected = select_active_context([self.base_entry], "NTC", self.as_of)
        self.assertEqual([item["id"] for item in selected], ["market-1"])

    def test_symbol_entry_only_applies_to_matching_symbol(self):
        symbol_entry = {
            **self.base_entry,
            "id": "symbol-1",
            "scope": "SYMBOL",
            "symbol": "NABIL",
        }
        self.assertEqual(
            len(select_active_context([symbol_entry], "NABIL", self.as_of)),
            1,
        )
        self.assertEqual(
            select_active_context([symbol_entry], "NTC", self.as_of),
            [],
        )

    def test_draft_and_expired_entries_are_ignored(self):
        draft = {**self.base_entry, "status": "DRAFT"}
        expired = {**self.base_entry, "expires_at": "2026-07-26"}
        self.assertEqual(
            select_active_context([draft, expired], "NTC", self.as_of),
            [],
        )

    def test_contextual_verdict_preserves_technical_action(self):
        selected = select_active_context([self.base_entry], "NTC", self.as_of)
        verdict = build_contextual_verdict({"action": "BUY"}, selected)
        self.assertEqual(verdict["technical_action"], "BUY")
        self.assertEqual(verdict["label"], "CAUTION")


if __name__ == "__main__":
    unittest.main()
