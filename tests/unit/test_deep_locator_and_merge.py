"""Phase 2 — locator_map entries for deep elements, the shared Python resolver, and the
enrichment-aware dom_elements merge (design §2 R1, R2, R5, R18 and §4.4–4.5)."""

import copy
import json
import os

import pytest

from tools.discovery.dom_scan import (
    _element_identity_parts,
    _identity_parts_with_frame,
    merge_elements,
)
from tools.test_creation.script_generator.build_dom_locator_map import (
    _apply_locator_update,
    _best_locator_entry,
    _legacy_best_locator_entry,
    _locator_value_key,
    _mint_key,
    build_named_locator_map,
)
from tools.test_creation.script_generator.locator_resolve import entry_resolves, resolve_entry


def _legacy_button(name="Save", id_=None, testid=None):
    pw = {"get_by_role": {"role": "button", "name": name}, "get_by_text": {"text": name}}
    cands = []
    if testid:
        cands.append({"type": "testid", "value": {"testid": testid}, "score": 150, "unique": True, "match_count": 1})
    if id_:
        cands.append({"type": "id", "value": {"id": id_}, "score": 140, "unique": True, "match_count": 1})
    cands.append({"type": "role", "value": {"role": "button", "name": name}, "score": 110, "unique": True, "match_count": 1})
    return {"locator_id": "LOC-0001", "tag": "button", "display_text": name,
            "semantic_locators": {"role": "button", "label": "", "placeholder": None, "aria_label": None, "title": None},
            "attribute_locators": {"testid": testid, "id": id_, "name": None, "type": None},
            "playwright_locators": pw, "technical_locators": {"css": "main>button:nth-of-type(2)", "xpath": "/html/body/main/button[2]"},
            "recommended_locator": cands[0], "locator_candidates": cands, "quality": {"visible": True, "enabled": True},
            "intent_hints": []}


def _deep(el, scoped=None, duplicated=False, frame=None):
    el = copy.deepcopy(el)
    el["capture_mode"] = "deep"
    if duplicated:
        for c in el["locator_candidates"]:
            if c["type"] == "role":
                c.update(unique=False, match_count=2, score=c["score"] - 50)
    if scoped:
        el["locator_candidates"].append({"type": "scoped_role", "value": {"container": scoped, "role": "button", "name": "Save"},
                                         "score": 105, "unique": True, "match_count": 1})
    if frame:
        el["frame"] = {"path": frame, "url": "http://h/f"}
    return el


# ── locator_map entries ─────────────────────────────────────────────────

def test_legacy_elements_get_exactly_the_old_entry():
    el = _legacy_button(id_="save")
    assert _best_locator_entry(el) == _legacy_best_locator_entry(el) == {"type": "role", "locator": "button", "name": "Save"}


def test_a_unique_deep_role_element_keeps_the_legacy_entry():
    assert _best_locator_entry(_deep(_legacy_button())) == {"type": "role", "locator": "button", "name": "Save"}


def test_a_duplicated_role_with_a_verified_scope_becomes_a_scoped_entry():
    el = _deep(_legacy_button(), scoped={"role": "dialog", "name": "Edit user"}, duplicated=True)
    assert _best_locator_entry(el) == {"type": "role", "locator": "button", "name": "Save",
                                       "scope": {"type": "role", "locator": "dialog", "name": "Edit user"}}
    unnamed = _deep(_legacy_button(), scoped={"role": "contentinfo", "name": None}, duplicated=True)
    assert _best_locator_entry(unnamed)["scope"] == {"type": "role", "locator": "contentinfo"}


def test_a_duplicated_role_without_a_scope_never_uses_the_bare_role_or_text():
    with_id = _deep(_legacy_button(id_="save-2"), duplicated=True)
    assert _best_locator_entry(with_id) == {"type": "css", "locator": "#save-2"}
    bare = _deep(_legacy_button(), duplicated=True)
    assert _best_locator_entry(bare) == {"type": "css", "locator": "main>button:nth-of-type(2)"}


def test_frame_elements_carry_the_frame_chain():
    el = _deep(_legacy_button(testid="pay"), frame=["#payment", "#nested"])
    entry = _best_locator_entry(el)
    assert entry["frame"] == ["#payment", "#nested"] and entry["type"] == "role"


def test_value_key_separates_scopes_and_frames():
    a = {"type": "role", "locator": "button", "name": "Save", "scope": {"type": "role", "locator": "dialog", "name": "A"}}
    b = {"type": "role", "locator": "button", "name": "Save", "scope": {"type": "role", "locator": "dialog", "name": "B"}}
    c = {"type": "role", "locator": "button", "name": "Save", "frame": ["#f"]}
    plain = {"type": "role", "locator": "button", "name": "Save"}
    keys = {_locator_value_key(x) for x in (a, b, c, plain)}
    assert len(keys) == 4
    assert _locator_value_key(plain) == ("role", "button", "Save", "", "")


def test_update_drops_a_stale_scope_or_frame():
    old = {"type": "role", "locator": "button", "name": "Save", "scope": {"type": "role", "locator": "dialog"},
           "frame": ["#f"], "description": "keep me"}
    merged = _apply_locator_update(old, {"type": "css", "locator": "#save"}, "LOC-0001", "M01")
    assert "scope" not in merged and "frame" not in merged and "name" not in merged
    assert merged["description"] == "keep me" and merged["locator"] == "#save"


def test_mint_key_slugifies_new_tags_and_keeps_legacy_keys():
    used = set()
    assert _mint_key({"tag": "input", "locator_id": "LOC-0001"}, used) == "input_loc_0001"
    assert _mint_key({"tag": "combobox", "locator_id": "LOC-0002"}, used) == "combobox_loc_0002"
    assert _mint_key({"tag": "div", "locator_id": "LOC-0003", "display_text": ""}, used) == "div_loc_0003"
    assert _mint_key({"tag": "[role=tab]", "locator_id": "LOC-0004"}, used) == "role_tab_loc_0004"


def _write_module(root, module, elements):
    d = os.path.join(root, "modules", module)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "dom_elements.json"), "w", encoding="utf-8") as f:
        json.dump({"url": "http://h/", "elements": elements}, f)


def test_two_scoped_save_buttons_become_two_map_entries(tmp_path):
    a = _deep(_legacy_button(), scoped={"role": "dialog", "name": "Edit user"}, duplicated=True)
    b = _deep(_legacy_button(), scoped={"role": "dialog", "name": "Create user"}, duplicated=True)
    a["locator_id"], b["locator_id"] = "LOC-0001", "LOC-0002"
    _write_module(str(tmp_path), "M01", [a, b])
    out = build_named_locator_map(str(tmp_path))
    entries = [e for e in out["map"].values()]
    assert len(entries) == 2
    assert sorted(e["scope"]["name"] for e in entries) == ["Create user", "Edit user"]
    # a rescan keeps the same keys (value key includes the scope)
    again = build_named_locator_map(str(tmp_path), existing_map=out["map"])
    assert sorted(again["map"]) == sorted(out["map"]) and again["updated"] == [] and again["added"] == []


# ── shared resolver (Python mirror of LocatorManager.ts) ────────────────

class _Fake:
    def __init__(self, trail=(), count=1, raise_on=None):
        self.trail, self._count, self._raise = list(trail), count, raise_on

    def _step(self, call):
        if self._raise and call.startswith(self._raise):
            raise RuntimeError("boom")
        return _Fake(self.trail + [call], self._count, self._raise)

    def locator(self, s):
        return self._step(f"locator({s})")

    def get_by_role(self, r, name=None):
        return self._step(f"role({r},{name})")

    def get_by_text(self, s):
        return self._step(f"text({s})")

    def get_by_label(self, s):
        return self._step(f"label({s})")

    def get_by_test_id(self, s):
        return self._step(f"testid({s})")

    def get_by_placeholder(self, s):
        return self._step(f"placeholder({s})")

    def frame_locator(self, s):
        return self._step(f"frame({s})")

    def count(self):
        return self._count


def test_resolver_chains_frame_scope_and_entry():
    entry = {"type": "role", "locator": "button", "name": "Save", "frame": ["#f1", "#f2"],
             "scope": {"type": "role", "locator": "dialog", "name": "Edit"}}
    assert resolve_entry(_Fake(), entry).trail == ["frame(#f1)", "frame(#f2)", "role(dialog,Edit)", "role(button,Save)"]
    assert resolve_entry(_Fake(), {"type": "xpath", "locator": "//a"}).trail == ["locator(xpath=//a)"]


def test_resolver_keeps_the_count_rule_and_the_fail_open_rules():
    assert entry_resolves(_Fake(count=1), {"type": "css", "locator": "#a"}) is True
    assert entry_resolves(_Fake(count=0), {"type": "css", "locator": "#a"}) is False
    assert entry_resolves(_Fake(count=2), {"type": "css", "locator": "#a"}) is False     # strict mode
    assert entry_resolves(_Fake(count=0), {"type": "mystery", "locator": "x"}) is True   # unknown type: can't tell
    assert entry_resolves(_Fake(count=0, raise_on="role"), {"type": "role", "locator": "x"}) is True
    assert entry_resolves(_Fake(count=0), {"type": "css", "locator": "#a", "scope": {"type": "nope", "locator": "y"}}) is True


def test_script_generation_and_healing_use_the_shared_resolver():
    from agents.test_creation.script_generation.agent import ScriptGenerationAgent
    from agents.test_execution.healing.tools import _locator_entry_resolves
    entry = {"type": "role", "locator": "button", "name": "Save", "scope": {"type": "role", "locator": "dialog"}}
    assert ScriptGenerationAgent._locator_entry_resolves(_Fake(count=2), entry) is False
    assert _locator_entry_resolves(_Fake(count=1), entry) is True


# ── identity + merge ────────────────────────────────────────────────────

def test_identity_is_unchanged_for_main_frame_elements_and_extended_for_frames():
    el = _legacy_button(id_="save")
    assert _identity_parts_with_frame(el) == _element_identity_parts(el)
    assert _identity_parts_with_frame(_deep(el)) == _element_identity_parts(el)
    framed = _deep(el, frame=["#pay"])
    assert _identity_parts_with_frame(framed) == _element_identity_parts(el) + ("frame:#pay",)


def test_merge_copies_enrichment_onto_unchanged_legacy_elements_without_drift():
    old = _legacy_button(id_="save")
    fresh = copy.deepcopy(old)
    fresh.update(capture_mode="deep", capture_reason="classic", tag_name="button", aria_role="button")
    out = merge_elements([old], [fresh])
    assert out["updated"] == [] and out["added"] == [] and out["possibly_removed"] == []
    assert out["elements"][0]["capture_mode"] == "deep" and out["elements"][0]["aria_role"] == "button"


def test_merge_reports_a_real_constraint_change_as_an_update():
    old = _legacy_button(id_="name")
    old.update(capture_mode="deep", constraints={"maxlength": 50})
    fresh = copy.deepcopy(old)
    fresh["constraints"] = {"maxlength": 100}
    out = merge_elements([old], [fresh])
    assert out["updated"] == ["LOC-0001"] and out["elements"][0]["constraints"] == {"maxlength": 100}


def test_merge_of_two_legacy_scans_is_unchanged():
    old = _legacy_button(id_="save")
    out = merge_elements([old], [copy.deepcopy(old)])
    assert out["elements"] == [old] and out["updated"] == []
