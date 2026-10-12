"""Phase 4.9 — test_suites/*.json -> one Playwright --grep (tools/execution/suite_grep.py).

Playwright compiles --grep as `new RegExp(source, "gi")` and matches it against
"<project> <spec path> <describe titles> <test title> <tags>". The matching assertions below use
Python's `re` with IGNORECASE (same semantics for these constructs) and, when node is available,
re-check every expression with the real JavaScript engine.
"""

import json
import re
import shutil
import subprocess

import pytest

from tools.execution.suite_grep import (
    build_suite_grep, id_pattern, js_escape, resolve_spec_id, suite_config_to_grep, tag_pattern,
)

SPECS = [
    {"spec_id": "M01_BS_001", "module_id": "M01", "file": "M01/test_M01_BS_001_login.spec.ts"},
    {"spec_id": "M01_BS_002", "module_id": "M01", "file": "M01/test_M01_BS_002_bad.spec.ts"},
    {"spec_id": "M01_BS_0010", "module_id": "M01", "file": "M01/test_M01_BS_0010_x.spec.ts"},
    {"spec_id": "M02_BS_001", "module_id": "M02", "file": "M02/test_M02_BS_001_list.spec.ts"},
    {"spec_id": "BS-003", "module": "M03", "file": "M03/test_BS-003_legacy.spec.ts"},
]


def grep_title(spec_file: str, describe: str, title: str, tags=()) -> str:
    """What Playwright greps: project, file path relative to testDir, describes, title, tags."""
    return " ".join(["chromium", f"shop/test_creation/test_scripts/{spec_file}", describe, title, *tags])


T_M01_1 = grep_title("M01/test_M01_BS_001_login.spec.ts", "Login (M01_BS_001)", "AC-01.1 valid login", ["@P0", "@smoke"])
T_M01_2 = grep_title("M01/test_M01_BS_002_bad.spec.ts", "Bad login (M01_BS_002)", "AC-01.2 wrong password", ["@P1"])
T_M01_10 = grep_title("M01/test_M01_BS_0010_x.spec.ts", "X (M01_BS_0010)", "something", ["@P10"])
T_M02_1 = grep_title("M02/test_M02_BS_001_list.spec.ts", "List (M02_BS_001)", "lists products", ["@P2", "@AC-02.1.1"])
T_LEGACY = grep_title("M03/test_BS-003_legacy.spec.ts", "Legacy (BS-003)", "legacy test")  # pre-Phase-1: no tags
ALL = [T_M01_1, T_M01_2, T_M01_10, T_M02_1, T_LEGACY]


def matches(grep: str):
    rx = re.compile(grep, re.IGNORECASE)
    return [t for t in ALL if rx.search(t)]


def node_matches(grep: str):
    script = ("const re=new RegExp(process.argv[1],'gi');const ts=JSON.parse(process.argv[2]);"
              "console.log(JSON.stringify(ts.filter(t=>{re.lastIndex=0;return re.test(t);})));")
    out = subprocess.run(["node", "-e", script, grep, json.dumps(ALL)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def both(grep: str):
    py = matches(grep)
    if shutil.which("node"):
        assert node_matches(grep) == py, "Python and JavaScript disagree on the grep"
    return py


def test_spec_ids_select_their_spec_only():
    sg = suite_config_to_grep({"scenarios": ["M01_BS_001", "M02_BS_001"]}, SPECS, "smoke")
    assert both(sg.grep) == [T_M01_1, T_M02_1]
    assert sg.modules == ["M01", "M02"]
    assert sg.spec_ids == ["M01_BS_001", "M02_BS_001"]


def test_id_is_bounded_no_prefix_match():
    assert both(id_pattern(["M01_BS_001"])) == [T_M01_1]          # not M01_BS_0010
    assert both(id_pattern(["M01_BS_0010"])) == [T_M01_10]


def test_legacy_spec_without_tags_selected_by_id():
    sg = suite_config_to_grep({"scenarios": ["BS-003"]}, SPECS)
    assert both(sg.grep) == [T_LEGACY]
    assert sg.modules == ["M03"]


def test_ordinal_ids_resolve_through_the_manifest():
    assert resolve_spec_id("SC-M01-002", SPECS)["spec_id"] == "M01_BS_0010"   # sorted by spec_id like the legacy resolver
    assert resolve_spec_id("SC-M01-009", SPECS) is None
    sg = suite_config_to_grep({"scenarios": ["SC-M02-001"]}, SPECS)
    assert both(sg.grep) == [T_M02_1]


def test_per_entry_grep_is_anded_with_its_id():
    sg = suite_config_to_grep({"scenarios": [{"id": "M01_BS_001", "grep": "valid login"}, "M02_BS_001"]}, SPECS)
    assert both(sg.grep) == [T_M01_1, T_M02_1]
    sg = suite_config_to_grep({"scenarios": [{"id": "M01_BS_001", "grep": "nothing like this"}]}, SPECS)
    assert both(sg.grep) == []


def test_tags_are_exact():
    assert both(tag_pattern(["@P1"])) == [T_M01_2]                 # not @P10
    assert both(tag_pattern(["smoke"])) == [T_M01_1]               # '@' added
    assert both(tag_pattern(["@AC-02.1"])) == []                   # not @AC-02.1.1
    sg = suite_config_to_grep({"tags": ["@P0", "@P2"]}, SPECS)
    assert both(sg.grep) == [T_M01_1, T_M02_1]
    assert sg.modules == []                                        # tags can reach any module


def test_ids_tags_and_raw_grep_are_ored():
    sg = suite_config_to_grep({"scenarios": ["BS-003"], "tags": ["@P1"], "grep": "lists products"}, SPECS)
    assert both(sg.grep) == [T_M01_2, T_M02_1, T_LEGACY]


def test_all_modules_means_no_grep():
    sg = suite_config_to_grep({"all_modules": True, "scenarios": ["M01_BS_001"]}, SPECS)
    assert sg.all_modules and sg.grep is None and not sg.empty


def test_unresolved_ids_are_reported_and_an_empty_suite_flagged(capsys):
    sg = suite_config_to_grep({"scenarios": ["NOPE_1", "M01_BS_002"]}, SPECS)
    assert sg.unresolved == ["NOPE_1"]
    assert both(sg.grep) == [T_M01_2]
    assert "NOPE_1" in capsys.readouterr().err
    empty = suite_config_to_grep({"scenarios": ["NOPE_2"]}, SPECS)
    assert empty.empty and empty.grep is None


def test_js_escape():
    assert js_escape("a.b(c)|d") == r"a\.b\(c\)\|d"
    assert re.fullmatch(js_escape("x+y?"), "x+y?")


def test_build_suite_grep_reads_files(tmp_path):
    (tmp_path / "test_suites").mkdir()
    (tmp_path / "test_creation").mkdir()
    (tmp_path / "test_suites" / "smoke_suite.json").write_text(json.dumps({"scenarios": ["M01_BS_001"]}), encoding="utf-8")
    (tmp_path / "test_creation" / "test_suite.json").write_text(json.dumps({"specs": SPECS}), encoding="utf-8")
    sg = build_suite_grep(str(tmp_path), "smoke")
    assert sg.suite == "smoke" and both(sg.grep) == [T_M01_1]
    with pytest.raises(FileNotFoundError):
        build_suite_grep(str(tmp_path), "nightly")
