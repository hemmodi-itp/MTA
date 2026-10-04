import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.playwright_scanner import _resolve_display_name, _demote_duplicate_role_candidates


class ResolveDisplayNameTests(unittest.TestCase):
    """The real geminiTest bug: icon-only buttons (mic, TTS toggle, avatar
    footer, input menu) have no inner text, so display_text/get_by_role name
    ended up blank — collapsing 6 distinct buttons onto one generic
    locator_id and forcing a fragile full-ancestor-chain CSS selector with an
    empty description. This is the fallback chain that fixes it."""

    def test_visible_text_wins_over_everything(self):
        self.assertEqual(_resolve_display_name("Sign in", "aria", "label", "title"), "Sign in")

    def test_falls_back_to_aria_label_when_text_is_blank(self):
        self.assertEqual(_resolve_display_name("", "Microphone", "", ""), "Microphone")

    def test_falls_back_to_associated_label_when_text_and_aria_are_blank(self):
        self.assertEqual(_resolve_display_name("", "", "Email address", ""), "Email address")

    def test_falls_back_to_title_as_last_resort(self):
        self.assertEqual(_resolve_display_name("", "", "", "Close dialog"), "Close dialog")

    def test_all_blank_returns_blank(self):
        self.assertEqual(_resolve_display_name("", "", "", ""), "")


def _el_with_role(role: str, name: str, extra_candidates=None):
    role_locator = {"get_by_role": {"role": role, "name": name}} if name else {}
    candidates = [{"type": "role", "value": {"role": role, "name": name}, "score": 110, "unique": True, "match_count": 1}]
    if extra_candidates:
        candidates = extra_candidates + candidates
    return {
        "playwright_locators": role_locator,
        "locator_candidates": list(candidates),
        "recommended_locator": candidates[0],
    }


class DemoteDuplicateRoleCandidatesTests(unittest.TestCase):
    """The real SC-001/SC-003 failures: two elements share the same
    accessible (role, name) pair (a text 'Sign in' button + an icon 'Sign in'
    button shown responsively) — Playwright correctly refuses to guess which
    one a bare get_by_role locator means (strict mode violation). This
    demotes the ambiguous role candidate so a durable alternative wins."""

    def test_unique_role_name_pair_is_left_alone(self):
        elements = [_el_with_role("button", "Sign in")]
        _demote_duplicate_role_candidates(elements)
        self.assertTrue(elements[0]["locator_candidates"][0]["unique"])
        self.assertEqual(elements[0]["recommended_locator"]["type"], "role")

    def test_duplicate_role_name_pair_is_demoted_below_a_durable_alternative(self):
        testid_candidate = {"type": "testid", "value": {"testid": "sign-in-icon"}, "score": 150, "unique": True, "match_count": 1}
        el_a = _el_with_role("button", "Sign in", extra_candidates=[testid_candidate])
        el_b = _el_with_role("button", "Sign in")
        elements = [el_a, el_b]
        _demote_duplicate_role_candidates(elements)

        for el in elements:
            role_candidate = next(c for c in el["locator_candidates"] if c["type"] == "role")
            self.assertFalse(role_candidate["unique"])
            self.assertEqual(role_candidate["match_count"], 2)

        # el_a has a durable testid candidate that now outranks its demoted role candidate
        self.assertEqual(el_a["recommended_locator"]["type"], "testid")

    def test_duplicate_with_no_alternative_falls_back_to_role_anyway(self):
        # Worse than nothing to drop the only candidate — still recommend it,
        # just correctly flagged as non-unique for downstream consumers.
        elements = [_el_with_role("link", "Gemini"), _el_with_role("link", "Gemini")]
        _demote_duplicate_role_candidates(elements)
        for el in elements:
            self.assertEqual(el["recommended_locator"]["type"], "role")
            self.assertFalse(el["recommended_locator"]["unique"])

    def test_elements_without_a_role_locator_are_untouched(self):
        el = {"playwright_locators": {}, "locator_candidates": [], "recommended_locator": {}}
        _demote_duplicate_role_candidates([el])
        self.assertEqual(el["locator_candidates"], [])


if __name__ == "__main__":
    unittest.main()
