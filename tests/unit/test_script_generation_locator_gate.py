import os
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.test_creation.script_generation.agent import ScriptGenerationAgent


class ValidateLocatorMapLiveTests(unittest.TestCase):
    """execute()'s locator_map validation now runs once per project per
    module (not once per scenario) — a key that fails to resolve must be
    excluded from that module's allowed_locators and reported, without
    blocking the whole run."""

    def setUp(self):
        self.agent = ScriptGenerationAgent(settings={})

    def _run(self, locator_map, page):
        with patch.object(ScriptGenerationAgent, "_get_validation_page", return_value=(None, page)):
            with patch("agents.test_creation.script_generation.agent.record_locator_drift") as drift:
                unresolvable = self.agent._validate_locator_map_live(
                    "proj", "proj", locator_map, "https://example.com", {}, {},
                )
        return unresolvable, drift

    def test_dead_key_is_reported_and_excluded(self):
        locator_map = {
            "login_button": {"type": "css", "locator": "#login", "_module_id": "M01"},
            "ghost_field": {"type": "placeholder", "locator": "Ghost", "_module_id": "M01"},
        }
        page = MagicMock()
        page.locator.return_value.count.return_value = 1
        page.get_by_placeholder.return_value.count.return_value = 0

        unresolvable, drift = self._run(locator_map, page)

        self.assertEqual(unresolvable, {"ghost_field"})
        drift.assert_called_once()
        self.assertEqual(drift.call_args.kwargs["possibly_removed"], ["ghost_field"])

    def test_all_keys_resolving_reports_nothing(self):
        locator_map = {"login_button": {"type": "css", "locator": "#login", "_module_id": "M01"}}
        page = MagicMock()
        page.locator.return_value.count.return_value = 1

        unresolvable, drift = self._run(locator_map, page)

        self.assertEqual(unresolvable, set())
        drift.assert_not_called()

    def test_no_validation_page_available_skips_module_entirely(self):
        # e.g. Chromium not installed — must not treat every key as dead.
        locator_map = {"login_button": {"type": "css", "locator": "#login", "_module_id": "M01"}}

        unresolvable, drift = self._run(locator_map, None)

        self.assertEqual(unresolvable, set())
        drift.assert_not_called()

    def test_one_browser_launch_per_module_not_per_key(self):
        locator_map = {
            "a": {"type": "css", "locator": "#a", "_module_id": "M01"},
            "b": {"type": "css", "locator": "#b", "_module_id": "M01"},
            "c": {"type": "css", "locator": "#c", "_module_id": "M02"},
        }
        page = MagicMock()
        page.locator.return_value.count.return_value = 1

        with patch.object(
            ScriptGenerationAgent, "_get_validation_page", return_value=(None, page)
        ) as get_page:
            with patch("agents.test_creation.script_generation.agent.record_locator_drift"):
                self.agent._validate_locator_map_live(
                    "proj", "proj", locator_map, "https://example.com", {}, {},
                )

        self.assertEqual(get_page.call_count, 2)  # one per module, not per key


if __name__ == "__main__":
    unittest.main()
