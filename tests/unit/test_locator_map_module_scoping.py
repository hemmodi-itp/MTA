"""Phase 0 fix — locator_map.json merge and ScriptGeneration's reverse index are
module-scoped. Every module's DOM scan numbers its elements from LOC-0001, so a
bare locator id (or an identical locator value, e.g. a shared header link) in
module M02 used to overwrite module M01's entry and move it to M02's Page class.
Found while recording the Phase 0 baseline (docs/phases/phase-0-report.md)."""

import json
import os

from agents.test_creation.script_generation.agent import (
    _allowed_locator_entries_for_scenario,
    _reverse_locator_index,
)
from tools.test_creation.script_generator.build_dom_locator_map import build_named_locator_map


def _el(loc_id, testid, text, role=None):
    el = {
        "locator_id": loc_id, "tag": "input", "display_text": text,
        "attribute_locators": {"testid": testid},
        "semantic_locators": {"label": text} if role is None else {"role": role},
        "playwright_locators": {},
        "recommended_locator": {"type": "testid", "value": {"testid": testid}},  # scanner's real shape
    }
    return el


def _write_modules(comp_dir, modules):
    for mid, elements in modules.items():
        d = os.path.join(comp_dir, "modules", mid)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "dom_elements.json"), "w", encoding="utf-8") as f:
            json.dump({"schema_version": 2, "artifact": "dom_elements", "elements": elements}, f)


M01 = [_el("LOC-0001", "username", "Username"), _el("LOC-0002", "password", "Password"),
       _el("LOC-0003", "brand-link", "Buggy Shop")]
M02 = [_el("LOC-0001", "search", "Search"), _el("LOC-0002", "sort", "Sort"),
       _el("LOC-0003", "brand-link", "Buggy Shop")]


def _by_module(result):
    out = {}
    for key, entry in result["map"].items():
        out.setdefault(entry["_module_id"], set()).add(key)
    return out


def test_second_module_never_overwrites_first(tmp_path):
    comp = str(tmp_path / "test_comprehension")
    _write_modules(comp, {"M01": M01})
    first = build_named_locator_map(comp)
    m01_keys = _by_module(first)["M01"]
    assert len(m01_keys) == 3

    # M02 is scanned later with the same LOC-0001..0003 ids and a shared header link.
    _write_modules(comp, {"M02": M02})
    second = build_named_locator_map(comp, existing_map=first["map"])
    mods = _by_module(second)
    assert mods["M01"] == m01_keys, "M01's entries must stay M01's"
    assert len(mods["M02"]) == 3, "M02 gets its own three entries, incl. its own brand link"
    for key in m01_keys:
        assert second["map"][key] == first["map"][key]
    assert second["updated"] == []


def test_same_module_rescan_still_updates_in_place(tmp_path):
    comp = str(tmp_path / "test_comprehension")
    _write_modules(comp, {"M01": M01})
    first = build_named_locator_map(comp)
    changed = [dict(e) for e in M01]
    changed[0] = _el("LOC-0001", "user-name", "Username")
    _write_modules(comp, {"M01": changed})
    second = build_named_locator_map(comp, existing_map=first["map"])
    assert len(second["map"]) == 3 and len(second["updated"]) == 1
    assert second["added"] == []


def test_reconcile_is_called_per_module_with_same_module_candidates(tmp_path):
    comp = str(tmp_path / "test_comprehension")
    _write_modules(comp, {"M01": M01, "M02": M02})
    first = build_named_locator_map(comp)
    _write_modules(comp, {"M01": [_el("LOC-0009", "login-user", "User")] + M01[1:],
                          "M02": [_el("LOC-0009", "query", "Query")] + M02[1:]})
    calls = []

    def reconcile(new_els, candidates):
        calls.append(({e["locator_id"] for e in new_els}, {c["_module_id"] for c in candidates}))
        return {}

    build_named_locator_map(comp, existing_map=first["map"], llm_reconcile=reconcile)
    assert sorted(c[1] for c in calls) == [{"M01"}, {"M02"}]


def test_reverse_index_is_module_scoped_and_keeps_unambiguous_bare_ids():
    loc_map = {
        "username": {"_module_id": "M01", "_source_locator_id": "LOC-0001"},
        "search": {"_module_id": "M02", "_source_locator_id": "LOC-0001"},
        "only_one": {"_module_id": "M02", "_source_locator_id": "LOC-0007"},
    }
    idx = _reverse_locator_index(loc_map)
    assert idx[("M01", "LOC-0001")] == "username" and idx[("M02", "LOC-0001")] == "search"
    assert "LOC-0001" not in idx               # ambiguous bare id is not offered
    assert idx["LOC-0007"] == "only_one"
    elements = [{"locator_id": "LOC-0001"}, {"locator_id": "LOC-0007"}]
    m01 = _allowed_locator_entries_for_scenario(elements, idx, loc_map, module_id="M01")
    assert [e["key"] for e in m01] == ["username", "only_one"]
    m02 = _allowed_locator_entries_for_scenario(elements, idx, loc_map, module_id="M02")
    assert [e["key"] for e in m02] == ["search", "only_one"]


def test_flat_default_projects_unchanged():
    loc_map = {"login": {"_module_id": "_default", "_source_locator_id": "LOC-0001"}}
    idx = _reverse_locator_index(loc_map)
    assert _allowed_locator_entries_for_scenario([{"locator_id": "LOC-0001"}], idx, loc_map)[0]["key"] == "login"
    assert _allowed_locator_entries_for_scenario(
        [{"locator_id": "LOC-0001"}], idx, loc_map, module_id="M05")[0]["key"] == "login"
