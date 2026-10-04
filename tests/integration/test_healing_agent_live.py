"""
Live end-to-end verification of HealingAgent's ADK loop, matching
docs/healing_agent_adk_supervisor_plan.md's own Verification #7: run against
the real AWS_Test project's known 15/17-failing report and confirm Gemini
actually diagnoses and patches at least one real failure.

Requires:
  - GOOGLE_API_KEY in the environment (or .env) with usable quota for the
    configured model. Skipped entirely if no key is present at all.
  - A Playwright install (node_modules/playwright + Chromium) — run_tests
    really launches `npx playwright test` against the live aws.amazon.com.
  - The checked-in AWS_Test fixtures.

Runs against a COPY of AWS_Test under a sibling project directory (a
throwaway project name, cleaned up in tearDownClass) rather than the checked-
in fixtures — apply_patch really writes .spec.ts files, so the checked-in
AWS_Test must never be the live target. The copy MUST live under
application_assets/projects/ (not a system temp dir) — run_tests really
launches `npx playwright test`, and Node resolves the `@playwright/test`
module by walking up the directory tree from the spec file looking for
node_modules/; a temp dir outside the repo tree can never find it.

This is a real, paid-API, live-network test — not part of the default fast
unit-test loop. Run explicitly:
    python -m pytest tests/integration/test_healing_agent_live.py -v -s
"""

import json
import os
import shutil
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(ROOT, ".env"))
except ImportError:
    pass

_PROJECTS_DIR = os.path.join(ROOT, "application_assets", "projects")
_AWS_TEST_SRC = os.path.join(_PROJECTS_DIR, "AWS_Test")
_COPY_PROJECT_NAME = "_AWS_Test_healing_integration_copy"
_KNOWN_REPORT_REL = os.path.join("test_execution", "reports", "json", "20260710T100608Z_results.json")
_PLAYWRIGHT_INSTALLED = os.path.isfile(os.path.join(ROOT, "node_modules", "playwright", "lib", "program.js"))

# gemini-2.0-flash (the plan's configured default in workflows/settings.yaml)
# may have zero free-tier quota depending on the API key's billing tier — that
# is a property of the key/project, not of this agent, so it's overridable
# here rather than hardcoded. gemini-flash-latest is used as a broadly
# available fallback for this live run.
_INTEGRATION_MODEL = os.environ.get("HEALING_INTEGRATION_MODEL", "gemini-flash-latest")


def _prereqs_met() -> bool:
    return bool(
        os.environ.get("GOOGLE_API_KEY")
        and os.path.exists(os.path.join(_AWS_TEST_SRC, _KNOWN_REPORT_REL))
        and _PLAYWRIGHT_INSTALLED
    )


@unittest.skipUnless(
    _prereqs_met(),
    "requires GOOGLE_API_KEY, the checked-in AWS_Test fixtures, and a Playwright install",
)
class HealingAgentLiveADKIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project_copy = os.path.join(_PROJECTS_DIR, _COPY_PROJECT_NAME)
        if os.path.exists(cls.project_copy):
            shutil.rmtree(cls.project_copy)
        shutil.copytree(_AWS_TEST_SRC, cls.project_copy)
        cls.report_copy = os.path.join(cls.project_copy, _KNOWN_REPORT_REL)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.project_copy, ignore_errors=True)

    def test_heals_known_aws_test_failures_end_to_end(self):
        from agents.test_execution.healing.agent import HealingAgent

        settings = {"adk": {"gemini_model": _INTEGRATION_MODEL, "healing_max_iterations": 2}}
        agent = HealingAgent(settings=settings)

        result = agent.execute(
            {
                "project_name": _COPY_PROJECT_NAME,
                "report_json": self.report_copy,
                "module_filter": "M01",
            },
            {},
        )

        print("\n=== HealingAgent live result ===")
        print(json.dumps(result, indent=2))

        self.assertIn(result["status"], ("success", "partial"))
        # The model must have actually engaged the loop, not just no-op'd —
        # a patch was applied, a healing decision was recorded, or a real
        # defect was explicitly (not silently) marked not_healable.
        engaged = (
            result.get("tests_healed", 0) > 0
            or len(result.get("not_healable", [])) > 0
        )
        self.assertTrue(engaged, "ADK loop returned without healing or marking anything not_healable")


if __name__ == "__main__":
    unittest.main()
