"""
Unit tests for the three-tier fallback dispatch in OrchestratorAgent.

Tiers (in order):
  1. Internal Python agent  (LLM-backed)
  2. NS HTTP fallback        (calls NeuroStack endpoint via NSHTTPConnector)
  3. Python stub fallback    (ComprehensionAgentStub — local, no LLM, no HTTP)

Tests verify that when the token is expired (or any exception/status=failed occurs)
the orchestrator silently promotes to the next tier and returns the first valid response.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.orchestrator.agent import OrchestratorAgent


# ── helpers ──────────────────────────────────────────────────────────────────

_FALLBACK_CHAIN = {
    "comprehension_agent": {
        "connector_type": "internal",
        # Every fallback tier ships disabled by default (workflows/agent_registry.yaml) —
        # these tests exercise the cascade itself, so they opt each tier in explicitly.
        "fallbacks": [
            {"connector_type": "ns_http", "agent_name": "comprehension_agent", "enabled": True},
            {
                "connector_type": "python_stub",
                "fallback_module": "agents.comprehension.comprehension_agent.agent",
                "fallback_class": "ComprehensionAgentStub",
                "enabled": True,
            },
        ],
    }
}

_NS_REGISTRY_SPEC = {
    "comprehension_agent": {
        "method": "POST",
        "endpoint": "/agents/comprehension_agent",
        "timeout": 30,
    }
}


class _SingleStepWorkflow:
    """Minimal workflow fixture with one step."""
    workflow_id = "fallback_test_workflow"
    steps = ["comprehension_agent"]
    always_run = set()


def _make_orchestrator(mock_internal_result=None, internal_exception=None):
    """
    Return (orchestrator, mock_ns_connector, mock_registry).

    The orchestrator is wired with:
      - a mock internal registry (controls primary agent behaviour)
      - a mock NS connector (controls ns_http tier behaviour)
      - the three-tier fallback chain injected directly
    """
    mock_agent = MagicMock()
    if internal_exception is not None:
        mock_agent.execute.side_effect = internal_exception
    elif mock_internal_result is not None:
        mock_agent.execute.return_value = mock_internal_result

    mock_registry = MagicMock()
    mock_registry.build.return_value = mock_agent

    settings = {
        "provider_mode": "external",
        "execution": {
            "ns": {
                "base_url": "http://localhost:8000",
                # point at a path that won't exist so ns_registry stays empty
                "registry": "__nonexistent_ns_registry__.yaml",
                "agent_registry": "__nonexistent_agent_registry__.yaml",
            }
        },
    }
    agents_config = {"agents": {"comprehension_agent": {"enabled": True}}}

    orch = OrchestratorAgent(
        settings=settings,
        agents_config=agents_config,
        registry=mock_registry,
        run_id="test-fallback-001",
    )

    # Override with mock NS connector so no real HTTP calls are made
    mock_ns = MagicMock()
    orch._ns_connector = mock_ns
    orch.settings["ns_connector"] = mock_ns

    # Inject fallback specs directly (bypasses YAML loading)
    orch._agent_registry = _FALLBACK_CHAIN

    # Step must NOT be in _ns_registry so it goes to _try_with_fallbacks
    orch._ns_registry = {}

    return orch, mock_ns, mock_registry


# ── test cases ────────────────────────────────────────────────────────────────

class TestFallbackOnTokenExpired(unittest.TestCase):
    """Primary agent raises (simulating expired LLM token) → NS HTTP tier fires."""

    def test_ns_response_returned_when_internal_raises(self):
        ns_response = {
            "module": "comprehension_agent",
            "status": "success",
            "business_scenarios_path": "/ns/scenarios.json",
            "scenarios_count": 5,
        }
        orch, mock_ns, _ = _make_orchestrator(
            internal_exception=Exception("401 Unauthorized: token expired")
        )
        mock_ns.call.return_value = ns_response

        result = orch.run(
            {"project_name": "test_project", "workflow": "fallback_test_workflow"},
            _SingleStepWorkflow(),
        )

        step_out = result["state"].outputs["comprehension_agent"]
        self.assertEqual(step_out["status"], "success")
        self.assertEqual(step_out["business_scenarios_path"], "/ns/scenarios.json")
        self.assertEqual(step_out["scenarios_count"], 5)
        mock_ns.call.assert_called_once()

    def test_ns_call_receives_original_request_payload(self):
        orch, mock_ns, _ = _make_orchestrator(
            internal_exception=Exception("token expired")
        )
        mock_ns.call.return_value = {"status": "success", "scenarios_count": 2}

        orch.run(
            {"project_name": "my_project", "workflow": "fallback_test_workflow"},
            _SingleStepWorkflow(),
        )

        call_args = mock_ns.call.call_args
        payload = call_args[0][1]          # second positional arg is the payload dict
        self.assertEqual(payload["project_name"], "my_project")


class TestFallbackOnStatusFailed(unittest.TestCase):
    """Primary agent returns status=failed (e.g. LLM auth error) → NS HTTP tier fires."""

    def test_ns_response_returned_when_internal_status_failed(self):
        orch, mock_ns, _ = _make_orchestrator(
            mock_internal_result={
                "module": "comprehension_agent",
                "status": "failed",
                "error": "LLM auth token is expired or invalid",
            }
        )
        mock_ns.call.return_value = {
            "module": "comprehension_agent",
            "status": "success",
            "business_scenarios_path": "/ns/scenarios.json",
            "scenarios_count": 3,
        }

        result = orch.run(
            {"project_name": "test_project", "workflow": "fallback_test_workflow"},
            _SingleStepWorkflow(),
        )

        step_out = result["state"].outputs["comprehension_agent"]
        self.assertEqual(step_out["status"], "success")
        self.assertEqual(step_out["scenarios_count"], 3)


class TestFallbackToStubWhenNSAlsoFails(unittest.TestCase):
    """Both internal and NS tiers fail → Python stub (last resort) responds."""

    def test_stub_response_returned_when_all_prior_tiers_fail(self):
        orch, mock_ns, _ = _make_orchestrator(
            internal_exception=Exception("token expired")
        )
        mock_ns.call.side_effect = Exception("NS service unreachable")

        result = orch.run(
            {"project_name": "test_project", "workflow": "fallback_test_workflow"},
            _SingleStepWorkflow(),
        )

        step_out = result["state"].outputs["comprehension_agent"]
        # ComprehensionAgentStub always returns status=success with stub=True
        self.assertEqual(step_out["status"], "success")
        self.assertTrue(step_out.get("stub"), "expected stub=True from ComprehensionAgentStub")
        self.assertEqual(step_out["module"], "comprehension_agent")

    def test_stub_sets_project_name_in_payload(self):
        orch, mock_ns, _ = _make_orchestrator(
            internal_exception=Exception("token expired")
        )
        mock_ns.call.side_effect = Exception("NS down")

        result = orch.run(
            {"project_name": "my_project", "workflow": "fallback_test_workflow"},
            _SingleStepWorkflow(),
        )

        step_out = result["state"].outputs["comprehension_agent"]
        self.assertEqual(step_out.get("project"), "my_project")


class TestNoFallbackWhenInternalSucceeds(unittest.TestCase):
    """Internal agent succeeds → NS connector is never called."""

    def test_ns_not_called_on_primary_success(self):
        orch, mock_ns, _ = _make_orchestrator(
            mock_internal_result={
                "module": "comprehension_agent",
                "status": "success",
                "business_scenarios_path": "/local/scenarios.json",
                "scenarios_count": 7,
            }
        )

        result = orch.run(
            {"project_name": "test_project", "workflow": "fallback_test_workflow"},
            _SingleStepWorkflow(),
        )

        step_out = result["state"].outputs["comprehension_agent"]
        self.assertEqual(step_out["status"], "success")
        self.assertEqual(step_out["scenarios_count"], 7)
        mock_ns.call.assert_not_called()

    def test_primary_response_passed_back_to_orchestrator_unchanged(self):
        primary_response = {
            "module": "comprehension_agent",
            "status": "success",
            "business_scenarios_path": "/local/scenarios.json",
            "scenarios_count": 7,
            "custom_field": "preserved",
        }
        orch, _, _ = _make_orchestrator(mock_internal_result=primary_response)

        result = orch.run(
            {"project_name": "test_project", "workflow": "fallback_test_workflow"},
            _SingleStepWorkflow(),
        )

        step_out = result["state"].outputs["comprehension_agent"]
        self.assertEqual(step_out["custom_field"], "preserved")


class TestUndispatchableTiersAreSkipped(unittest.TestCase):
    """Enabled tiers the orchestrator can't run as a whole-agent swap (python_stub
    without fallback_module, alt_model, dom_synthesized) are skipped with a
    warning instead of raising KeyError/ValueError mid-cascade."""

    def test_skips_and_reaches_next_dispatchable_tier(self):
        orch, mock_ns, _ = _make_orchestrator(internal_exception=Exception("token expired"))
        orch._agent_registry = {
            "comprehension_agent": {
                "connector_type": "internal",
                "fallbacks": [
                    {"connector_type": "python_stub", "enabled": True},
                    {"connector_type": "alt_model", "model": "x", "enabled": True},
                    {"connector_type": "dom_synthesized", "enabled": True},
                    {"connector_type": "ns_http", "agent_name": "comprehension_agent", "enabled": True},
                ],
            }
        }
        mock_ns.call.return_value = {"status": "success", "scenarios_count": 1}

        with self.assertLogs("workflow", level="WARNING") as logs:
            result = orch.run(
                {"project_name": "p", "workflow": "fallback_test_workflow"},
                _SingleStepWorkflow(),
            )

        self.assertEqual(result["state"].outputs["comprehension_agent"]["status"], "success")
        skipped = [line for line in logs.output if "skipping" in line]
        self.assertEqual(len(skipped), 3)

    def test_only_undispatchable_tiers_fails_cleanly(self):
        orch, _, _ = _make_orchestrator(internal_exception=Exception("boom"))
        orch._agent_registry = {
            "comprehension_agent": {
                "connector_type": "internal",
                "fallbacks": [{"connector_type": "alt_model", "enabled": True}],
            }
        }
        out = orch._try_with_fallbacks("comprehension_agent", {"project_name": "p"})
        self.assertEqual(out["status"], "failed")
        self.assertEqual(out["error"], "all fallback tiers exhausted")


if __name__ == "__main__":
    unittest.main()
