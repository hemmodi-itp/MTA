import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.test_creation.semantic_map.tools import (
    apply_user_flow_clusters,
    backlink_source_scenarios,
    build_intent_clusters,
    enrich_relevant_elements,
    score_scenario_relevance,
)


def _intent(intent_id, name, locator_id=None, action="click", expected_result=None):
    return {
        "intent_id": intent_id,
        "intent_name": name,
        "action": action,
        "locator_id": locator_id or f"LOC-{intent_id}",
        "expected_result": expected_result,
    }


LOGIN_INTENTS = [
    _intent("DOM_INT_001", "enter_username"),
    _intent("DOM_INT_002", "enter_password"),
    _intent("DOM_INT_003", "click_forgot_password"),
    _intent("DOM_INT_004", "click_forgot_username"),
    _intent("DOM_INT_005", "click_products"),
    _intent("DOM_INT_006", "click_pricing"),
]


class BuildIntentClustersTests(unittest.TestCase):
    def test_login_intents_cluster_together(self):
        clusters = build_intent_clusters(LOGIN_INTENTS)
        login_cluster = clusters["DOM_INT_001"]
        self.assertEqual(clusters["DOM_INT_002"], login_cluster)
        self.assertEqual(clusters["DOM_INT_003"], login_cluster)
        self.assertEqual(clusters["DOM_INT_004"], login_cluster)

    def test_unrelated_intents_land_in_a_different_cluster(self):
        clusters = build_intent_clusters(LOGIN_INTENTS)
        self.assertNotEqual(clusters["DOM_INT_005"], clusters["DOM_INT_001"])

    def test_no_intent_id_is_skipped_without_error(self):
        intents = LOGIN_INTENTS + [{"intent_name": "no_id_here"}]
        clusters = build_intent_clusters(intents)
        self.assertEqual(len(clusters), len(LOGIN_INTENTS))


class ApplyUserFlowClustersTests(unittest.TestCase):
    def test_flow_overrides_keyword_cluster_across_unrelated_intents(self):
        base_clusters = build_intent_clusters(LOGIN_INTENTS)
        # A recorded flow: sign in -> search -> add to cart touches an
        # otherwise-unrelated login intent and a products intent together.
        flows = [{
            "flow_id": "FLOW-001",
            "inferred_name": "sign_in_and_search",
            "steps": [
                {"locator_id": "LOC-DOM_INT_001", "action": "fill"},
                {"locator_id": "LOC-DOM_INT_005", "action": "click"},
            ],
        }]
        intent_id_by_locator = {i["locator_id"]: i["intent_id"] for i in LOGIN_INTENTS}
        updated = apply_user_flow_clusters(base_clusters, flows, intent_id_by_locator)
        self.assertEqual(updated["DOM_INT_001"], updated["DOM_INT_005"])
        self.assertTrue(updated["DOM_INT_001"].startswith("flow:"))

    def test_single_step_flow_is_not_a_cluster(self):
        base_clusters = build_intent_clusters(LOGIN_INTENTS)
        flows = [{"flow_id": "FLOW-002", "steps": [{"locator_id": "LOC-DOM_INT_005"}]}]
        intent_id_by_locator = {i["locator_id"]: i["intent_id"] for i in LOGIN_INTENTS}
        updated = apply_user_flow_clusters(base_clusters, flows, intent_id_by_locator)
        self.assertEqual(updated, base_clusters)


class ScoreScenarioRelevanceTests(unittest.TestCase):
    def test_products_scenario_boosts_whole_cluster_via_brd_traceability(self):
        clusters = build_intent_clusters(LOGIN_INTENTS)
        scenario = {
            "title": "Browse products",
            "business_objective": "Let users find products",
            "steps": ["User clicks products navigation"],
            "traceability": [{"section": "Products overview", "requirement_id": "REQ-010"}],
        }
        scores = score_scenario_relevance(scenario, LOGIN_INTENTS, clusters)
        self.assertIn("DOM_INT_005", scores)
        # DOM_INT_006 (pricing) shares no token with "products" directly —
        # confirm it's untouched unless clustered with a direct match.
        if clusters["DOM_INT_006"] == clusters["DOM_INT_005"]:
            self.assertIn("DOM_INT_006", scores)

    def test_login_scenario_scores_the_whole_login_cluster(self):
        clusters = build_intent_clusters(LOGIN_INTENTS)
        scenario = {
            "title": "Test login functionality",
            "business_objective": "User logs in with username and password",
            "steps": ["Enter username", "Enter password"],
            "traceability": [],
        }
        scores = score_scenario_relevance(scenario, LOGIN_INTENTS, clusters)
        for iid in ("DOM_INT_001", "DOM_INT_002", "DOM_INT_003", "DOM_INT_004"):
            self.assertIn(iid, scores, f"{iid} should be pulled in by the login cluster boost")
        self.assertNotIn("DOM_INT_006", scores)

    def test_no_overlap_yields_empty_scores(self):
        clusters = build_intent_clusters(LOGIN_INTENTS)
        scenario = {"title": "zzz qqq xyz", "steps": [], "traceability": []}
        scores = score_scenario_relevance(scenario, LOGIN_INTENTS, clusters)
        self.assertEqual(scores, {})


class EnrichRelevantElementsTests(unittest.TestCase):
    def test_attaches_intent_fields_by_locator_id(self):
        intent = _intent("DOM_INT_001", "enter_username", locator_id="LOC-0001",
                          action="fill", expected_result="username_entered")
        intents_by_locator = {"LOC-0001": intent}
        clusters = {"DOM_INT_001": "login"}
        confidences = {"DOM_INT_001": 0.9}
        result = enrich_relevant_elements(
            [{"locator_id": "LOC-0001", "playwright_expr": "x", "relevance": "y"}],
            intents_by_locator, clusters, confidences,
        )
        self.assertEqual(result[0]["intent_id"], "DOM_INT_001")
        self.assertEqual(result[0]["action"], "fill")
        self.assertEqual(result[0]["expected_result"], "username_entered")
        self.assertEqual(result[0]["cluster"], "login")
        self.assertEqual(result[0]["confidence"], 0.9)

    def test_unmatched_locator_passes_through_unchanged(self):
        result = enrich_relevant_elements(
            [{"locator_id": "LOC-9999", "playwright_expr": "x", "relevance": "y"}],
            {}, {}, {},
        )
        self.assertNotIn("intent_id", result[0])
        self.assertEqual(result[0]["locator_id"], "LOC-9999")


class BacklinkSourceScenariosTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "intents.yaml")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, intents):
        import yaml
        with open(self.path, "w", encoding="utf-8") as f:
            yaml.dump({"project": "p", "intents": intents}, f)

    def _read(self):
        import yaml
        with open(self.path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_populates_source_scenarios_for_matching_module_only(self):
        self._write([
            {"intent_id": "DOM_INT_001", "module_id": "M01", "source_scenarios": []},
            {"intent_id": "DOM_INT_001", "module_id": "M02", "source_scenarios": []},
        ])
        changed = backlink_source_scenarios(self.path, "M01", {"M01_BS_001": ["DOM_INT_001"]})
        self.assertTrue(changed)
        data = self._read()
        m01 = next(i for i in data["intents"] if i["module_id"] == "M01")
        m02 = next(i for i in data["intents"] if i["module_id"] == "M02")
        self.assertEqual(m01["source_scenarios"], ["M01_BS_001"])
        self.assertEqual(m02["source_scenarios"], [])

    def test_returns_false_and_writes_nothing_when_already_up_to_date(self):
        self._write([
            {"intent_id": "DOM_INT_001", "module_id": "M01", "source_scenarios": ["M01_BS_001"]},
        ])
        changed = backlink_source_scenarios(self.path, "M01", {"M01_BS_001": ["DOM_INT_001"]})
        self.assertFalse(changed)

    def test_missing_file_returns_false(self):
        changed = backlink_source_scenarios(
            os.path.join(self.tmp, "nope.yaml"), "M01", {"M01_BS_001": ["DOM_INT_001"]}
        )
        self.assertFalse(changed)


if __name__ == "__main__":
    unittest.main()
