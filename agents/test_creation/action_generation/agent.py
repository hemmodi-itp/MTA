"""
ActionGenerationAgent — converts BRD-traced test cases into executable, grounded browser/HTTP actions.

Inputs come from earlier steps: test_cases (AgentTestGeneration), runtime_profile (RuntimeDiscovery)
and app_classification (AppClassification). Gemini proposes, per test, which discovered elements to
fill/click and with what values (prompt.py); engines/runtime/actions.py validates every step against
the live-app inventory, falls back to deterministic rules per app class, and completes each plan
(login, navigation, required fields, trigger, wait, download, capture, judged assertion). Output is the
action_plan the Playwright Executor runs.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from agents.base_agent import BaseAgent
from agents.test_creation.action_generation.prompt import ACTION_GENERATION_PROMPT
from agents.test_creation.action_generation.tools import (
    ACTION_PROPOSALS,
    build_inventory,
    generate_action_plan,
    generate_json,
    inventory_for_prompt,
)
from connectors.connector_registry import ConnectorRegistry
from engines.runtime.actions import effective_classes
from tools.agent_eval.untrusted import neutralise
from tools.shared import get_logger

BATCH = 12
BATCH_LARGE_FORM = 3   # full-form plans for 15+ field forms are long: fewer tests per call
UI_LLM_CLASSES = {"Form Application", "Document Generator", "Workflow System", "Chatbot", "Hybrid Application"}


class ActionGenerationAgent(BaseAgent):
    MODULE_NAME = "action_generation"

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self._registry = ConnectorRegistry(self.settings)
        self.logger = get_logger("agent.action_generation")

    def execute(self, request: dict, state: dict) -> Dict[str, Any]:
        emit = request.get("emit") or (lambda *a, **k: None)
        if request.get("mode") == "brd_only" or not (request.get("live_url") or "").strip():
            return {"module": self.MODULE_NAME, "status": "skipped", "reason": "not deployed", "action_plan": None}
        tests: List[dict] = request.get("test_cases") or []
        profile = request.get("runtime_profile")
        classification = request.get("app_classification") or {}
        if not tests:
            return {"module": self.MODULE_NAME, "status": "skipped", "reason": "no test cases", "action_plan": None}
        if not profile:
            return {"module": self.MODULE_NAME, "status": "skipped", "reason": "runtime discovery produced no profile",
                    "action_plan": None}

        app_type = classification.get("app_type") or profile.get("app_type")
        has_creds = bool(request.get("has_live_credentials"))
        inv = build_inventory(profile)
        endpoints = ((request.get("agent_profile") or {}).get("interface") or {}).get("endpoints") or []
        classes = effective_classes(app_type, classification.get("components") or [], inv, endpoints)
        blocked = profile.get("needs_credentials") and not has_creds
        proposals: Dict[str, Dict[str, Any]] = {}
        if inv["elements"] and not blocked and (app_type in UI_LLM_CLASSES or any(c in UI_LLM_CLASSES for c in classes)):
            emit(f"Mapping {len(tests)} test(s) onto {len(inv['elements'])} element(s) found on the live app.")
            proposals = self._propose(tests, inv, app_type, classification, request, emit)

        plan = generate_action_plan(classification, profile, tests, proposals=proposals, has_credentials=has_creds,
                                    endpoints=endpoints, log=emit)
        c = plan["counts"]
        if plan["status"] == "blocked":
            emit(plan["reason"], "warning")
        else:
            emit(f"Action plans: {c['ready']}/{c['tests']} test(s) ready ({c.get('llm_mapped', 0)} mapped by Gemini, "
                 f"the rest by rules), {c['unmappable']} not testable through the UI, "
                 f"{c.get('flow_checks', 0)} flow check(s).", "success" if c["ready"] else "warning")
        return {"module": self.MODULE_NAME, "status": "success", "action_plan": plan}

    def _propose(self, tests, inv, app_type, classification, request, emit) -> Dict[str, Dict[str, Any]]:
        """Gemini proposals per test code; empty on failure (the engine's rules take over)."""
        try:
            llm = self._registry.get_llm(request.get("connector_mode"))
        except Exception as exc:
            emit(f"No LLM available for action mapping ({exc}); using rules.", "warning")
            return {}
        strategy = "; ".join(s["strategy"] for s in classification.get("testing_strategy") or []) or "exercise each feature"
        inventory = json.dumps(inventory_for_prompt(inv), ensure_ascii=False)

        def ask(batch: List[dict]) -> List[dict]:
            rows = [{k: t.get(k) for k in ("code", "title", "variant_type", "execution", "input", "expected_behavior", "area")}
                    for t in batch]
            prompt = ACTION_GENERATION_PROMPT.substitute(app_type=app_type, strategy=strategy, inventory=neutralise(inventory),
                                                         tests=neutralise(json.dumps(rows, indent=1, ensure_ascii=False)))
            return generate_json(llm, prompt, required_keys=["plans"], schema=ACTION_PROPOSALS, temperature=0.1).get("plans") or []

        size = BATCH_LARGE_FORM if max((len(f["fields"]) for f in inv["forms"].values()), default=0) >= 15 else BATCH
        batches = [tests[i:i + size] for i in range(0, len(tests), size)]
        out: Dict[str, Dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=min(4, len(batches))) as pool:
            for fut in [pool.submit(ask, b) for b in batches]:
                try:
                    for p in fut.result():
                        if isinstance(p, dict) and p.get("test_code"):
                            out[str(p["test_code"]).strip().upper()] = p
                except Exception as exc:
                    emit(f"Gemini action mapping failed for one batch ({exc}); rules used for it.", "warning")
        return out
