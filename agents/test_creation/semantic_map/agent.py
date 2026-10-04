"""
SemanticMapAgent — clusters each module's DOM intents into functional buckets
(login, search, checkout, ...) and maps each business scenario to its
relevant intents/elements, boosting a whole cluster's priority when a
scenario touches that functional area.

Runs ONE LLM call covering all scenarios at once (element-relevance pass),
plus deterministic Python clustering/confidence-scoring on top — no second
LLM round-trip. Prevents dumping all 63+ DOM elements into every
ScriptGenerationAgent call.

Failure routing (via BaseAgent.execute_with_fallback):
    Tier 0 — primary LLM (_run_primary)
    Tier 1 — NSHTTPConnector (_run_ns_fallback)
    Tier 2 — keyword-overlap Python fallback (_run_py_fallback → fallback_core)

Output: test_creation/scenario_element_map.json — each relevant_elements entry
now also carries intent_id/action/expected_result/cluster/confidence when a
module-scoped comprehension/.../dom_intents.json is available (BRD-only
projects have none, so this enrichment is a graceful no-op there).
"""

import json
import os
from typing import Any, Dict, List, Optional

from agents.base_agent import BaseAgent
from agents.test_creation.semantic_map.prompt import SEMANTIC_MAP_PROMPT
from agents.test_creation.semantic_map.tools import (
    apply_user_flow_clusters,
    backlink_source_scenarios,
    build_element_summary,
    build_intent_clusters,
    build_locator_map,
    enrich_relevant_elements,
    score_scenario_relevance,
)
from connectors.connector_registry import ConnectorRegistry
from tools.constants import PROJECTS_BASE as _ASSETS_BASE
from tools.discovery.dom_intents import load_dom_intents
from tools.discovery.paths import comprehension_scan_dir
from tools.shared import get_logger
from tools.shared.llm_response_validator import parse_llm_json


class SemanticMapAgent(BaseAgent):
    MODULE_NAME = "semantic_map"

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self.registry = ConnectorRegistry(self.settings)
        self.logger = get_logger("agent.semantic_map")

    # ── Public entry point ────────────────────────────────────────────────────

    def execute(self, request: dict, state: dict) -> Dict:
        return self.execute_with_fallback(request, state)

    # ── Tier 0 — primary LLM ─────────────────────────────────────────────────

    def _run_primary(self, request: dict, state: dict) -> Dict:
        llm = self.registry.get_llm(request.get("connector_mode"))
        return self._llm_map(request, state, llm=llm)

    # ── Tier 1 — NSHTTPConnector ──────────────────────────────────────────────

    def _run_ns_fallback(self, request: dict, state: dict) -> Dict:
        ns = self.registry.get_ns()
        project_name = request.get("project_name") or request.get("message", "project")
        self._log(f"Routing to NSHTTPConnector — project='{project_name}'")
        result = ns.call("semantic_map_agent", {"project_name": project_name})
        if "module" not in result:
            result["module"] = "semantic_map"
        if "status" not in result:
            result["status"] = "success"
        return result

    # ── Tier 1b — alternate (lighter) model ───────────────────────────────────

    def _run_with_alt_model(self, model: str, request: dict, state: dict) -> Dict:
        self._log(f"Switching to alt model: {model}")
        try:
            from connectors.llm.claude import ClaudeConnector
            alt_llm = ClaudeConnector(model=model)
        except TypeError:
            alt_llm = self.registry.get_llm("external")
        return self._llm_map(request, state, llm=alt_llm)

    # ── Tier 2 — Python deterministic fallback ────────────────────────────────

    def _run_py_fallback(self, request: dict, state: dict) -> Dict:
        from agents.common import fallback_core

        project_name = request.get("project_name") or request.get("message", "project")
        safe = _safe_name(project_name)
        comprehension_dir = os.path.join(_ASSETS_BASE, safe, "test_comprehension")
        output_dir = os.path.join(_ASSETS_BASE, safe, "test_creation")
        dom_dir = comprehension_scan_dir(comprehension_dir, request.get("module_filter"))
        dom_path = os.path.join(dom_dir, "dom_elements.json")
        scenarios_path = os.path.join(comprehension_dir, "business_scenarios.json")

        self._log("Python fallback — keyword-overlap semantic mapping")

        scenarios = _load_scenarios(scenarios_path)
        elements = _load_dom_elements(dom_path)

        if not scenarios:
            from agents.common.failure_classifier import MissingInputError
            raise MissingInputError(
                f"business_scenarios.json not found or empty: {scenarios_path}"
            )

        scenario_map = fallback_core.fallback_semantic_map(scenarios, elements)
        scenario_map = self._enrich_with_intents(
            scenario_map, scenarios, safe, request.get("module_filter"), comprehension_dir,
        )
        out_path = _write_map(scenario_map, output_dir)

        return {
            "module": "semantic_map",
            "status": "degraded",
            "project": project_name,
            "scenarios_mapped": len(scenario_map),
            "fallback": True,
            "output": out_path,
        }

    # ── Core LLM logic ────────────────────────────────────────────────────────

    def _llm_map(self, request: dict, state: dict, llm) -> Dict:
        project_name = (
            request.get("project_name") or request.get("message", "project")
        )
        safe = _safe_name(project_name)
        comprehension_dir = os.path.join(_ASSETS_BASE, safe, "test_comprehension")
        output_dir = os.path.join(_ASSETS_BASE, safe, "test_creation")
        dom_dir = comprehension_scan_dir(comprehension_dir, request.get("module_filter"))
        dom_path = os.path.join(dom_dir, "dom_elements.json")
        scenarios_path = os.path.join(comprehension_dir, "business_scenarios.json")

        self._log(f"Starting — project='{project_name}'")

        # Fail fast if required inputs are missing
        for path, label in [(scenarios_path, "business_scenarios.json"), (dom_path, "dom_elements.json")]:
            if not os.path.exists(path):
                from agents.common.failure_classifier import MissingInputError
                raise MissingInputError(f"{label} not found: {path}")

        scenarios = _load_scenarios(scenarios_path)
        elements = build_element_summary(dom_path)

        self._log(
            f"Loaded {len(scenarios)} scenario(s) + {len(elements)} element(s) → "
            f"sending 1 LLM call"
        )

        prompt = SEMANTIC_MAP_PROMPT.safe_substitute(
            scenarios_json=json.dumps(scenarios, ensure_ascii=False, indent=2),
            elements_json=json.dumps(elements, ensure_ascii=False, indent=2),
        )

        raw = llm.generate(prompt)
        scenario_map = _parse_map_response(raw)

        # Enrich with playwright_expr from the locator map (authoritative source)
        locator_map = build_locator_map(dom_path)
        scenario_map = _enrich_locator_exprs(scenario_map, locator_map)

        scenario_map = self._enrich_with_intents(
            scenario_map, scenarios, safe, request.get("module_filter"), comprehension_dir,
        )

        out_path = _write_map(scenario_map, output_dir)
        self._log(
            f"Mapped {len(scenario_map)} scenario(s) → {out_path}"
        )

        return {
            "module": "semantic_map",
            "status": "success",
            "project": project_name,
            "scenarios_mapped": len(scenario_map),
            "output": out_path,
        }

    # ── Intent clustering / confidence / source_scenarios backlink ─────────────

    def _enrich_with_intents(
        self,
        scenario_map: Dict[str, Any],
        scenarios: List[Dict[str, Any]],
        safe: str,
        module_id: Optional[str],
        comprehension_dir: str,
    ) -> Dict[str, Any]:
        """
        Attach intent-level richness (action/expected_result/cluster/
        confidence) to every relevant_elements entry, and backlink each
        matched intent's source_scenarios in intents.yaml — for both the
        LLM tier and the Python fallback tier, so neither leaves this
        richness on the table.

        Graceful no-op when this module has no dom_intents.json (BRD-only
        projects, or a module discovery hasn't scanned yet) — every reader
        below already tolerates an empty list/dict.
        """
        dom_intents = load_dom_intents(safe, module_id)
        if not dom_intents:
            return scenario_map

        clusters = build_intent_clusters(dom_intents)

        user_flows = _load_user_flows(comprehension_dir, module_id)
        if user_flows:
            intent_id_by_locator = {
                i["locator_id"]: i["intent_id"] for i in dom_intents if i.get("locator_id")
            }
            clusters = apply_user_flow_clusters(clusters, user_flows, intent_id_by_locator)

        intents_by_locator = {
            i["locator_id"]: i for i in dom_intents if i.get("locator_id")
        }
        scenarios_by_id = {s.get("scenario_id"): s for s in scenarios}

        scenario_to_intent_ids: Dict[str, List[str]] = {}
        for sid, data in scenario_map.items():
            scenario = scenarios_by_id.get(sid, {})
            confidences = score_scenario_relevance(scenario, dom_intents, clusters)
            relevant_elements = data.get("relevant_elements", [])
            enriched = enrich_relevant_elements(
                relevant_elements, intents_by_locator, clusters, confidences,
            )
            data["relevant_elements"] = enriched
            matched = [el["intent_id"] for el in enriched if el.get("intent_id")]
            if matched:
                scenario_to_intent_ids[sid] = matched

        intents_yaml_path = os.path.join(_ASSETS_BASE, safe, "test_creation", "intents.yaml")
        if backlink_source_scenarios(intents_yaml_path, module_id, scenario_to_intent_ids):
            self._log(
                f"  Backlinked source_scenarios for module '{module_id}' in intents.yaml"
            )

        return scenario_map


# ── Module helpers ─────────────────────────────────────────────────────────────

def _safe_name(name: str) -> str:
    sanitised = "".join(
        c if (c.isalnum() or c in "-_") else "_" for c in name
    ).strip("_")
    return sanitised or "project"


def _load_scenarios(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    # Support both {scenarios: [...]} and flat list
    if isinstance(raw, dict):
        raw = raw.get("scenarios", raw.get("business_scenarios", []))
    return raw if isinstance(raw, list) else []


def _load_dom_elements(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, dict) and raw.get("pages"):
        return [el for page in raw["pages"] for el in page.get("elements", [])]
    if isinstance(raw, dict):
        return raw.get("elements", [])
    return raw if isinstance(raw, list) else []


def _load_user_flows(comprehension_dir: str, module_id: Optional[str]) -> List[Dict[str, Any]]:
    """Read comprehension/.../interactive/user_flows.json (module-scoped)
    for interactive_scan projects — [] for automated-crawl projects, which
    never produce this file."""
    scan_dir = comprehension_scan_dir(comprehension_dir, module_id)
    path = os.path.join(scan_dir, "interactive", "user_flows.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return (json.load(f) or {}).get("flows", [])
    except Exception:
        return []


def _parse_map_response(raw: str) -> Dict[str, Any]:
    try:
        return parse_llm_json(raw)
    except ValueError as exc:
        from agents.common.failure_classifier import LLMResponseValidationError
        raise LLMResponseValidationError(f"SemanticMapAgent: {exc}") from exc


def _enrich_locator_exprs(
    scenario_map: Dict[str, Any],
    locator_map: Dict[str, str],
) -> Dict[str, Any]:
    """
    Replace LLM-generated playwright_expr with the authoritative expression from
    build_locator_map when available. Prevents the LLM from inventing locators.
    """
    for sid, data in scenario_map.items():
        for elem in data.get("relevant_elements", []):
            loc_id = elem.get("locator_id", "")
            if loc_id in locator_map:
                elem["playwright_expr"] = locator_map[loc_id]
    return scenario_map


def _write_map(scenario_map: Dict[str, Any], output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "scenario_element_map.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(scenario_map, f, indent=2, ensure_ascii=False)
    return out_path
