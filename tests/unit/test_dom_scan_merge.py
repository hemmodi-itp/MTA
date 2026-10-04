import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.discovery.dom_scan import assign_stable_locator_ids, merge_elements
from tools.state.artifact_registry import ArtifactRegistry


def _el(tag="input", role=None, elem_id=None, name=None, testid=None, display_text="",
        aria_label=None, css=None):
    return {
        "tag": tag,
        "display_text": display_text,
        "semantic_locators": {"role": role, "aria_label": aria_label},
        "attribute_locators": {"id": elem_id, "name": name, "testid": testid},
        "playwright_locators": {},
        "technical_locators": {"css": css if css is not None else (f"#{elem_id}" if elem_id else "")},
        "recommended_locator": {},
        "quality": {"visible": True, "enabled": True},
        "intent_hints": [],
    }


class AssignStableLocatorIdsTests(unittest.TestCase):
    def test_same_identity_gets_same_id_across_two_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry1 = ArtifactRegistry(tmp)
            stamped1 = assign_stable_locator_ids([_el(elem_id="login")], "M01", registry1)
            registry1.save()

            registry2 = ArtifactRegistry(tmp)  # simulates a fresh process/rescan
            stamped2 = assign_stable_locator_ids([_el(elem_id="login")], "M01", registry2)

            self.assertEqual(stamped1[0]["locator_id"], stamped2[0]["locator_id"])

    def test_reordered_scan_does_not_reassign_ids(self):
        # The bug being fixed: a bare per-scan counter reassigns ids when
        # element order shifts (e.g. an element earlier in the DOM vanishes).
        with tempfile.TemporaryDirectory() as tmp:
            registry = ArtifactRegistry(tmp)
            first_scan = [_el(elem_id="a"), _el(elem_id="b")]
            stamped_first = assign_stable_locator_ids(first_scan, "M01", registry)
            registry.save()
            b_id = stamped_first[1]["locator_id"]

            registry2 = ArtifactRegistry(tmp)
            reordered_scan = [_el(elem_id="b")]  # "a" disappeared, "b" is now first
            stamped_second = assign_stable_locator_ids(reordered_scan, "M01", registry2)

            self.assertEqual(stamped_second[0]["locator_id"], b_id)

    def test_different_elements_get_different_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = ArtifactRegistry(tmp)
            stamped = assign_stable_locator_ids([_el(elem_id="a"), _el(elem_id="b")], "M01", registry)
            self.assertNotEqual(stamped[0]["locator_id"], stamped[1]["locator_id"])

    def test_same_tag_and_role_but_different_aria_label_get_different_ids(self):
        # The real geminiTest bug: 6 icon-only buttons (mic, TTS toggle, avatar
        # footer x2, input menu, side-nav toggle) all share tag="button",
        # role="button", and blank id/name/testid/display_text — only their
        # aria-label actually distinguishes them. Before the fix, tag+role
        # alone were treated as "durable" identity and all 6 collapsed onto
        # one locator_id.
        with tempfile.TemporaryDirectory() as tmp:
            registry = ArtifactRegistry(tmp)
            mic = _el(tag="button", role="button", aria_label="Microphone", css="div>button:nth-of-type(1)")
            tts = _el(tag="button", role="button", aria_label="Read aloud", css="div>button:nth-of-type(2)")
            stamped = assign_stable_locator_ids([mic, tts], "M01", registry)
            self.assertNotEqual(stamped[0]["locator_id"], stamped[1]["locator_id"])

    def test_same_tag_and_role_with_no_durable_signal_falls_back_to_css(self):
        # Two genuinely anonymous same-tag/role elements (no id/name/testid/
        # aria_label/display_text at all) — the only remaining distinguisher
        # is CSS position, which is still strictly better than colliding both
        # onto the same identity.
        with tempfile.TemporaryDirectory() as tmp:
            registry = ArtifactRegistry(tmp)
            a = _el(tag="div", role=None, css="div:nth-of-type(1)")
            b = _el(tag="div", role=None, css="div:nth-of-type(2)")
            stamped = assign_stable_locator_ids([a, b], "M01", registry)
            self.assertNotEqual(stamped[0]["locator_id"], stamped[1]["locator_id"])

    def test_truly_identical_anonymous_elements_still_collide(self):
        # Not a bug: two elements with zero distinguishing data of any kind
        # (same tag/role, same — or blank — CSS) are indistinguishable by
        # definition; this documents that floor rather than asserting
        # uniqueness that isn't possible to derive.
        with tempfile.TemporaryDirectory() as tmp:
            registry = ArtifactRegistry(tmp)
            a = _el(tag="div", role=None, css="")
            b = _el(tag="div", role=None, css="")
            stamped = assign_stable_locator_ids([a, b], "M01", registry)
            self.assertEqual(stamped[0]["locator_id"], stamped[1]["locator_id"])


class MergeElementsTests(unittest.TestCase):
    def test_unchanged_element_is_left_as_is(self):
        el = dict(_el(elem_id="a"), locator_id="LOC-0001")
        result = merge_elements([el], [dict(el)])
        self.assertEqual(result["elements"], [el])
        self.assertEqual(result["added"], [])
        self.assertEqual(result["updated"], [])
        self.assertEqual(result["possibly_removed"], [])

    def test_changed_content_updates_in_place(self):
        old = dict(_el(elem_id="a"), locator_id="LOC-0001")
        new = dict(_el(elem_id="a", display_text="Now visible"), locator_id="LOC-0001")
        result = merge_elements([old], [new])
        self.assertEqual(len(result["elements"]), 1)
        self.assertEqual(result["elements"][0]["display_text"], "Now visible")
        self.assertEqual(result["updated"], ["LOC-0001"])

    def test_new_element_is_appended(self):
        existing = [dict(_el(elem_id="a"), locator_id="LOC-0001")]
        fresh = [dict(_el(elem_id="a"), locator_id="LOC-0001"), dict(_el(elem_id="b"), locator_id="LOC-0002")]
        result = merge_elements(existing, fresh)
        self.assertEqual(len(result["elements"]), 2)
        self.assertEqual(result["added"], ["LOC-0002"])

    def test_missing_element_is_kept_never_deleted(self):
        existing = [dict(_el(elem_id="a"), locator_id="LOC-0001"), dict(_el(elem_id="b"), locator_id="LOC-0002")]
        fresh = [dict(_el(elem_id="a"), locator_id="LOC-0001")]  # "b" no longer scanned
        result = merge_elements(existing, fresh)
        ids = {e["locator_id"] for e in result["elements"]}
        self.assertEqual(ids, {"LOC-0001", "LOC-0002"})
        self.assertEqual(result["possibly_removed"], ["LOC-0002"])

    def test_never_produces_duplicate_ids(self):
        existing = [dict(_el(elem_id="a"), locator_id="LOC-0001")]
        fresh = [dict(_el(elem_id="a"), locator_id="LOC-0001")]
        result = merge_elements(existing, fresh)
        ids = [e["locator_id"] for e in result["elements"]]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
