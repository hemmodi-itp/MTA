import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.test_execution.healing import tools as healing_tools
from agents.test_execution.healing.tools import HealingRunContext

_SPEC_CONTENT = """import { test, expect } from '@playwright/test';
test.describe('Example', () => {
  test('locator times out', async ({ page }) => {
    await page.locator('#foo').waitFor();
  });
  test.skip('a skipped stub', () => {
    // no locator for: something
  });
  test('navigation fails', async ({ page }) => {
    await page.goto('https://example.com');
  });
});
"""


def _report(spec_file, extra_tests=None):
    specs = [
        {
            "file": spec_file,
            "title": "locator times out",
            "tests": [{
                "status": "failed",
                "results": [{"error": {"message": "TimeoutError: locator.waitFor: Timeout exceeded 5000ms"}}],
            }],
        },
        {
            "file": spec_file,
            "title": "navigation fails",
            "tests": [{
                "status": "failed",
                "results": [{"error": {"message": "Navigation failed: ERR_CONNECTION_TIMED_OUT"}}],
            }],
        },
    ]
    if extra_tests:
        specs.extend(extra_tests)
    return {"suites": [{"specs": specs}]}


# ── Bug-fix regression: module-relative spec keys (was os.path.basename()) ────

class SpecKeyResolutionTests(unittest.TestCase):
    def test_module_scoped_path_keeps_module_subdir(self):
        key = healing_tools._spec_key_from_report_path(
            "application_assets/projects/AWS_Test/test_creation/test_scripts/M01/test_x.spec.ts"
        )
        self.assertEqual(key, "M01/test_x.spec.ts")

    def test_flat_path_without_marker_falls_back_to_basename(self):
        key = healing_tools._spec_key_from_report_path("some/other/root/test_x.spec.ts")
        self.assertEqual(key, "test_x.spec.ts")

    def test_windows_backslashes_normalized(self):
        key = healing_tools._spec_key_from_report_path(
            r"application_assets\projects\AWS_Test\test_creation\test_scripts\M02\test_y.spec.ts"
        )
        self.assertEqual(key, "M02/test_y.spec.ts")


# ── Bug-fix regression: test.skip/test.fixme block extraction ─────────────────

class ExtractTestBlockTests(unittest.TestCase):
    def test_extracts_async_test_block(self):
        block = healing_tools._extract_test_block(_SPEC_CONTENT, "locator times out")
        self.assertIn("page.locator('#foo').waitFor()", block)

    def test_extracts_test_skip_stub_without_async(self):
        block = healing_tools._extract_test_block(_SPEC_CONTENT, "a skipped stub")
        self.assertTrue(block.startswith("  test.skip("))

    def test_missing_test_name_returns_empty(self):
        block = healing_tools._extract_test_block(_SPEC_CONTENT, "does not exist")
        self.assertEqual(block, "")


class StructuralValidationTests(unittest.TestCase):
    def test_valid_block_passes(self):
        self.assertTrue(healing_tools._structurally_valid_block(
            "test('x', async ({ page }) => { await page.goto('/'); });"
        ))

    def test_empty_block_fails(self):
        self.assertFalse(healing_tools._structurally_valid_block(""))

    def test_unbalanced_braces_fail(self):
        self.assertFalse(healing_tools._structurally_valid_block(
            "test('x', async ({ page }) => { await page.goto('/');"
        ))

    def test_missing_test_call_fails(self):
        self.assertFalse(healing_tools._structurally_valid_block("const x = 1;"))


class RankCandidateElementsTests(unittest.TestCase):
    def test_ranks_by_keyword_overlap(self):
        elements = [
            {"description": "unrelated submit button"},
            {"description": "email address input field"},
        ]
        ranked = healing_tools._rank_candidate_elements(elements, "email", None)
        self.assertEqual(ranked[0]["description"], "email address input field")

    def test_no_overlap_returns_empty(self):
        elements = [{"description": "unrelated submit button"}]
        ranked = healing_tools._rank_candidate_elements(elements, "zzznomatch", None)
        self.assertEqual(ranked, [])


class ProposeNavigationFixTests(unittest.TestCase):
    def _ctx(self, base_url="https://real.example.com"):
        logger = MagicMock()
        return HealingRunContext(
            project_name="proj", scripts_dir=self.scripts_dir, reports_dir="",
            report_json="", dom_elements=[], module_urls={}, default_url=base_url,
            test_data_map={}, settings={}, logger=logger,
        )

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.scripts_dir = self.tmp_dir
        self.spec_filename = "test_x.spec.ts"
        with open(os.path.join(self.scripts_dir, self.spec_filename), "w", encoding="utf-8") as f:
            f.write(_SPEC_CONTENT)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_mismatched_url_is_fixable(self):
        ctx = self._ctx(base_url="https://real.example.com")
        result = healing_tools._propose_navigation_fix(ctx, self.spec_filename, "navigation fails")
        self.assertTrue(result["fixed"])
        self.assertIn("https://real.example.com", result["new_block"])

    def test_matching_url_is_not_fixable(self):
        ctx = self._ctx(base_url="https://example.com")
        result = healing_tools._propose_navigation_fix(ctx, self.spec_filename, "navigation fails")
        self.assertFalse(result["fixed"])

    def test_no_configured_url_reports_reason(self):
        ctx = self._ctx(base_url="")
        result = healing_tools._propose_navigation_fix(ctx, self.spec_filename, "navigation fails")
        self.assertFalse(result["fixed"])
        self.assertIn("no configured url", result["reason"])


class ProposeTestDataFixTests(unittest.TestCase):
    def test_flags_stale_literal_not_in_expected_dataset(self):
        spec_content = """test.describe('S', () => {
  test('BS-001 fill form', async ({ page }) => {
    await page.locator('#email').fill('stale@example.com');
  });
});
"""
        tmp_dir = tempfile.mkdtemp()
        try:
            spec_filename = "test_BS-001_x.spec.ts"
            with open(os.path.join(tmp_dir, spec_filename), "w", encoding="utf-8") as f:
                f.write(spec_content)
            ctx = HealingRunContext(
                project_name="proj", scripts_dir=tmp_dir, reports_dir="",
                report_json="", dom_elements=[], module_urls={}, default_url="",
                test_data_map={"BS-001": {"positive_dataset": [
                    {"field_name": "email", "field_type": "text", "value": "fresh@example.com"},
                ]}},
                settings={}, logger=MagicMock(),
            )
            result = healing_tools._propose_test_data_fix(ctx, spec_filename, "BS-001 fill form")
            self.assertFalse(result["fixed"])
            self.assertIn("stale@example.com", result["stale_values"])
            self.assertEqual(result["expected_dataset"], {"email": "fresh@example.com"})
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


class ProposeCompilationFixTests(unittest.TestCase):
    def test_rewrites_deprecated_click_selector_call(self):
        block = "test('x', async ({ page }) => { await page.click('#submit'); });"
        ctx = HealingRunContext(
            project_name="proj", scripts_dir="", reports_dir="", report_json="",
            dom_elements=[], module_urls={}, default_url="", test_data_map={}, settings={}, logger=MagicMock(),
        )
        with patch.object(healing_tools, "_read_test_block", return_value=block):
            result = healing_tools._propose_compilation_fix(ctx, "s.spec.ts", "x")
        self.assertTrue(result["fixed"])
        self.assertIn("page.locator('#submit').click()", result["new_block"])

    def test_no_known_pattern_reports_unfixed(self):
        block = "test('x', async ({ page }) => { await page.locator('#a').click(); });"
        ctx = HealingRunContext(
            project_name="proj", scripts_dir="", reports_dir="", report_json="",
            dom_elements=[], module_urls={}, default_url="", test_data_map={}, settings={}, logger=MagicMock(),
        )
        with patch.object(healing_tools, "_read_test_block", return_value=block):
            result = healing_tools._propose_compilation_fix(ctx, "s.spec.ts", "x")
        self.assertFalse(result["fixed"])


class ApplyPatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.spec_filename = "test_x.spec.ts"
        self.spec_path = os.path.join(self.tmp_dir, self.spec_filename)
        with open(self.spec_path, "w", encoding="utf-8") as f:
            f.write(_SPEC_CONTENT)
        self.ctx = HealingRunContext(
            project_name="proj", scripts_dir=self.tmp_dir, reports_dir="",
            report_json="", dom_elements=[], module_urls={}, default_url="", test_data_map={},
            settings={}, logger=MagicMock(),
        )

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_rejects_structurally_invalid_block(self):
        result = healing_tools._apply_patch(self.ctx, self.spec_filename, "locator times out", "not a test block")
        self.assertFalse(result["applied"])
        self.assertEqual(self.ctx.tests_healed, 0)

    def test_applies_valid_block_and_updates_ctx(self):
        new_block = "test('locator times out', async ({ page }) => { await page.getByRole('button').click(); });"
        result = healing_tools._apply_patch(self.ctx, self.spec_filename, "locator times out", new_block)
        self.assertTrue(result["applied"])
        self.assertEqual(self.ctx.tests_healed, 1)
        self.assertIn(self.spec_filename, self.ctx.healed_specs)
        with open(self.spec_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("getByRole('button')", content)

    def test_missing_test_name_is_rejected(self):
        new_block = "test('does not exist', async ({ page }) => { await page.goto('/'); });"
        result = healing_tools._apply_patch(self.ctx, self.spec_filename, "does not exist", new_block)
        self.assertFalse(result["applied"])


class MarkNotHealableTests(unittest.TestCase):
    def test_removes_from_remaining_and_records_reason(self):
        ctx = HealingRunContext(
            project_name="proj", scripts_dir="", reports_dir="", report_json="",
            dom_elements=[], module_urls={}, default_url="", test_data_map={}, settings={}, logger=MagicMock(),
        )
        ctx.remaining = {"s.spec.ts": {"a": "err", "b": "err2"}}
        result = healing_tools._mark_not_healable(ctx, "s.spec.ts", "a", "real app defect")
        self.assertTrue(result["acknowledged"])
        self.assertNotIn("a", ctx.remaining.get("s.spec.ts", {}))
        self.assertEqual(len(ctx.not_healable), 1)
        self.assertEqual(ctx.not_healable[0]["reason"], "real app defect")

    def test_removing_last_test_drops_spec_key(self):
        ctx = HealingRunContext(
            project_name="proj", scripts_dir="", reports_dir="", report_json="",
            dom_elements=[], module_urls={}, default_url="", test_data_map={}, settings={}, logger=MagicMock(),
        )
        ctx.remaining = {"s.spec.ts": {"a": "err"}}
        healing_tools._mark_not_healable(ctx, "s.spec.ts", "a", "reason")
        self.assertNotIn("s.spec.ts", ctx.remaining)
        self.assertEqual(ctx.remaining_total(), 0)


class RunTestsTests(unittest.TestCase):
    def test_all_resolved_when_ui_execution_reports_all_passed(self):
        ctx = HealingRunContext(
            project_name="proj", scripts_dir="", reports_dir="", report_json="",
            dom_elements=[], module_urls={}, default_url="", test_data_map={}, settings={}, logger=MagicMock(),
        )
        ctx.remaining = {"M01/test_x.spec.ts": {"locator times out": "old error"}}

        fake_result = {
            "status": "success",
            "passed": 1, "failed": 0,
            "results": [{
                "spec_file": "application_assets/projects/proj/test_creation/test_scripts/M01/test_x.spec.ts",
                "test_title": "locator times out", "status": "success",
            }],
        }
        with patch("agents.test_execution.ui_execution.agent.UIExecutionAgent.execute", return_value=fake_result):
            result = healing_tools._run_tests(ctx, ["M01/test_x.spec.ts"])

        self.assertTrue(result["ran"])
        self.assertTrue(result["all_resolved"])
        self.assertEqual(ctx.remaining, {})

    def test_still_failing_test_stays_in_remaining_with_updated_error(self):
        ctx = HealingRunContext(
            project_name="proj", scripts_dir="", reports_dir="", report_json="",
            dom_elements=[], module_urls={}, default_url="", test_data_map={}, settings={}, logger=MagicMock(),
        )
        ctx.remaining = {"test_x.spec.ts": {"still broken": "old error"}}

        fake_result = {
            "status": "success",
            "passed": 0, "failed": 1,
            "results": [{"spec_file": "test_x.spec.ts", "test_title": "still broken",
                         "status": "failed", "errors": ["new error"]}],
        }
        with patch("agents.test_execution.ui_execution.agent.UIExecutionAgent.execute", return_value=fake_result):
            result = healing_tools._run_tests(ctx, ["test_x.spec.ts"])

        self.assertFalse(result["all_resolved"])
        self.assertEqual(ctx.remaining["test_x.spec.ts"]["still broken"], "new error")

    def test_ui_execution_failure_reports_not_ran(self):
        ctx = HealingRunContext(
            project_name="proj", scripts_dir="", reports_dir="", report_json="",
            dom_elements=[], module_urls={}, default_url="", test_data_map={}, settings={}, logger=MagicMock(),
        )
        ctx.remaining = {"test_x.spec.ts": {"a": "err"}}
        fake_result = {"status": "failed", "error": "playwright not installed"}
        with patch("agents.test_execution.ui_execution.agent.UIExecutionAgent.execute", return_value=fake_result):
            result = healing_tools._run_tests(ctx, ["test_x.spec.ts"])
        self.assertFalse(result["ran"])
        self.assertIn("test_x.spec.ts", [e["spec_file"] for e in result["still_failing"]])


# ── Round-history capture (per-iteration reporting) ────────────────────────────

class RunTestsRoundHistoryTests(unittest.TestCase):
    def _ctx(self):
        return HealingRunContext(
            project_name="proj", scripts_dir="", reports_dir="", report_json="",
            dom_elements=[], module_urls={}, default_url="", test_data_map={}, settings={}, logger=MagicMock(),
        )

    def test_run_tests_appends_round_record_on_success(self):
        ctx = self._ctx()
        ctx.remaining = {"M01/test_x.spec.ts": {"locator times out": "old error"}}
        fake_result = {
            "status": "success", "passed": 1, "failed": 0,
            "results": [{
                "spec_file": "application_assets/projects/proj/test_creation/test_scripts/M01/test_x.spec.ts",
                "test_title": "locator times out", "status": "success",
            }],
        }
        with patch("agents.test_execution.ui_execution.agent.UIExecutionAgent.execute", return_value=fake_result):
            healing_tools._run_tests(ctx, ["M01/test_x.spec.ts"])

        self.assertEqual(len(ctx.rounds), 1)
        record = ctx.rounds[0]
        self.assertEqual(record["round"], 1)
        self.assertEqual(record["spec_files"], ["M01/test_x.spec.ts"])
        self.assertTrue(record["ran"])
        self.assertEqual(record["passed"], 1)
        self.assertEqual(record["failed"], 0)
        self.assertEqual(record["remaining_after"], 0)

    def test_run_tests_appends_round_record_on_ui_execution_failure(self):
        ctx = self._ctx()
        ctx.remaining = {"test_x.spec.ts": {"a": "err"}}
        fake_result = {"status": "failed", "error": "playwright not installed"}
        with patch("agents.test_execution.ui_execution.agent.UIExecutionAgent.execute", return_value=fake_result):
            healing_tools._run_tests(ctx, ["test_x.spec.ts"])

        self.assertEqual(len(ctx.rounds), 1)
        record = ctx.rounds[0]
        self.assertEqual(record["round"], 1)
        self.assertFalse(record["ran"])
        self.assertEqual(record["error"], "playwright not installed")
        self.assertEqual(record["remaining_after"], 1)

    def test_multiple_run_tests_calls_produce_sequential_round_numbers(self):
        ctx = self._ctx()
        ctx.remaining = {
            "a.spec.ts": {"t1": "err"},
            "b.spec.ts": {"t2": "err"},
        }
        result1 = {
            "status": "success", "passed": 1, "failed": 0,
            "results": [{"spec_file": "a.spec.ts", "test_title": "t1", "status": "success"}],
        }
        result2 = {
            "status": "success", "passed": 0, "failed": 1,
            "results": [{"spec_file": "b.spec.ts", "test_title": "t2", "status": "failed", "errors": ["still broken"]}],
        }
        with patch("agents.test_execution.ui_execution.agent.UIExecutionAgent.execute", side_effect=[result1, result2]):
            healing_tools._run_tests(ctx, ["a.spec.ts"])
            healing_tools._run_tests(ctx, ["b.spec.ts"])

        self.assertEqual(len(ctx.rounds), 2)
        self.assertEqual(ctx.rounds[0]["round"], 1)
        self.assertEqual(ctx.rounds[1]["round"], 2)
        self.assertEqual(ctx.rounds[0]["spec_files"], ["a.spec.ts"])
        self.assertEqual(ctx.rounds[1]["spec_files"], ["b.spec.ts"])


# ── HealingAgent.execute() paths that don't require a live ADK/Gemini call ────

class HealingAgentExecuteFastPathsTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.spec_filename = "test_x.spec.ts"

        self.reports_dir = os.path.join(self.tmp_dir, "proj", "test_execution", "reports", "json")
        os.makedirs(self.reports_dir, exist_ok=True)

        self._assets_patch = patch("agents.test_execution.healing.agent._ASSETS_BASE", self.tmp_dir)
        self._assets_patch.start()

        from agents.test_execution.healing.agent import HealingAgent
        self.agent = HealingAgent(settings={})
        self.agent._log = MagicMock()

    def tearDown(self):
        self._assets_patch.stop()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_no_report_returns_failed_status(self):
        result = self.agent.execute({"project_name": "proj"}, {})
        self.assertEqual(result["status"], "failed")
        self.assertIn("error", result)

    def test_no_failing_tests_short_circuits_without_adk(self):
        report_path = os.path.join(self.reports_dir, "20260101_000000_results.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump({"suites": [{"specs": [{
                "file": "test_creation/test_scripts/test_x.spec.ts",
                "title": "passes",
                "tests": [{"status": "passed", "results": []}],
            }]}]}, f)

        with patch("agents.test_execution.healing.agent.HealingAgent._run_adk_healing") as mock_run:
            result = self.agent.execute({"project_name": "proj"}, {})
        mock_run.assert_not_called()
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["tests_healed"], 0)

    def test_unresolvable_connector_mode_returns_failed_without_adk(self):
        report_path = os.path.join(self.reports_dir, "20260101_000000_results.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(_report(self.spec_filename), f)

        self.agent.settings = {"connectors": {"llm": "internal"}}
        with patch("agents.test_execution.healing.agent.HealingAgent._run_adk_healing") as mock_run:
            result = self.agent.execute({"project_name": "proj"}, {})
        mock_run.assert_not_called()
        self.assertEqual(result["status"], "failed")
        self.assertIn("internal", result["error"])

    def test_adk_exception_is_caught_and_reported_as_failed(self):
        report_path = os.path.join(self.reports_dir, "20260101_000000_results.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(_report(self.spec_filename), f)

        with patch(
            "agents.test_execution.healing.agent.HealingAgent._run_adk_healing",
            side_effect=RuntimeError("adk boom"),
        ):
            result = self.agent.execute({"project_name": "proj"}, {})
        self.assertEqual(result["status"], "failed")
        self.assertIn("adk boom", result["error"])

    def test_adk_exception_preserves_ctx_progress_in_returned_dict(self):
        """The key regression test: a crash mid-loop must not discard whatever
        real progress (patches applied, rounds verified) already happened."""
        report_path = os.path.join(self.reports_dir, "20260101_000000_results.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(_report(self.spec_filename), f)

        def _crash_after_progress(ctx, model, max_iterations):
            ctx.tests_healed = 1
            ctx.healed_specs.add(self.spec_filename)
            ctx.rounds.append({
                "round": 1, "spec_files": [self.spec_filename], "ran": True,
                "passed": 1, "failed": 1, "remaining_after": 1,
            })
            ctx.remaining = {self.spec_filename: {"still broken": "err"}}
            raise RuntimeError("boom")

        with patch(
            "agents.test_execution.healing.agent.HealingAgent._run_adk_healing",
            side_effect=_crash_after_progress,
        ):
            result = self.agent.execute({"project_name": "proj"}, {})

        self.assertEqual(result["status"], "failed")
        self.assertIn("boom", result["error"])
        self.assertEqual(result["tests_healed"], 1)
        self.assertEqual(result["specs_healed"], 1)
        self.assertEqual(len(result["rounds"]), 1)
        self.assertEqual(result["remaining_failing_count"], 1)

    def test_success_path_returns_rounds_and_remaining_failing_count(self):
        report_path = os.path.join(self.reports_dir, "20260101_000000_results.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(_report(self.spec_filename), f)

        def _succeed(ctx, model, max_iterations):
            ctx.tests_healed = 2
            ctx.healed_specs.add(self.spec_filename)
            ctx.rounds.append({
                "round": 1, "spec_files": [self.spec_filename], "ran": True,
                "passed": 2, "failed": 0, "remaining_after": 0,
            })
            ctx.remaining = {}

        with patch(
            "agents.test_execution.healing.agent.HealingAgent._run_adk_healing",
            side_effect=_succeed,
        ):
            result = self.agent.execute({"project_name": "proj"}, {})

        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["rounds"]), 1)
        self.assertEqual(result["remaining_failing_count"], 0)


# ── UIExecutionAgent spec_files targeting (new, additive branch) ──────────────

class UIExecutionSpecFilesTests(unittest.TestCase):
    def test_spec_files_routes_to_run_playwright_with_expected_args(self):
        from agents.test_execution.ui_execution.agent import UIExecutionAgent

        agent = UIExecutionAgent(settings={})
        agent._log = MagicMock()
        agent._run_playwright = MagicMock(return_value={"module": "ui_execution", "status": "success"})

        agent.execute({"project_name": "proj", "spec_files": ["M01/test_x.spec.ts"]}, {})

        agent._run_playwright.assert_called_once()
        _, kwargs = agent._run_playwright.call_args
        self.assertEqual(kwargs["ts_files"], ["M01/test_x.spec.ts"])
        self.assertTrue(kwargs["spec_files"][0].endswith("M01/test_x.spec.ts"))


if __name__ == "__main__":
    unittest.main()
