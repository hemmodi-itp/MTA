"""Regression comparison (tools/agent_tests/regression.py, Phase 9.5)."""

import pytest

from tools.agent_tests import regression

pytestmark = pytest.mark.mta


def entry(run_id, rates, verdicts=None, version="1.0"):
    return {"run_id": run_id, "agent": "bot", "agent_version": version, "dataset_version": 1, "date": "2026-10-12",
            "dimensions": {d: {"pass_rate": r, "verdict": (verdicts or {}).get(d, "pass")} for d, r in rates.items()}}


def test_first_run_is_a_baseline():
    r = regression.compare(entry("r1", {"scope": 1.0}), None)
    assert r["ok"] and r["baseline"]


def test_drop_beyond_threshold_is_a_regression():
    prev = entry("r1", {"scope": 1.0, "task_success": 0.9, "hallucination": 0.8})
    cur = entry("r2", {"scope": 0.9, "task_success": 0.88, "hallucination": None}, version="1.1")
    r = regression.compare(cur, prev, max_drop_points=5)
    assert not r["ok"]
    assert [x["dimension"] for x in r["regressions"]] == ["scope"]
    assert r["dimensions"]["scope"]["delta_points"] == -10.0
    assert r["dimensions"]["task_success"]["status"] == "ok"   # -2 pts is within the 5-point tolerance
    assert r["dimensions"]["hallucination"]["delta_points"] is None
    assert r["previous"]["agent_version"] == "1.0"


def test_gate_flip_from_pass_to_fail_is_a_regression_even_within_tolerance():
    prev = entry("r1", {"data_leakage": 1.0})
    cur = entry("r2", {"data_leakage": 0.98}, {"data_leakage": "fail"})
    assert regression.compare(cur, prev, 5)["regressions"][0]["dimension"] == "data_leakage"


def test_new_dimension_is_not_a_regression():
    r = regression.compare(entry("r2", {"tool_use": 0.5}), entry("r1", {"scope": 1.0}))
    assert r["ok"] and r["dimensions"]["tool_use"]["status"] == "new"


def test_history_file_append_read_and_exclude(tmp_path, monkeypatch):
    path = regression.history_path("bot", str(tmp_path))
    assert path.endswith("bot.jsonl") and regression.last_entry(path) is None
    regression.append(path, entry("r1", {"scope": 1.0}))
    regression.append(path, entry("r2", {"scope": 0.5}))
    with open(path, "a", encoding="utf-8") as f:
        f.write('{"torn line\n')
    assert [e["run_id"] for e in regression.read(path)] == ["r1", "r2"]
    assert regression.last_entry(path)["run_id"] == "r2"
    assert regression.last_entry(path, exclude_run="r2")["run_id"] == "r1"
    monkeypatch.setenv("AQP_AGENT_QUALITY_DIR", str(tmp_path / "h"))
    assert regression.history_path("x").startswith(str(tmp_path / "h"))


def test_history_entry_from_a_run_result():
    result = {"run_id": "r9", "agent": "bot", "agent_version": "2", "dimensions": {
        "scope": {"verdict": "pass", "stats": {"pass_rate": 0.95}},
        "latency_cost": {"verdict": "fail", "stats": {}}}}
    e = regression.history_entry(result, 3, "2026-10-12")
    assert e["dimensions"] == {"scope": {"pass_rate": 0.95, "verdict": "pass"},
                               "latency_cost": {"pass_rate": 0.0, "verdict": "fail"}}
    assert e["dataset_version"] == 3
