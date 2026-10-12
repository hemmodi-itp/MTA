"""
Golden dataset (tools/agent_tests/dataset.py, models.py) and CLI (tools/agent_tests/cli.py): record validation,
loader errors, merge rules that never destroy human review (design D9), byte-stable writes and versioning.
"""

import json
import os
import shutil

import pytest

from tools.agent_tests import cli, dataset
from tools.agent_tests.catalogs import load_catalogs
from tools.agent_tests.generators import generate_all
from tools.agent_tests.models import AgentTestCase, Expected

pytestmark = pytest.mark.mta

SRC_SPEC = os.path.join(dataset.agent_dir("buggy_bot"), "agent.yaml")


@pytest.fixture
def root(tmp_path):
    (tmp_path / "buggy_bot").mkdir()
    shutil.copy(SRC_SPEC, tmp_path / "buggy_bot" / "agent.yaml")
    return str(tmp_path)


def _gen(root, seed=7):
    assert cli.main(["--root", root, "generate", "--agent", "buggy_bot", "--seed", str(seed)]) == 0
    return os.path.join(root, "buggy_bot")


def _case(**kw) -> AgentTestCase:
    base = dict(id="AT-TASK-00000001", dimension="task_success", title="t", input="hi",
                expected=Expected(contains_all=["x"]), source="generated")
    base.update(kw)
    return AgentTestCase(**base).with_hash()


# ── the record ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("kw,msg", [
    (dict(input=None), "exactly one of"),
    (dict(turns=[{"user": "a"}]), "exactly one of"),
    (dict(source="brd"), "ac_ids"),
    (dict(ac_ids=["REQ-1"]), "malformed acceptance-criterion id"),
    (dict(input="say {{NOT_A_TOKEN}}"), "unknown placeholder"),
    (dict(expected=Expected()), "deterministic expectation or a rubric"),
    (dict(dimension="vibes"), "dimension"),
])
def test_record_validation(kw, msg):
    with pytest.raises(Exception) as exc:
        _case(**kw)
    assert msg in str(exc.value)


def test_canary_placeholder_names_are_checked():
    with pytest.raises(Exception, match="unknown canary placeholder"):
        Expected(canary_absent=["PASSWORD"])
    assert _case(expected=Expected(), rubric="judge it").rubric


def test_hash_ignores_review_bookkeeping():
    c = _case()
    reviewed = c.model_copy(update={"reviewed": True, "reviewed_by": "qa", "reviewed_at": "2026-10-12"})
    assert reviewed.compute_hash() == c.compute_hash()
    assert _case(input="other").compute_hash() != c.compute_hash()


# ── generate / write / version ──────────────────────────────────────────────

def test_generate_writes_valid_dataset_and_is_byte_stable(root):
    d = _gen(root)
    m1 = dataset.read_manifest(d)
    assert m1["dataset_version"] == 1 and m1["total"] >= 90 and m1["unreviewed"] == m1["total"]
    files = {n: open(os.path.join(d, n), "rb").read() for n in os.listdir(d)}
    _gen(root)  # same seed again → nothing changes, version stays
    assert {n: open(os.path.join(d, n), "rb").read() for n in os.listdir(d)} == files
    rep = dataset.validate(d)
    assert rep.ok and rep.unreviewed == m1["total"] and not rep.warnings
    assert cli.main(["--root", root, "validate", "--agent", "buggy_bot"]) == 0


def test_review_marks_cases_and_bumps_version(root, capsys):
    d = _gen(root)
    cases, _ = dataset.load_cases(d)
    ids = [c.id for c in cases if c.dimension == "hallucination"]
    assert cli.main(["--root", root, "review", "--agent", "buggy_bot", "--dimension", "hallucination",
                     "--by", "QA Lead"]) == 0
    after, _ = dataset.load_cases(d)
    marked = [c for c in after if c.reviewed]
    assert {c.id for c in marked} == set(ids) and all(c.reviewed_by == "QA Lead" and c.reviewed_at for c in marked)
    assert dataset.read_manifest(d)["dataset_version"] == 2
    assert cli.main(["--root", root, "review", "--agent", "buggy_bot", "--ids", "AT-NOPE-00000000",
                     "--by", "x"]) == 1
    capsys.readouterr()
    assert cli.main(["--root", root, "list", "--agent", "buggy_bot", "--unreviewed", "--dimension",
                     "hallucination"]) == 0
    assert capsys.readouterr().out.strip() == ""


def test_regeneration_keeps_reviewed_and_human_cases(root):
    d = _gen(root)
    cases, _ = dataset.load_cases(d)
    reviewed_id = next(c.id for c in cases if c.dimension == "scope")
    dataset.mark_reviewed(d, "qa", "2026-10-12", ids=[reviewed_id])
    human = _case(id="AT-TASK-feedf00d", source="human", input="Do you have a café?", rubric="human-written")
    cases, _ = dataset.load_cases(d)
    dataset.write(d, cases + [human], "buggy_bot", 7)
    _gen(root)  # regenerate
    after = {c.id: c for c in dataset.load_cases(d)[0]}
    assert after[reviewed_id].reviewed and after[reviewed_id].reviewed_by == "qa"
    assert after["AT-TASK-feedf00d"].source == "human"
    # a different seed changes the typo variants: unreviewed ones are replaced, nothing reviewed is lost
    _gen(root, seed=8)
    after8 = {c.id: c for c in dataset.load_cases(d)[0]}
    assert after8[reviewed_id].reviewed and "AT-TASK-feedf00d" in after8


def test_merge_rules():
    a = _case(id="AT-TASK-0000000a")
    b = _case(id="AT-TASK-0000000b").model_copy(update={"reviewed": True})
    c = _case(id="AT-TASK-0000000c")
    h = _case(id="AT-TASK-0000000d", source="human")
    b_changed = _case(id="AT-TASK-0000000b", input="changed")
    merged, ch = dataset.merge([a, b, c, h], [a, b_changed, _case(id="AT-TASK-0000000e")])
    ids = {m.id: m for m in merged}
    assert ch["unchanged"] == ["AT-TASK-0000000a"] and ch["review_reset"] == ["AT-TASK-0000000b"]
    assert not ids["AT-TASK-0000000b"].reviewed and ids["AT-TASK-0000000b"].input == "changed"
    assert ch["dropped"] == ["AT-TASK-0000000c"] and "AT-TASK-0000000c" not in ids
    assert ch["kept_human"] == ["AT-TASK-0000000d"] and ch["added"] == ["AT-TASK-0000000e"]
    stale_reviewed = _case(id="AT-TASK-0000000f").model_copy(update={"reviewed": True})
    _, ch2 = dataset.merge([stale_reviewed], [])
    assert ch2["kept_reviewed"] == ["AT-TASK-0000000f"]


def test_loader_reports_bad_lines_duplicates_and_hand_edits(root):
    d = _gen(root)
    path = os.path.join(d, "scope.jsonl")
    lines = open(path, encoding="utf-8").read().splitlines()
    edited = json.loads(lines[0])
    edited["title"] = "edited by hand"
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join([json.dumps(edited), lines[1], lines[1], "{not json", '{"id": "x"}'] + lines[2:]) + "\n")
    open(os.path.join(d, "bogus.jsonl"), "w").close()
    cases, rep = dataset.load_cases(d)
    text = "\n".join(rep.errors)
    assert "duplicate id" in text and "scope.jsonl:4" in text and "scope.jsonl:5" in text
    assert "bogus.jsonl: not a known dimension file" in text
    assert any("edited by hand" in w for w in rep.warnings)
    assert cli.main(["--root", root, "validate", "--agent", "buggy_bot"]) == 1


def test_validate_flags_missing_spec_and_dangling_same_as(root, tmp_path):
    assert not dataset.validate(str(tmp_path / "nothing")).ok
    d = _gen(root)
    rows = [json.loads(x) for x in open(os.path.join(d, "robustness.jsonl"), encoding="utf-8")]
    variant = next(r for r in rows if r["expected"].get("same_as"))
    variant["expected"]["same_as"] = "AT-TASK-deadbeef"
    with open(os.path.join(d, "robustness.jsonl"), "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(r) + "\n" for r in rows))
    rep = dataset.validate(d)
    assert any("same_as points at missing case" in e for e in rep.errors)


def test_agent_dir_rejects_path_tricks():
    for bad in ("../etc", "a/b", ".hidden", ""):
        with pytest.raises(ValueError):
            dataset.agent_dir(bad)


def test_committed_buggy_bot_dataset_is_valid_and_current():
    d = dataset.agent_dir("buggy_bot")
    rep = dataset.validate(d)
    assert rep.ok, rep.errors
    assert not rep.warnings, rep.warnings
    spec = dataset.spec_for(d)
    m = dataset.read_manifest(d)
    regenerated = [c for r in generate_all(spec, load_catalogs(), m["seed"]).values() for c in r.cases]
    stored = {c.id: c.compute_hash() for c in dataset.load_cases(d)[0]}
    assert {c.id: c.compute_hash() for c in regenerated} == stored, "run: python -m tools.agent_tests generate"


def test_exported_json_schema_is_fresh_and_validates_every_committed_case():
    import jsonschema

    from tools.agent_tests.models import SCHEMA_PATH, export_schema
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        committed = f.read()
    assert committed == export_schema(), "regenerate: tools.agent_tests.models.export_schema()"
    schema = json.loads(committed)
    d = dataset.agent_dir("buggy_bot")
    for name in sorted(os.listdir(d)):
        if name.endswith(".jsonl"):
            for line in open(os.path.join(d, name), encoding="utf-8"):
                jsonschema.validate(json.loads(line), schema)


def test_crlf_checkout_keeps_the_manifest_valid(root):
    d = _gen(root)
    path = os.path.join(d, "scope.jsonl")
    data = open(path, "rb").read()
    with open(path, "wb") as f:
        f.write(data.replace(b"\n", b"\r\n"))  # what git autocrlf does on Windows
    rep = dataset.validate(d)
    assert rep.ok and not rep.warnings, rep.warnings
