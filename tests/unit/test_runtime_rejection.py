"""Unit tests for engines/runtime/rejection.py and the action plan's grounding of record ids and same-labelled boxes."""

from engines.runtime.actions import build_inventory, ground_record_id, validate_steps
from engines.runtime.rejection import INPUT_REJECTED, named_fields

BRD_AGENT_MSG = ('Please add at least one point to every field before generating (or mark it "Not applicable" if it '
                 "genuinely doesn't apply): Constraints.")


def test_named_fields():
    assert INPUT_REJECTED.search(BRD_AGENT_MSG)
    assert named_fields(BRD_AGENT_MSG) == ["Constraints"]
    assert named_fields("Please fill these in: Project Name, Objectives and Permanently Excluded.") == \
        ["Project Name", "Objectives", "Permanently Excluded"]
    assert named_fields("Email is required") == ["Email"]
    assert named_fields("Please fill all required fields") == []      # names nothing: nothing to complete


def _profile():
    return {"pages": [
        {"path": "/new", "forms": [{"fields": [
            {"label": "Doc ID Acronym (required)", "type": "text"},
            {"label": "Not applicable — omit this section", "type": "checkbox", "group": "Constraints"},
            {"label": "Constraints", "type": "textarea"},
            {"label": "Not applicable — omit this section", "type": "checkbox", "group": "Dependencies"}]}]},
        {"path": "/history", "forms": [{"fields": [{"label": "Search runs…", "type": "text"}]}]},
        {"path": "/runs/20261007-051753-2366f9", "forms": []}]}


def test_same_labelled_boxes_keep_their_group_into_the_plan():
    inv = build_inventory(_profile())
    boxes = {e["group"]: e for e in inv["elements"].values() if e.get("group")}
    steps, dropped = validate_steps([{"action": "check", "element_id": boxes["Dependencies"]["id"]}], inv)
    assert not dropped and steps[0]["target"]["group"] == "Dependencies"


def test_invented_record_ids_are_grounded():
    inv = build_inventory(_profile())
    assert inv["known_ids"] == ["20261007-051753-2366f9"]                 # item pages are not targets, their ids are kept
    els = {e["label"]: e for e in inv["elements"].values()}
    search, acronym = els["Search runs…"], els["Doc ID Acronym (required)"]
    assert ground_record_id("run_9999", search, inv) == "20261007-051753-2366f9"
    assert ground_record_id("20261007-051753-2366f9", search, inv) == "20261007-051753-2366f9"
    assert ground_record_id("payment gateway", search, inv) == "payment gateway"   # a real search phrase is kept
    assert ground_record_id("PRJ-2026", acronym, inv) == "PRJ-2026"                # a form value, not a lookup
    assert ground_record_id("run_9999", search, {**inv, "known_ids": []}) is None  # nothing real to use: dropped
    steps, dropped = validate_steps([{"action": "fill", "element_id": search["id"], "value": "run_9999"}],
                                    {**inv, "known_ids": []})
    assert steps == [] and dropped == 1
