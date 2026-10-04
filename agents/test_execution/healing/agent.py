"""
HealingAgent — native ADK agent that heals failing Playwright .spec.ts tests.

Full replacement of the old deterministic root-cause-table healer (see
docs/healing_agent_adk_supervisor_plan.md). This is a genuinely agentic
run -> heal -> verify loop, not a wrap around the old design:

  1. read_failure_report parses the Playwright JSON results into structured
     failing-test entries (module-relative spec keys — this fixes the old
     agent's basename()-only bug, since a fresh implementation should get
     this right rather than carrying the defect forward).
  2. An LlmAgent (model resolved by connectors.adk_model.resolve_adk_model()
     from the shared connectors.llm setting — gemini natively, or aws/
     external/openai/ollama via LiteLLM), wrapped in an ADK
     LoopAgent(max_iterations=N), diagnoses each failure and calls a repair
     tool (locator / timing / compilation / test-data / navigation), or
     marks it not_healable.
  3. apply_patch is the ONLY tool that writes a .spec.ts file, and only after
     structural validation. run_tests re-executes just the patched spec(s) to
     verify before the model moves on.

Structural safety boundary: no tool in tools.py can write business_scenarios.
json, acceptance criteria, assertion values, intents.yaml, dom_intents.json,
or any workflows/*.yaml — enforced by the tool surface simply not exposing a
path to those files, not by instruction text.

Same contract as before: execute(request, state) -> dict with
{"status", "specs_healed", "tests_healed", "not_healable"}, registered under
the same "healing" registry key — orchestrator/agent.py, full_workflow.yaml,
and report_writer.py's step_name == "healing" lookups need zero changes.
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agents.base_agent import BaseAgent
from agents.test_execution.healing.prompt import SUPERVISOR_INSTRUCTION
from agents.test_execution.healing.tools import HealingRunContext, _get_failing_tests, build_tools
from connectors.adk_model import resolve_adk_model
from tools.constants import PROJECTS_BASE as _ASSETS_BASE
from tools.discovery.paths import comprehension_scan_dir
from tools.shared import get_logger


class HealingAgent(BaseAgent):
    MODULE_NAME = "healing"

    def __init__(self, provider=None, settings: Optional[dict] = None):
        self.settings = settings or {}
        self.logger = get_logger("agent.healing")

    def execute(self, request: dict, state: dict) -> Dict[str, Any]:
        project_name = request.get("project_name") or request.get("message", "project")
        safe = _safe_name(project_name)

        reports_dir = os.path.join(_ASSETS_BASE, safe, "test_execution", "reports")
        scripts_dir = os.path.join(_ASSETS_BASE, safe, "test_creation", "test_scripts")
        comprehension_dir = os.path.join(_ASSETS_BASE, safe, "test_comprehension")
        comp_dir = comprehension_scan_dir(comprehension_dir, request.get("module_filter"))
        dom_path = os.path.join(comp_dir, "dom_elements.json")
        suite_path = os.path.join(_ASSETS_BASE, safe, "test_creation", "test_suite.json")
        test_data_path = os.path.join(_ASSETS_BASE, safe, "test_creation", "test_data", "test_data.json")
        locator_map_path = os.path.join(_ASSETS_BASE, safe, "test_creation", "locator_map.json")

        report_json = request.get("report_json") or _find_latest_report(reports_dir)
        if not report_json:
            msg = "No Playwright JSON report found. Run ui_execution first."
            self._log(msg, level="error")
            return {"module": "healing", "status": "failed", "project": project_name, "error": msg}

        failing_tests = _get_failing_tests(report_json, self.logger)
        if not failing_tests:
            self._log("No failing tests found — nothing to heal")
            return {
                "module": "healing",
                "status": "success",
                "project": project_name,
                "specs_healed": 0,
                "tests_healed": 0,
                "not_healable": [],
                "message": "no failing tests",
            }

        module_urls, default_url = _load_project_urls(safe)
        ctx = HealingRunContext(
            project_name=project_name,
            scripts_dir=scripts_dir,
            reports_dir=reports_dir,
            report_json=report_json,
            dom_elements=_load_dom_elements(dom_path),
            module_urls=module_urls,
            default_url=default_url,
            test_data_map=_load_test_data_map(test_data_path),
            settings=self.settings,
            logger=self.logger,
            generation_modes=_load_generation_modes(suite_path),
            locator_map=_load_json_or_empty(locator_map_path),
            locator_map_path=locator_map_path,
            comprehension_dir=comprehension_dir,
        )

        self._log(
            f"Found {sum(len(v) for v in failing_tests.values())} failing test(s) "
            f"across {len(failing_tests)} spec(s) — starting ADK healing loop"
        )

        max_iterations = self.settings.get("adk", {}).get("healing_max_iterations", 3)

        try:
            model = resolve_adk_model(self.settings)
            self._run_adk_healing(ctx, model, max_iterations)
        except Exception as exc:
            self._log(f"ADK healing loop failed: {exc}", level="error")
            # Even on a crash mid-loop, ctx already holds whatever real
            # progress happened before the exception (patches applied,
            # rounds verified) — return it rather than discarding it, so a
            # crash after 2 good rounds is distinguishable in reports from a
            # crash with zero progress. `status` stays "failed" regardless;
            # that's still a genuine hard failure of the step itself.
            return {
                "module": "healing",
                "status": "failed",
                "project": project_name,
                "error": str(exc),
                "specs_healed": len(ctx.healed_specs),
                "tests_healed": ctx.tests_healed,
                "not_healable": ctx.not_healable,
                "rounds": ctx.rounds,
                "remaining_failing_count": ctx.remaining_total(),
            }
        finally:
            ctx.close()

        _update_suite_status(suite_path, sorted(ctx.healed_specs), "healed")

        status = "success" if not ctx.remaining else "partial"
        self._log(
            f"Healing done — status={status} tests_healed={ctx.tests_healed} "
            f"specs_healed={len(ctx.healed_specs)} not_healable={len(ctx.not_healable)}"
        )
        return {
            "module": "healing",
            "status": status,
            "project": project_name,
            "specs_healed": len(ctx.healed_specs),
            "tests_healed": ctx.tests_healed,
            "not_healable": ctx.not_healable,
            "rounds": ctx.rounds,
            "remaining_failing_count": ctx.remaining_total(),
        }

    def _run_adk_healing(self, ctx: HealingRunContext, model, max_iterations: int) -> None:
        """Build the LoopAgent(LlmAgent) and drive it via the single asyncio.run()
        bridge for this agent — the only async boundary in an otherwise fully
        synchronous codebase. Mutates ctx in place; nothing meaningful is read
        back from the ADK session itself.

        `model` is whatever connectors.adk_model.resolve_adk_model() returned —
        a bare Gemini model-id string (ADK's native support), or a LiteLlm
        instance for every other provider (aws/external/openai/ollama)."""
        from google.adk.agents import LlmAgent, LoopAgent

        tools = build_tools(ctx)
        llm_agent = LlmAgent(
            name="healing_llm",
            model=model,
            instruction=SUPERVISOR_INSTRUCTION,
            tools=tools,
        )
        loop_agent = LoopAgent(
            name="healing_loop",
            sub_agents=[llm_agent],
            max_iterations=max_iterations,
        )
        asyncio.run(_drive_loop(loop_agent, app_name="healing"))


# ── ADK async bridge ───────────────────────────────────────────────────────────

async def _drive_loop(loop_agent, app_name: str) -> None:
    from google.adk.runners import InMemoryRunner
    from google.genai import types as genai_types

    runner = InMemoryRunner(agent=loop_agent, app_name=app_name)
    user_id = "healing"
    session_id = "healing-session"
    await runner.session_service.create_session(app_name=app_name, user_id=user_id, session_id=session_id)

    kickoff = genai_types.Content(
        role="user",
        parts=[genai_types.Part(text="Begin healing. Call read_failure_report first.")],
    )
    async for _event in runner.run_async(user_id=user_id, session_id=session_id, new_message=kickoff):
        pass


# ── Loaders ────────────────────────────────────────────────────────────────────

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


def _load_project_urls(safe_project: str) -> "tuple[Dict[str, str], str]":
    """Return ({module_id: url}, default_url). Every real project.yaml in this
    codebase declares url per-module (modules[].url) rather than at the top
    level, so module_urls is the primary source — default_url is a rarely-used
    fallback for flat, non-module-scoped projects."""
    import yaml
    yaml_path = os.path.join(_ASSETS_BASE, safe_project, "project.yaml")
    if not os.path.exists(yaml_path):
        return {}, ""
    try:
        with open(yaml_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except Exception:
        return {}, ""
    default_url = cfg.get("url", "") or (cfg.get("project") or {}).get("url", "")
    module_urls = {
        m["id"]: m["url"]
        for m in (cfg.get("modules") or [])
        if isinstance(m, dict) and m.get("id") and m.get("url")
    }
    return module_urls, default_url


def _load_test_data_map(path: str) -> Dict[str, Any]:
    """Return {scenario_id: test_data_record} from test_data.json."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, list):
        return {r.get("scenario_id", ""): r for r in raw if r.get("scenario_id")}
    if isinstance(raw, dict):
        return raw
    return {}


def _load_json_or_empty(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f) or {}


def _load_generation_modes(suite_path: str) -> Dict[str, str]:
    """Return {spec_file: generation_mode} from test_suite.json — lets tools.py
    branch a locator failure to the locator_map.json repair path
    ("action_library" specs) instead of the legacy .spec.ts patch path
    (everything else, including specs with no generation_mode at all)."""
    suite = _load_json_or_empty(suite_path)
    return {
        s["file"]: s.get("generation_mode")
        for s in suite.get("specs", [])
        if s.get("file") and s.get("generation_mode")
    }


# ── suite.json / report helpers ───────────────────────────────────────────────

def _update_suite_status(suite_path: str, healed_files: List[str], status: str) -> None:
    if not os.path.exists(suite_path) or not healed_files:
        return
    try:
        with open(suite_path, encoding="utf-8") as f:
            suite = json.load(f)
        healed_set = set(healed_files)
        for spec in suite.get("specs", []):
            if spec.get("file") in healed_set:
                spec["status"] = status
                spec["healed_at"] = datetime.now(timezone.utc).isoformat()
        with open(suite_path, "w", encoding="utf-8") as f:
            json.dump(suite, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def _find_latest_report(reports_dir: str) -> Optional[str]:
    json_dir = os.path.join(reports_dir, "json")
    if not os.path.isdir(json_dir):
        return None
    files = sorted(
        (f for f in os.listdir(json_dir) if f.endswith("_results.json")),
        reverse=True,
    )
    return os.path.join(json_dir, files[0]) if files else None


def _safe_name(name: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in name).strip("_") or "project"
