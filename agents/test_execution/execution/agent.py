import uuid
from typing import Any, Dict, List

from agents.base_agent import BaseAgent
from agents.test_execution.ui_execution.agent import UIExecutionAgent
from tools.shared import get_logger


class ExecutionAgent(BaseAgent):
    """
    Runs UIExecutionAgent to execute test cases against the live UI.

    LocatorAgent is a separate upstream workflow step (step: locator) —
    this agent does NOT re-run it.
    """

    def __init__(self, provider=None, settings=None):
        self.settings = settings or {}
        self.logger = get_logger("agent.execution")

    def execute(self, request: dict, state: dict) -> Dict[str, Any]:
        self.logger.info("ExecutionAgent starting — running UIExecutionAgent")

        ui_result = self._run_ui_execution(request, state)
        # Execution completed = the step succeeded; test pass/fail lives in results.
        # Only mark the step failed when the runner itself couldn't start (infrastructure error).
        ui_status = "failed" if ui_result.get("error") else "success"

        # Propagate failures into request so HealingAgent can act on them
        failures = self._extract_failures(ui_result)
        request["failures"] = failures
        request["execution_id"] = str(uuid.uuid4())
        request["suite_name"] = ui_result.get("suite")

        self.logger.info(
            f"ExecutionAgent done — ui_execution: {ui_status}, "
            f"failures forwarded: {len(failures)}"
        )

        return {
            "module": "execution",
            "status": ui_status,
            "summary": {
                "suite": ui_result.get("suite"),
                "scenarios_executed": ui_result.get("scenarios_executed", 0),
                "passed": ui_result.get("passed", 0),
                "failed": ui_result.get("failed", 0),
            },
            "results": ui_result.get("results", []),
        }

    def _run_ui_execution(self, request: dict, state: dict) -> Dict[str, Any]:
        self.logger.info("Running UIExecutionAgent")
        try:
            agent = UIExecutionAgent(settings=self.settings)
            result = agent.execute(request, state)
            self.logger.info(
                f"UIExecutionAgent completed: {result.get('passed', 0)} passed, "
                f"{result.get('failed', 0)} failed"
            )
            return result
        except Exception as exc:
            self.logger.error(f"UIExecutionAgent raised exception: {exc}")
            return {"status": "failed", "failed": 1, "error": str(exc)}

    def _extract_failures(self, ui_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """UIExecutionAgent's results are a flat list (spec_file, status, errors,
        test_case_id, ...) — one failure entry is synthesized per error message
        for each non-success test, since there's no per-step breakdown."""
        failures = []
        for tc_result in ui_result.get("results", []):
            if tc_result.get("status") == "success":
                continue
            for i, error in enumerate(tc_result.get("errors", []) or [""]):
                failures.append({
                    "step_id": f"STEP-{i + 1:03d}",
                    "test_case_id": tc_result.get("test_case_id"),
                    "business_scenario_id": tc_result.get("business_scenario_id"),
                    "failure_reason": self._classify_error(error),
                    "spec_file": tc_result.get("spec_file"),
                })
        return failures

    def _classify_error(self, error: str) -> str:
        e = error.lower()
        if "strict mode violation" in e:
            return "strict_mode_violation"
        if "resolved to" in e and "elements" in e:
            return "locator_resolved_multiple_elements"
        if "timeout" in e:
            return "timeout_waiting_for_element"
        if "not visible" in e:
            return "locator_not_visible"
        if "not enabled" in e or "disabled" in e:
            return "locator_not_enabled"
        return "element_not_found"
