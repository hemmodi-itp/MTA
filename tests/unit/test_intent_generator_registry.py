import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.intent_generator import (
    generate_intent_suggestions,
    generate_intent_suggestions_multipage,
)
from tools.state.artifact_registry import ArtifactRegistry


def _button(text):
    return {"tag": "button", "display_text": text}


class GenerateIntentSuggestionsRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def test_without_registry_behaves_like_before(self):
        result = generate_intent_suggestions("home", [_button("Submit")])
        self.assertEqual(result["intents"][0]["intent_id"], "INT-001")

    def test_rescan_of_same_elements_reuses_intent_ids(self):
        registry = ArtifactRegistry(self.tmp_dir)
        first_scan = generate_intent_suggestions(
            "home", [_button("Submit"), _button("Cancel")], registry=registry
        )
        registry.save()

        registry_2 = ArtifactRegistry(self.tmp_dir)
        second_scan = generate_intent_suggestions(
            "home", [_button("Submit"), _button("Cancel")], registry=registry_2
        )

        first_ids = {i["intent_name"]: i["intent_id"] for i in first_scan["intents"]}
        second_ids = {i["intent_name"]: i["intent_id"] for i in second_scan["intents"]}
        self.assertEqual(first_ids, second_ids)

    def test_new_element_on_rescan_gets_new_id_without_disturbing_existing_ones(self):
        registry = ArtifactRegistry(self.tmp_dir)
        first_scan = generate_intent_suggestions("home", [_button("Submit")], registry=registry)
        submit_id = first_scan["intents"][0]["intent_id"]
        registry.save()

        registry_2 = ArtifactRegistry(self.tmp_dir)
        second_scan = generate_intent_suggestions(
            "home", [_button("Submit"), _button("New Button")], registry=registry_2
        )
        by_name = {i["intent_name"]: i["intent_id"] for i in second_scan["intents"]}

        self.assertEqual(by_name["click_submit"], submit_id)
        self.assertNotEqual(by_name["click_new_button"], submit_id)


class MultipageRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def test_same_intent_name_on_different_pages_gets_distinct_ids(self):
        registry = ArtifactRegistry(self.tmp_dir)
        pages = [
            {"page_id": "PAGE-001", "page_name": "Home", "elements": [_button("Submit")]},
            {"page_id": "PAGE-002", "page_name": "Checkout", "elements": [_button("Submit")]},
        ]
        result = generate_intent_suggestions_multipage(pages, registry=registry)
        ids = [i["intent_id"] for i in result["intents"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_rescan_reuses_ids_per_page(self):
        registry = ArtifactRegistry(self.tmp_dir)
        pages = [{"page_id": "PAGE-001", "page_name": "Home", "elements": [_button("Submit")]}]
        first = generate_intent_suggestions_multipage(pages, registry=registry)
        registry.save()

        registry_2 = ArtifactRegistry(self.tmp_dir)
        second = generate_intent_suggestions_multipage(pages, registry=registry_2)

        self.assertEqual(first["intents"][0]["intent_id"], second["intents"][0]["intent_id"])


if __name__ == "__main__":
    unittest.main()
