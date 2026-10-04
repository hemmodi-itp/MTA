import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.discovery.interactive_dom_scan import promote_checkpoint


def _checkpoint_with_data():
    return {
        "status": "in_progress",
        "base_url": "https://app.example/dashboard",
        "pages": [],
        "current_path": "/dashboard",
        "current_page_elements": [
            {
                "locator_id": "LOC-0001", "page_id": "PAGE-001",
                "blast_radius_source": None, "blast_radius_score": None,
                "tag": "button",
                "technical_locators": {"css": "#submit"},
                "playwright_locators": {}, "semantic_locators": {}, "attribute_locators": {},
                "recommended_locator": {"type": "id", "value": {"id": "submit"}, "score": 90, "unique": True},
                "quality": {"visible": True, "enabled": True},
                "intent_hints": [],
            }
        ],
        "current_page_clicks": ["LOC-0001"],
        "all_click_events": [
            {"css": "#submit", "tag": "button", "display_text": "Submit", "ts_ms": 1000,
             "seq": 1, "page_id": "PAGE-001", "page_path": "/dashboard", "locator_id": "LOC-0001"}
        ],
        "all_api_calls": [],
        "all_page_transitions": [],
        "loc_counter": 2,
        "page_counter": 1,
        "global_seq": 1,
    }


def _empty_checkpoint():
    return {
        "status": "in_progress",
        "base_url": "https://app.example/dashboard",
        "pages": [],
        "current_path": "/dashboard",
        "current_page_elements": [],
        "current_page_clicks": [],
        "all_click_events": [],
        "all_api_calls": [],
        "all_page_transitions": [],
        "loc_counter": 1,
        "page_counter": 1,
        "global_seq": 0,
    }


class PromoteCheckpointTests(unittest.TestCase):
    """A recording abandoned before scan_interactive() returns cleanly (the
    original M04 failure mode) must still produce usable output — promote_checkpoint
    rebuilds it from the same checkpoint _flush_checkpoint() already writes,
    reusing InteractiveScanner._restore_from_checkpoint/_build_result rather
    than a new persistence mechanism."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        # Mirrors real usage: DiscoveryAgent._read_recorded_scan always places
        # the checkpoint inside the same (module-scoped) dir it promotes into.
        self.output_dir = os.path.join(self.tmp_dir, "modules", "M04")
        self.checkpoint_path = os.path.join(self.output_dir, ".scan_checkpoint.json")

    def _write_checkpoint(self, data):
        os.makedirs(self.output_dir, exist_ok=True)
        with open(self.checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_returns_none_when_no_checkpoint_file(self):
        result = promote_checkpoint(
            checkpoint_path=self.checkpoint_path, url="https://x", project_name="proj",
            output_dir=self.output_dir,
        )
        self.assertIsNone(result)

    def test_returns_none_when_checkpoint_captured_nothing(self):
        self._write_checkpoint(_empty_checkpoint())

        result = promote_checkpoint(
            checkpoint_path=self.checkpoint_path, url="https://x", project_name="proj",
            output_dir=self.output_dir,
        )

        self.assertIsNone(result)

    def test_promotes_captured_checkpoint_to_final_artifacts(self):
        self._write_checkpoint(_checkpoint_with_data())

        result = promote_checkpoint(
            checkpoint_path=self.checkpoint_path, url="https://app.example/dashboard",
            project_name="proj", output_dir=self.output_dir,
        )

        self.assertIsNotNone(result)
        self.assertTrue(os.path.exists(result["dom_elements"]))
        self.assertTrue(os.path.exists(result["dom_intents"]))

        with open(result["dom_elements"], encoding="utf-8") as f:
            elements_doc = json.load(f)
        self.assertEqual(elements_doc["scan_mode"], "interactive")
        self.assertGreaterEqual(elements_doc["total_element_count"], 1)

        session_path = os.path.join(self.output_dir, "interactive", "session.json")
        flows_path = os.path.join(self.output_dir, "interactive", "user_flows.json")
        self.assertTrue(os.path.exists(session_path))
        self.assertTrue(os.path.exists(flows_path))

    def test_returns_none_for_corrupt_checkpoint(self):
        os.makedirs(self.output_dir, exist_ok=True)
        with open(self.checkpoint_path, "w", encoding="utf-8") as f:
            f.write("{not valid json")

        result = promote_checkpoint(
            checkpoint_path=self.checkpoint_path, url="https://x", project_name="proj",
            output_dir=self.output_dir,
        )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
