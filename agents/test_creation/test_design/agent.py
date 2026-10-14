"""
TestDesignAgent — Phase 3: derives test cases with named techniques, prioritises them by risk and selects them
within the profile's budget. Writes test_creation/test_cases.json; ScriptGeneration then implements exactly the
selected cases (one plan test per case).

    profile off (no test_generation.profile)  → skipped, nothing written (legacy path unchanged)
    requirements off / requirements.json gone → skipped with a warning (cases need AC ids)

Flow: load inputs → deterministic generators → one schema-validated LLM call per module (decision-table rules,
negative paths, AC links, domain cases; additive only) → SemanticDedupAgent on the LLM's extra cases → risk,
scenario assignment, budgeted selection → form locators merged into locator_map.json → test_cases.json.
The LLM step is optional (`test_generation.design_llm: false`) and degrades to the deterministic set on failure.
"""

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agents.base_agent import BaseAgent
from tools.constants import PROJECTS_BASE as _ASSETS_BASE
from tools.requirements.config import requirements_enabled
from tools.shared import get_logger
from tools.state.review_queue import flag_expected_value_conflicts
from tools.test_design import design as design_mod
from tools.test_design import hint_cache, linking
from tools.test_design.config import load_design_config
from tools.test_design.inputs import DesignInputs
from tools.test_design.llm import interpret_module, merge_hints, sanitize
from tools.test_design.locators import update_locator_map_file
from tools.test_design.store import write_doc


def _safe_name(name: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in name).strip("_") or "project"


class TestDesignAgent(BaseAgent):
    __test__ = False
    MODULE_NAME = "test_design"

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self.logger = get_logger("agent.test_design")
        self._registry = None

    def _log(self, msg: str, level: str = "info") -> None:
        getattr(self.logger, level)(f"[TestDesign] {msg}")

    def _llm(self, request: dict):
        if self._registry is None:
            from connectors.connector_registry import ConnectorRegistry
            self._registry = ConnectorRegistry(self.settings)
        return self._registry.get_llm(request.get("connector_mode"))

    # ── entry point ──────────────────────────────────────────────────────────

    def execute(self, request: dict, state: dict) -> Dict[str, Any]:
        project_name = request.get("project_name") or request.get("message", "project")
        safe = _safe_name(project_name)
        project_dir = os.path.join(_ASSETS_BASE, safe)
        cfg = request.get("test_design") if isinstance(request.get("test_design"), dict) else load_design_config(safe)
        base = {"module": self.MODULE_NAME, "project": project_name}

        if not cfg.get("enabled"):
            return dict(base, status="success", skipped=True,
                        reason="test_generation.profile is not set — legacy generation (caps) applies")
        if not requirements_enabled(safe, request):
            self._log("test_generation.profile needs requirements.enabled: true (cases are traced to ACs) — skipped",
                      level="warning")
            return dict(base, status="success", skipped=True, reason="requirements_disabled")
        for cap in cfg.get("deprecated_caps") or []:
            self._log(f"test_generation.{cap} is deprecated with a profile: design cases are not capped by it "
                      f"(the budget applies instead)", level="warning")

        inp = DesignInputs.load(project_dir, safe)
        if not inp.acs:
            self._log("requirements.json has no acceptance criteria — run discovery first; skipped", level="warning")
            return dict(base, status="success", skipped=True, reason="no_requirements")
        profile, budget = cfg["profile"], cfg["budget"]

        hints, llm_status, extras, rejected = {}, None, [], 0
        if cfg.get("llm", True):
            hints, llm_status, extras, rejected = self._interpret(request, inp, project_dir)

        doc = design_mod.design(inp, profile, budget, hints=hints, llm_status=llm_status, extras=extras,
                                rejected_extras=rejected)
        locator_map_path = os.path.join(project_dir, "test_creation", "locator_map.json")
        added = update_locator_map_file(locator_map_path, inp, doc["test_cases"])
        doc["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        path = write_doc(project_dir, doc)

        s, b = doc["summary"], doc["budget"]
        self._log(f"{s['selected']} case(s) selected of {s['generated']} generated (profile={profile}); "
                  f"{s['cut']} cut; AC coverage {s['ac_coverage_pct']}% of {s['acs_testable']} testable; "
                  f"est. {b['est_runtime_minutes']} min (budget {b['max_tests']} tests / {b['max_runtime_minutes']} min"
                  f"{'' if b['respected'] else ' — EXCEEDED by P0/floor cases'})")
        if doc["conflicts"]:
            # Phase 5.2: a potential defect for a human to decide — never resolved silently
            queued = flag_expected_value_conflicts(safe, doc["conflicts"], output_dir=project_dir)
            self._log(f"{len(doc['conflicts'])} BRD-vs-observed conflict(s) recorded for human review "
                      f"({queued} new in human_review_queue.json)", level="warning")
        warnings = [f"budget exceeded by P0/floor cases ({b['selected']} selected)"] if not b["respected"] else []
        if doc["llm"]["status"] == "degraded":
            warnings.append("LLM interpretation degraded for some modules — deterministic cases only there")
        return dict(
            base, status="partial" if warnings else "success", warnings=warnings,
            output={"test_cases": path, "locator_keys_added": added},
            profile=profile, summary=s, budget=b, conflicts=len(doc["conflicts"]), llm=doc["llm"]["status"],
        )

    # ── LLM interpretation (additive only) ───────────────────────────────────

    def _interpret(self, request: dict, inp: DesignInputs, project_dir: str):
        """(hints, llm_status, extra_cases, rejected_duplicates). Never raises: a failed module is 'degraded'.

        The LLM is called only for the modules this run is scoped to (`--module` narrows request["modules"]);
        every other module reuses its cached hints when its criteria are unchanged (test_design_llm_cache.json),
        so module-by-module runs neither repeat calls nor lose earlier modules' decision tables."""
        cases, _tables = design_mod.generate_all(inp, {})
        cases, _ = design_mod.dedupe(cases)
        linking.link_unattributed(cases, inp)
        unlinked = linking.unlinked(cases)
        modules = sorted({a["module_id"] for a in inp.testable_acs() if a["module_id"]})
        in_scope = {m.get("id") for m in request.get("modules") or [] if isinstance(m, dict)} or set(modules)
        cache = hint_cache.load(project_dir)
        parts, statuses, extras = [], {}, []
        llm, llm_error = None, None
        for m in modules:
            unl = [c for c in unlinked if c.get("module_id") == m]
            key = hint_cache.criteria_hash(inp, m)
            cached = cache.get(m)
            if cached and cached.get("criteria_hash") == key and (m not in in_scope or cached.get("status") == "ok"):
                part = cached["hints"]
                statuses[m] = "cached"
            elif m not in in_scope:
                statuses[m] = "skipped"            # out of this run's scope and nothing cached yet
                continue
            else:
                try:
                    if llm is None and llm_error is None:
                        llm = self._llm(request)
                    if llm is None:
                        raise RuntimeError(f"no LLM available: {llm_error}")
                    raw = interpret_module(llm, inp, m, unl)
                    part = sanitize(raw, inp, m, [c["id"] for c in unl])
                    cache[m] = {"criteria_hash": key, "status": "ok", "hints": part}
                    statuses[m] = "ok"
                except Exception as exc:
                    if llm is None and llm_error is None:
                        llm_error = exc
                    self._log(f"{m}: LLM interpretation failed ({type(exc).__name__}: {exc}) — deterministic only",
                              level="warning")
                    statuses[m] = f"degraded:{type(exc).__name__}"
                    continue
            parts.append(part)
            extras += design_mod.extra_cases(part.get("extra_cases") or [], inp, m)
        hint_cache.save(project_dir, cache)
        approved, rejected = self._dedup_extras(request, cases, extras)
        status = "degraded" if any(v.startswith("degraded") for v in statuses.values()) else "ok"
        llm_status = {"status": status, "modules": statuses, "added": len(approved), "rejected_duplicates": rejected}
        return merge_hints(parts), llm_status, approved, rejected

    def _dedup_extras(self, request: dict, deterministic: List[dict], extras: List[dict]):
        """3.6: SemanticDedupAgent decides which LLM-added cases duplicate a deterministic one. Deterministic
        cases are only ever the `existing` side, so they can never be removed."""
        if not extras:
            return [], 0
        try:
            from agents.test_creation.dedup.agent import SemanticDedupAgent
            acs = {a for e in extras for a in e["ac_ids"]}
            existing = [{"test_case_id": c["id"], "test_case_name": c["title"], "test_case_type": c["test_type"]}
                        for c in deterministic if set(c.get("ac_ids") or []) & acs]
            proposed = [{"test_case_id": e["id"], "test_case_name": e["title"], "test_case_type": e["test_type"],
                         "expected_result": (e["oracles"][0].get("expected") if e["oracles"] else "")}
                        for e in extras]
            result = SemanticDedupAgent(self.settings).execute(
                {"existing_test_cases": existing, "proposed_test_cases": proposed,
                 "connector_mode": request.get("connector_mode")}, {})
            keep = {p.get("test_case_id") for p in result.get("approved") or []}
            approved = [e for e in extras if e["id"] in keep]
            return approved, len(extras) - len(approved)
        except Exception as exc:
            self._log(f"semantic dedup of LLM cases failed ({exc}) — keeping them all", level="warning")
            return extras, 0
