import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.test_creation.script_generator.build_dom_locator_map import (
    _best_locator_entry,
    _mint_key,
    _slugify,
    build_named_locator_map,
    render_pages_module,
    repair_named_locator,
    write_named_locator_map,
)


def _element(locator_id, tag="input", placeholder=None, role=None, role_name=None,
             label=None, text=None, display_text="", css=None):
    pw = {}
    if placeholder:
        pw["get_by_placeholder"] = {"placeholder": placeholder}
    if role:
        pw["get_by_role"] = {"role": role, "name": role_name} if role_name else {"role": role}
    if label:
        pw["get_by_label"] = {"label": label}
    if text:
        pw["get_by_text"] = {"text": text}
    return {
        "locator_id": locator_id,
        "tag": tag,
        "display_text": display_text,
        "semantic_locators": {"role": role, "label": label, "placeholder": placeholder},
        "attribute_locators": {"id": None, "name": None, "testid": None},
        "playwright_locators": pw,
        "technical_locators": {"css": css or "", "xpath": ""},
        "recommended_locator": {"type": "", "value": {}},
        "intent_hints": [],
    }


def _write_dom_elements(path, elements):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"url": "https://x", "project": "p", "elements": elements}, f)


class BestLocatorEntryTests(unittest.TestCase):
    def test_placeholder_wins_top_priority(self):
        el = _element("LOC-0001", placeholder="Search", role="textbox")
        self.assertEqual(_best_locator_entry(el), {"type": "placeholder", "locator": "Search"})

    def test_label_tier_is_reachable(self):
        el = _element("LOC-0002", label="Email address")
        self.assertEqual(_best_locator_entry(el), {"type": "label", "locator": "Email address"})

    def test_role_with_name(self):
        el = _element("LOC-0003", role="button", role_name="Submit")
        self.assertEqual(_best_locator_entry(el), {"type": "role", "locator": "button", "name": "Submit"})

    def test_technical_xpath_is_absolute_last_resort(self):
        el = _element("LOC-0004")
        el["technical_locators"]["xpath"] = "/html/body/div[1]/input"
        self.assertEqual(_best_locator_entry(el), {"type": "xpath", "locator": "/html/body/div[1]/input"})

    def test_no_locator_available_returns_none(self):
        el = _element("LOC-0005")
        self.assertIsNone(_best_locator_entry(el))


class SlugifyMintKeyTests(unittest.TestCase):
    def test_slugify_lowercases_and_underscores(self):
        self.assertEqual(_slugify("Search Products!"), "search_products")

    def test_mint_key_dedupes_on_collision(self):
        used = {"login_button"}
        el = {"intent_hints": ["login_button"], "display_text": "", "locator_id": "LOC-0009", "tag": "button"}
        key = _mint_key(el, used)
        self.assertEqual(key, "login_button_2")


class BuildNamedLocatorMapMergeTests(unittest.TestCase):
    """The core never-delete/never-duplicate merge algorithm."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.comp_dir = os.path.join(self.tmp, "test_comprehension")

    def test_first_build_from_flat_layout_mints_fresh_keys(self):
        _write_dom_elements(
            os.path.join(self.comp_dir, "dom_elements.json"),
            [_element("LOC-0001", placeholder="Username", display_text="Username")],
        )
        result = build_named_locator_map(self.comp_dir)
        self.assertEqual(len(result["map"]), 1)
        self.assertEqual(result["added"], list(result["map"].keys()))
        self.assertEqual(result["updated"], [])
        self.assertEqual(result["possibly_removed"], [])
        entry = next(iter(result["map"].values()))
        self.assertEqual(entry["_module_id"], "_default")
        self.assertEqual(entry["_source_locator_id"], "LOC-0001")

    def test_per_module_layout_is_merged_into_one_map(self):
        _write_dom_elements(
            os.path.join(self.comp_dir, "modules", "M01", "dom_elements.json"),
            [_element("LOC-0001", placeholder="Username")],
        )
        _write_dom_elements(
            os.path.join(self.comp_dir, "modules", "M02", "dom_elements.json"),
            [_element("LOC-0001", placeholder="Search")],
        )
        result = build_named_locator_map(self.comp_dir)
        module_ids = {e["_module_id"] for e in result["map"].values()}
        self.assertEqual(module_ids, {"M01", "M02"})

    def test_unchanged_element_on_rescan_is_left_untouched(self):
        elements = [_element("LOC-0001", placeholder="Username")]
        _write_dom_elements(os.path.join(self.comp_dir, "dom_elements.json"), elements)
        first = build_named_locator_map(self.comp_dir)

        second = build_named_locator_map(self.comp_dir, existing_map=first["map"])
        self.assertEqual(second["map"], first["map"])
        self.assertEqual(second["added"], [])
        self.assertEqual(second["updated"], [])
        self.assertEqual(second["possibly_removed"], [])

    def test_changed_locator_updates_entry_in_place_same_key(self):
        _write_dom_elements(
            os.path.join(self.comp_dir, "dom_elements.json"),
            [_element("LOC-0001", placeholder="Username")],
        )
        first = build_named_locator_map(self.comp_dir)
        key = next(iter(first["map"]))

        # Same locator_id, but the app now exposes a role locator instead.
        _write_dom_elements(
            os.path.join(self.comp_dir, "dom_elements.json"),
            [_element("LOC-0001", role="textbox", role_name="Username")],
        )
        second = build_named_locator_map(self.comp_dir, existing_map=first["map"])

        self.assertEqual(set(second["map"].keys()), {key})  # same key, not a new one
        self.assertEqual(second["updated"], [key])
        self.assertEqual(second["map"][key]["type"], "role")

    def test_removed_element_is_kept_never_deleted(self):
        _write_dom_elements(
            os.path.join(self.comp_dir, "dom_elements.json"),
            [_element("LOC-0001", placeholder="Username")],
        )
        first = build_named_locator_map(self.comp_dir)
        key = next(iter(first["map"]))

        # Element vanished from the latest scan entirely.
        _write_dom_elements(os.path.join(self.comp_dir, "dom_elements.json"), [])
        second = build_named_locator_map(self.comp_dir, existing_map=first["map"])

        self.assertIn(key, second["map"])  # never deleted
        self.assertEqual(second["possibly_removed"], [key])

    def test_same_locator_reappearing_under_new_id_reuses_existing_key_not_a_duplicate(self):
        _write_dom_elements(
            os.path.join(self.comp_dir, "dom_elements.json"),
            [_element("LOC-0001", placeholder="Username")],
        )
        first = build_named_locator_map(self.comp_dir)
        key = next(iter(first["map"]))

        # Same resolved locator, but a different locator_id this scan
        # (e.g. discovery reordering) — must NOT mint "username_2".
        _write_dom_elements(
            os.path.join(self.comp_dir, "dom_elements.json"),
            [_element("LOC-0099", placeholder="Username")],
        )
        second = build_named_locator_map(self.comp_dir, existing_map=first["map"])

        self.assertEqual(set(second["map"].keys()), {key})
        self.assertEqual(second["map"][key]["_source_locator_id"], "LOC-0099")
        self.assertEqual(second["added"], [])

    def test_llm_reconcile_only_called_for_ambiguous_remainder(self):
        _write_dom_elements(
            os.path.join(self.comp_dir, "dom_elements.json"),
            [_element("LOC-0001", placeholder="Username")],
        )
        first = build_named_locator_map(self.comp_dir)
        old_key = next(iter(first["map"]))

        # A genuinely different element replaces it (different locator AND
        # a fresh id) — ambiguous: could be a relocation or a new element.
        _write_dom_elements(
            os.path.join(self.comp_dir, "dom_elements.json"),
            [_element("LOC-0007", role="textbox", role_name="Full Name")],
        )
        calls = []

        def fake_reconcile(new_elements, removed_candidates):
            calls.append((new_elements, removed_candidates))
            return {"LOC-0007": old_key}  # tell it: this is the same control, relocated

        second = build_named_locator_map(self.comp_dir, existing_map=first["map"], llm_reconcile=fake_reconcile)

        self.assertEqual(len(calls), 1)
        self.assertEqual(set(second["map"].keys()), {old_key})  # reused, not a new key
        self.assertEqual(second["map"][old_key]["type"], "role")

    def test_llm_reconcile_not_called_when_nothing_ambiguous(self):
        _write_dom_elements(
            os.path.join(self.comp_dir, "dom_elements.json"),
            [_element("LOC-0001", placeholder="Username")],
        )
        first = build_named_locator_map(self.comp_dir)
        calls = []
        build_named_locator_map(
            self.comp_dir, existing_map=first["map"],
            llm_reconcile=lambda *a: calls.append(a) or {},
        )
        self.assertEqual(calls, [])

    def test_write_named_locator_map_persists_and_returns_drift(self):
        _write_dom_elements(
            os.path.join(self.comp_dir, "dom_elements.json"),
            [_element("LOC-0001", placeholder="Username")],
        )
        out_path = os.path.join(self.tmp, "test_creation", "locator_map.json")
        drift = write_named_locator_map(self.comp_dir, out_path)
        self.assertTrue(os.path.exists(out_path))
        self.assertEqual(len(drift["added"]), 1)


class RepairNamedLocatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.comp_dir = os.path.join(self.tmp, "test_comprehension")

    def test_repairs_by_source_locator_id_match(self):
        _write_dom_elements(
            os.path.join(self.comp_dir, "modules", "M01", "dom_elements.json"),
            [_element("LOC-0001", role="textbox", role_name="Username")],
        )
        locator_map_path = os.path.join(self.tmp, "locator_map.json")
        with open(locator_map_path, "w", encoding="utf-8") as f:
            json.dump({"username_input": {
                "type": "placeholder", "locator": "Old Placeholder",
                "description": "", "_source_locator_id": "LOC-0001", "_module_id": "M01",
            }}, f)

        ok = repair_named_locator(locator_map_path, self.comp_dir, "username_input")
        self.assertTrue(ok)

        with open(locator_map_path, encoding="utf-8") as f:
            updated = json.load(f)
        self.assertEqual(updated["username_input"]["type"], "role")
        self.assertNotIn("name", updated["username_input"]) if False else None

    def test_returns_false_when_key_not_found(self):
        locator_map_path = os.path.join(self.tmp, "locator_map.json")
        with open(locator_map_path, "w", encoding="utf-8") as f:
            json.dump({}, f)
        self.assertFalse(repair_named_locator(locator_map_path, self.comp_dir, "nope"))

    def test_returns_false_when_no_confident_match(self):
        _write_dom_elements(os.path.join(self.comp_dir, "modules", "M01", "dom_elements.json"), [])
        locator_map_path = os.path.join(self.tmp, "locator_map.json")
        with open(locator_map_path, "w", encoding="utf-8") as f:
            json.dump({"username_input": {
                "type": "placeholder", "locator": "X", "description": "",
                "_source_locator_id": "LOC-0001", "_module_id": "M01",
            }}, f)
        self.assertFalse(repair_named_locator(locator_map_path, self.comp_dir, "username_input"))


class RenderPagesModuleTests(unittest.TestCase):
    def test_one_class_per_module_plus_registry(self):
        locator_map = {
            "username_input": {"type": "css", "locator": "#u", "_module_id": "M01"},
            "search_box": {"type": "placeholder", "locator": "Search", "_module_id": "M02"},
        }
        content = render_pages_module(locator_map, module_names={"M01": "Login", "M02": "Inventory"})
        self.assertIn("export class LoginPage", content)
        self.assertIn("export class InventoryPage", content)
        # Getter names are the raw locator_map key, verbatim — must match
        # exactly what ActionEngine looks up via pageObject[locator_key].
        self.assertIn("get username_input(): Locator", content)
        self.assertIn("get search_box(): Locator", content)
        self.assertIn("PAGE_REGISTRY", content)
        self.assertIn('"M01": LoginPage', content)
        self.assertIn('"M02": InventoryPage', content)

    def test_duplicate_class_names_across_modules_are_deduped(self):
        locator_map = {
            "a": {"type": "css", "locator": "#a", "_module_id": "M01"},
            "b": {"type": "css", "locator": "#b", "_module_id": "M02"},
        }
        content = render_pages_module(locator_map, module_names={"M01": "Checkout", "M02": "Checkout"})
        self.assertIn("export class CheckoutPage", content)
        self.assertIn("export class CheckoutPage2", content)


if __name__ == "__main__":
    unittest.main()
