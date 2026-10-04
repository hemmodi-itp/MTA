import os
import sys
import unittest
from unittest.mock import MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.interactive_scanner import InteractiveScanner, _blast_radius_score, _BLAST_SCORE_THRESHOLD


class ScanCurrentPageBlastRadiusSchemaTests(unittest.TestCase):
    """_scan_current_page (the initial full-page sweep) and _scan_blast_radius
    (triggered per click) must produce elements with the SAME keys — a prior
    asymmetry meant only blast-radius-discovered elements had a
    blast_radius_score key, forcing every downstream reader to use a
    defensive .get(). Both paths must now always set both keys."""

    def setUp(self):
        self.scanner = InteractiveScanner(browser_name="chromium")

    def test_scan_current_page_sets_blast_radius_score_key(self):
        fake_page = MagicMock()
        fake_handle = MagicMock()
        fake_page.query_selector_all.side_effect = lambda sel: [fake_handle] if sel == "button" else []
        self.scanner._get_element_data = MagicMock(return_value={"technical_locators": {"css": "#btn"}})

        elements = self.scanner._scan_current_page(fake_page)

        self.assertEqual(len(elements), 1)
        self.assertIn("blast_radius_score", elements[0])
        self.assertIsNone(elements[0]["blast_radius_score"])
        self.assertIn("blast_radius_source", elements[0])
        self.assertIsNone(elements[0]["blast_radius_source"])

    def test_scan_blast_radius_sets_the_same_two_keys(self):
        fake_page = MagicMock()
        fake_page.evaluate.return_value = {"css": "form#login", "containerTag": "form"}
        fake_handle = MagicMock()
        fake_page.query_selector_all.side_effect = lambda sel: [fake_handle] if sel.endswith(" input") else []
        self.scanner._get_element_data = MagicMock(return_value={"technical_locators": {"css": "#username"}})

        elements = self.scanner._scan_blast_radius(fake_page, click_css="#login-btn", clicked_loc_id="LOC-0001")

        self.assertEqual(len(elements), 1)
        self.assertIn("blast_radius_score", elements[0])
        self.assertIn("blast_radius_source", elements[0])
        self.assertEqual(elements[0]["blast_radius_source"], "LOC-0001")
        # form scores 0.90, well above the 0.50 threshold used to gate inclusion
        self.assertGreater(elements[0]["blast_radius_score"], _BLAST_SCORE_THRESHOLD)


class BlastRadiusScoreFunctionTests(unittest.TestCase):
    """Direct coverage of the scoring table referenced by the schema tests
    above — form/dialog containers clear the threshold, broad regions don't."""

    def test_form_container_clears_threshold(self):
        self.assertGreater(_blast_radius_score("form", "input", "button"), _BLAST_SCORE_THRESHOLD)

    def test_main_container_stays_below_threshold(self):
        self.assertLessEqual(_blast_radius_score("main", "input", "button"), _BLAST_SCORE_THRESHOLD)

    def test_unknown_container_stays_below_threshold(self):
        self.assertLessEqual(_blast_radius_score("", "input", "button"), _BLAST_SCORE_THRESHOLD)


if __name__ == "__main__":
    unittest.main()
