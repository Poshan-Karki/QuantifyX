"""Behaviour of the /hmm regime service.

The previous endpoint refit on every request with no fixed seed, so "state 2"
meant something different each call; hardcoded three states; used a volume
feature that is undefined on zero-volume days; and returned Viterbi labels for
the whole history, which are informed by later bars and inflate any backtest
built on them.
"""

import json
import pathlib
import unittest
from dataclasses import replace
from datetime import datetime

import numpy as np
from fastapi import HTTPException

from hmm_service import (
    HIGH_VOLATILITY,
    LOW_VOLATILITY,
    RANGING,
    TRENDING_DOWN,
    TRENDING_UP,
    HmmSettings,
    clear_cache,
    describe_regime,
    fit_regime_model,
    get_regime_model,
)
from main import hmm_learn
from market_regime import REGIME_STRATEGY_MAP, STRATEGY_DESCRIPTIONS
from regime.synthetic import synthetic_ohlcv
from schema import HmmRequest

#: Small enough to keep the suite quick; not what production uses.
FAST = HmmSettings(n_components=(2, 3), covariance_type="diag", n_iter=40, restarts=2)

VOCABULARY = {TRENDING_UP, TRENDING_DOWN, HIGH_VOLATILITY, LOW_VOLATILITY, RANGING}


def frame(n_bars=600, seed=0):
    return synthetic_ohlcv(n_bars=n_bars, seed=seed)


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class FakeDatabase:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def execute(self, query, params):
        self.queries.append((str(query), params))
        return FakeResult(self.rows)


def rows_from(df):
    return [
        (index, row.Open, row.High, row.Low, row.Close, row.Volume)
        for index, row in df.iterrows()
    ]


class ResponseShapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        clear_cache()
        cls.payload = describe_regime("SYNTH", frame(), settings=FAST)

    def test_reports_a_named_regime_not_a_bare_integer(self):
        self.assertIn(self.payload["regime"], VOCABULARY)

    def test_shares_the_keys_regime_endpoint_uses(self):
        """So both endpoints can be rendered by the same component."""
        for key in (
            "regime",
            "confidence",
            "recommended_strategies",
            "strategy_descriptions",
            "reasoning",
        ):
            with self.subTest(key=key):
                self.assertIn(key, self.payload)

    def test_confidence_is_a_probability(self):
        self.assertGreaterEqual(self.payload["confidence"], 0.0)
        self.assertLessEqual(self.payload["confidence"], 1.0)

    def test_next_regime_is_also_named(self):
        self.assertIn(self.payload["next_regime"], VOCABULARY)

    def test_recommended_strategies_come_from_the_shared_map(self):
        self.assertEqual(
            self.payload["recommended_strategies"],
            REGIME_STRATEGY_MAP[self.payload["regime"]],
        )

    def test_every_recommendation_has_a_description(self):
        for name in self.payload["recommended_strategies"]:
            with self.subTest(strategy=name):
                self.assertIn(name, STRATEGY_DESCRIPTIONS)
                self.assertIn(name, self.payload["strategy_descriptions"])

    def test_state_probabilities_form_a_distribution(self):
        self.assertAlmostEqual(sum(self.payload["state_probabilities"]), 1.0, places=2)

    def test_transition_rows_form_distributions(self):
        for row in self.payload["transition_matrix"]:
            with self.subTest(row=row):
                self.assertAlmostEqual(sum(row), 1.0, places=2)

    def test_every_state_is_profiled_with_readable_statistics(self):
        self.assertEqual(len(self.payload["states"]), self.payload["n_states"])
        for profile in self.payload["states"]:
            with self.subTest(state=profile["state"]):
                self.assertIn(profile["label"], VOCABULARY)
                self.assertIn("mean_daily_return_pct", profile)
                self.assertIn("volatility_pct", profile)


class HonestDecodeTests(unittest.TestCase):
    """The current label must agree with the filtered posterior beside it.

    Swapping the forward recursion back for Viterbi would let the reported state
    disagree with those probabilities, because Viterbi maximises the joint path
    rather than the marginal at the final bar.
    """

    def setUp(self):
        clear_cache()

    def test_reported_state_is_the_argmax_of_the_reported_probabilities(self):
        payload = describe_regime("SYNTH", frame(), settings=FAST)

        self.assertEqual(payload["state"], int(np.argmax(payload["state_probabilities"])))

    def test_next_state_is_the_argmax_of_the_next_distribution(self):
        payload = describe_regime("SYNTH", frame(), settings=FAST)

        self.assertEqual(
            payload["next_state"], int(np.argmax(payload["next_state_probabilities"]))
        )

    def test_history_is_labelled_as_filtered(self):
        payload = describe_regime("SYNTH", frame(), settings=FAST)

        self.assertEqual(payload["history"]["decode"], "filtered")

    def test_history_is_bounded_rather_than_the_whole_series(self):
        """The old endpoint returned every bar, so payloads grew without bound."""
        payload = describe_regime("SYNTH", frame(n_bars=900), settings=FAST, history_bars=120)

        self.assertEqual(payload["history"]["bars"], 120)
        self.assertEqual(len(payload["history"]["states"]), 120)

    def test_history_labels_match_their_state_ids(self):
        payload = describe_regime("SYNTH", frame(), settings=FAST)
        profiles = {p["state"]: p["label"] for p in payload["states"]}

        for state, label in zip(payload["history"]["states"], payload["history"]["labels"]):
            with self.subTest(state=state):
                self.assertEqual(label, profiles[state])


class DeterminismTests(unittest.TestCase):
    """State 2 must mean the same thing between calls, which it previously did not."""

    def setUp(self):
        clear_cache()

    def test_two_fits_of_the_same_data_agree(self):
        first = fit_regime_model("SYNTH", frame(), settings=FAST)
        second = fit_regime_model("SYNTH", frame(), settings=FAST)

        self.assertEqual(first.n_states, second.n_states)
        np.testing.assert_array_equal(first.states, second.states)
        self.assertEqual([p.label for p in first.profiles], [p.label for p in second.profiles])

    def test_states_are_ordered_from_most_bearish_to_most_bullish(self):
        """Canonical ordering is what makes the state id stable across refits."""
        model = fit_regime_model("SYNTH", frame(), settings=FAST)
        means = [p.mean_daily_return_pct for p in model.profiles]

        self.assertEqual(means, sorted(means))


class CacheTests(unittest.TestCase):
    def setUp(self):
        clear_cache()

    def test_first_call_fits_and_second_call_is_served_from_cache(self):
        df = frame()

        _, first_cached = get_regime_model("SYNTH", df, settings=FAST)
        _, second_cached = get_regime_model("SYNTH", df, settings=FAST)

        self.assertFalse(first_cached)
        self.assertTrue(second_cached)

    def test_new_data_invalidates_the_cache_rather_than_serving_a_stale_regime(self):
        get_regime_model("SYNTH", frame(n_bars=600), settings=FAST)

        _, cached = get_regime_model("SYNTH", frame(n_bars=601), settings=FAST)

        self.assertFalse(cached)

    def test_different_symbols_do_not_share_an_entry(self):
        get_regime_model("AAA", frame(seed=1), settings=FAST)

        _, cached = get_regime_model("BBB", frame(seed=2), settings=FAST)

        self.assertFalse(cached)

    def test_changed_settings_invalidate_the_cache(self):
        df = frame()
        get_regime_model("SYNTH", df, settings=FAST)

        _, cached = get_regime_model("SYNTH", df, settings=replace(FAST, seed=999))

        self.assertFalse(cached)

    def test_the_response_reports_whether_it_was_cached(self):
        df = frame()

        first = describe_regime("SYNTH", df, settings=FAST)
        second = describe_regime("SYNTH", df, settings=FAST)

        self.assertFalse(first["model"]["cached"])
        self.assertTrue(second["model"]["cached"])


class ShortHistoryTests(unittest.TestCase):
    def setUp(self):
        clear_cache()

    def test_too_few_bars_gives_an_actionable_message(self):
        with self.assertRaises(ValueError) as ctx:
            fit_regime_model("SYNTH", frame(n_bars=100), settings=FAST)

        self.assertIn("at least", str(ctx.exception))


class EndpointTests(unittest.TestCase):
    def setUp(self):
        clear_cache()

    def test_endpoint_returns_a_named_regime(self):
        response = hmm_learn(HmmRequest(sym="synth"), FakeDatabase(rows_from(frame())))

        self.assertEqual(response["status"], "success")
        self.assertIn(response["regime"], VOCABULARY)
        self.assertEqual(response["symbol"], "SYNTH")

    def test_missing_data_returns_404(self):
        """Failures are HTTP status codes, not 200s carrying a "fail" body."""
        with self.assertRaises(HTTPException) as caught:
            hmm_learn(HmmRequest(sym="nope"), FakeDatabase([]))

        self.assertEqual(caught.exception.status_code, 404)

    def test_short_history_returns_422_rather_than_raising_raw(self):
        with self.assertRaises(HTTPException) as caught:
            hmm_learn(HmmRequest(sym="short"), FakeDatabase(rows_from(frame(n_bars=80))))

        self.assertEqual(caught.exception.status_code, 422)
        self.assertIn("at least", caught.exception.detail)

    def test_startdate_is_pushed_into_the_query_rather_than_ignored(self):
        db = FakeDatabase(rows_from(frame()))

        hmm_learn(HmmRequest(sym="synth", startdate=datetime(2019, 1, 1)), db)

        query, params = db.queries[0]
        self.assertIn('"Date" >= :date', query)
        self.assertIn("date", params)

    def test_response_is_json_serialisable(self):
        response = hmm_learn(HmmRequest(sym="synth"), FakeDatabase(rows_from(frame())))

        self.assertIsInstance(json.dumps(response), str)


class ResearchBoundaryTests(unittest.TestCase):
    """The dependency runs app -> regime, never app -> research.

    `regime` holds the inference primitives both sides share: the forward
    recursion, canonical ordering, BIC selection. The API reuses them rather
    than keeping a second copy of the recursion, which is the one piece that
    must not drift.

    `research` is the experiment. Its arms fit on data a live caller has no
    business seeing, so reaching it from a request would reintroduce exactly the
    leak the study exists to measure. It is also gitignored -- a deployed
    checkout does not contain it, so an import would be a hard startup failure,
    not a subtle one.
    """

    APP_MODULES = ("main.py", "hmm_service.py", "market_regime.py", "costs.py")

    def _imports(self, path):
        import ast

        tree = ast.parse(pathlib.Path(path).read_text(encoding="utf-8"))
        return {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }

    def test_app_modules_never_import_the_study(self):
        for filename in self.APP_MODULES:
            with self.subTest(module=filename):
                offenders = {
                    m for m in self._imports(filename) if m == "research" or m.startswith("research.")
                }
                self.assertFalse(offenders, f"{filename} imports {offenders}")

    def test_the_regime_package_never_imports_the_study(self):
        """The inversion this layout exists for.

        regime/ must stand alone: research imports from it, not the reverse.
        If this fails, deleting research/ takes the API down again.
        """
        for path in sorted(pathlib.Path("regime").glob("*.py")):
            with self.subTest(module=path.name):
                offenders = {
                    m for m in self._imports(path) if m == "research" or m.startswith("research.")
                }
                self.assertFalse(offenders, f"{path} imports {offenders}")

    def test_the_service_does_reuse_the_shared_inference_primitives(self):
        """Guards the other direction: a second forward recursion must not appear."""
        self.assertIn("regime.hmm_regime", self._imports("hmm_service.py"))

    def test_the_app_runs_without_the_research_package_present(self):
        """The property that makes research/ safe to gitignore.

        Walks every import in the app modules and asserts none of them would
        fail if research/ were absent from the checkout.
        """
        for filename in self.APP_MODULES:
            for module in self._imports(filename):
                with self.subTest(module=filename, imports=module):
                    self.assertFalse(module.split(".")[0] == "research")


if __name__ == "__main__":
    unittest.main()
