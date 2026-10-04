import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.test_creation.script_generator.spec_renderer import (
    render_flows_module,
    render_spec_from_plan,
)

_SCENARIO = {"scenario_id": "M01_BS_001", "title": "Standard login"}
_SPEC_REL_PATH = "projects/demo/test_creation/test_scripts/M01/test_M01_BS_001_standard_login.spec.ts"


def _plan(tests):
    return {"tests": tests, "missing_actions": [], "missing_locators": []}


class RenderSpecFromPlanTests(unittest.TestCase):
    def test_basic_click_and_verify_renders_action_calls(self):
        plan = _plan([{
            "name": "positive — logs in",
            "type": "positive",
            "steps": [
                {"action": "enterText", "locator_key": "username_input", "value": "bob"},
                {"action": "click", "locator_key": "login_button"},
                {"action": "verifyVisible", "locator_key": "welcome_banner", "message": "shows welcome"},
            ],
        }])
        content = render_spec_from_plan(plan, _SCENARIO, "https://x.com", _SPEC_REL_PATH)

        self.assertIn("await action.enterText(\"username_input\", \"bob\");", content)
        self.assertIn("await action.click(\"login_button\");", content)
        self.assertIn('await action.verifyVisible("welcome_banner", "shows welcome");', content)
        self.assertIn("test.describe(", content)
        self.assertNotIn("page.getBy", content)  # no raw Playwright locator calls

    def test_positive_test_gets_smoke_tag_negative_gets_regression_tag(self):
        plan = _plan([
            {"name": "positive — happy path", "type": "positive", "steps": [{"action": "navigate"}]},
            {"name": "negative — bad input", "type": "negative", "steps": [{"action": "navigate"}]},
            {"name": "boundary — max length", "type": "boundary", "steps": [{"action": "navigate"}]},
        ])
        content = render_spec_from_plan(plan, _SCENARIO, "https://x.com", _SPEC_REL_PATH)

        self.assertIn("positive — happy path @smoke", content)
        self.assertIn("negative — bad input @regression", content)
        self.assertIn("boundary — max length @regression", content)

    def test_soft_flag_renders_soft_true_option(self):
        plan = _plan([{
            "name": "positive — x", "type": "positive",
            "steps": [{"action": "verifyValue", "locator_key": "field", "value": "x", "message": "m", "soft": True}],
        }])
        content = render_spec_from_plan(plan, _SCENARIO, "https://x.com", _SPEC_REL_PATH)
        self.assertIn("{ soft: true }", content)

    def test_verify_url_contains_and_title_contains_have_no_locator_argument(self):
        # The real geminiTest bug these two exist for: the app redirects "/"
        # -> "/app" and renders the title as "Google Gemini" instead of
        # "Gemini" — an exact verifyUrl/verifyTitle chases a moving target
        # that isn't the meaningful assertion; these render as page-level
        # calls with no locator_key, same shape as verifyUrl/verifyTitle.
        plan = _plan([{
            "name": "positive — x", "type": "positive",
            "steps": [
                {"action": "verifyUrlContains", "value": "/app", "message": "reached the app"},
                {"action": "verifyTitleContains", "value": "Gemini", "message": "title mentions Gemini"},
            ],
        }])
        content = render_spec_from_plan(plan, _SCENARIO, "https://x.com", _SPEC_REL_PATH)
        self.assertIn('await action.verifyUrlContains("/app", "reached the app");', content)
        self.assertIn('await action.verifyTitleContains("Gemini", "title mentions Gemini");', content)

    def test_verify_no_page_errors_has_no_locator_argument(self):
        plan = _plan([{
            "name": "positive — x", "type": "positive",
            "steps": [{"action": "verifyNoPageErrors", "message": "no errors"}],
        }])
        content = render_spec_from_plan(plan, _SCENARIO, "https://x.com", _SPEC_REL_PATH)
        self.assertIn('await action.verifyNoPageErrors("no errors");', content)

    def test_press_key_with_null_locator_renders_null(self):
        plan = _plan([{
            "name": "positive — x", "type": "positive",
            "steps": [{"action": "pressKey", "locator_key": None, "value": "Escape"}],
        }])
        content = render_spec_from_plan(plan, _SCENARIO, "https://x.com", _SPEC_REL_PATH)
        self.assertIn("await action.pressKey(null, \"Escape\");", content)

    def test_drag_and_drop_renders_both_keys(self):
        plan = _plan([{
            "name": "positive — x", "type": "positive",
            "steps": [{"action": "dragAndDrop", "locator_key": "src", "target_locator_key": "dst"}],
        }])
        content = render_spec_from_plan(plan, _SCENARIO, "https://x.com", _SPEC_REL_PATH)
        self.assertIn('await action.dragAndDrop("src", "dst");', content)

    def test_use_flow_renders_flows_call_and_imports_flows_module(self):
        plan = _plan([{
            "name": "positive — x", "type": "positive",
            "steps": [{"action": "useFlow", "flow": "login", "args": {"username": "u", "password": "p"}}],
        }])
        content = render_spec_from_plan(
            plan, _SCENARIO, "https://x.com", _SPEC_REL_PATH,
            project="demo", flows_meta={"login": ["username", "password"]},
        )
        self.assertIn("await flows.login(action, \"u\", \"p\");", content)
        self.assertIn("import * as flows from", content)

    def test_use_flow_without_project_raises(self):
        plan = _plan([{
            "name": "positive — x", "type": "positive",
            "steps": [{"action": "useFlow", "flow": "login", "args": {}}],
        }])
        with self.assertRaises(ValueError):
            render_spec_from_plan(plan, _SCENARIO, "https://x.com", _SPEC_REL_PATH, flows_meta={"login": []})

    def test_no_flows_used_means_no_flows_import(self):
        plan = _plan([{"name": "positive — x", "type": "positive", "steps": [{"action": "navigate"}]}])
        content = render_spec_from_plan(plan, _SCENARIO, "https://x.com", _SPEC_REL_PATH)
        self.assertNotIn("import * as flows", content)

    def test_import_is_extensionless(self):
        plan = _plan([{"name": "positive — x", "type": "positive", "steps": [{"action": "navigate"}]}])
        content = render_spec_from_plan(plan, _SCENARIO, "https://x.com", _SPEC_REL_PATH)
        self.assertIn("testFixture';", content)
        self.assertNotIn("testFixture.js';", content)


class RenderFlowsModuleTests(unittest.TestCase):
    def test_renders_one_exported_function_per_flow(self):
        flows = {
            "login": {
                "params": ["username", "password"],
                "steps": [
                    {"action": "enterText", "locator_key": "username_input", "value": "{{username}}"},
                    {"action": "enterText", "locator_key": "password_input", "value": "{{password}}"},
                    {"action": "click", "locator_key": "login_button"},
                ],
            }
        }
        content = render_flows_module(flows, "demo")
        self.assertIn(
            "export async function login(action: ActionEngine, username: string, password: string): Promise<void> {",
            content,
        )
        # template params render as raw identifiers, not quoted literals
        self.assertIn("await action.enterText(\"username_input\", username);", content)
        self.assertIn("await action.enterText(\"password_input\", password);", content)
        self.assertNotIn('"{{username}}"', content)


if __name__ == "__main__":
    unittest.main()
