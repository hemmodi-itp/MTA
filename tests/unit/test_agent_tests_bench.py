"""
buggy_bot benchmark (tools/agent_tests/bench.py), in-process: acceptance criteria 1 and 3 as tests.

  * all flags off  → no dimension fails and none is undecided (false-positive check)
  * each weakness  → detected in a `detected_by` dimension, no failure outside detected_by ∪ may_affect
  * same seed      → identical verdicts on a second run
BOT_BUG_10 (latency) sleeps 1.2 s per reply, so it is run on the latency dimension only.
"""

import pytest

from tools.agent_tests.bench import bot_env, failing, load_weaknesses, markdown, run_config, score
from tools.agent_tests.dataset import agent_dir, load_cases, spec_for
from tools.agent_tests.runner import verdict_signature

pytestmark = pytest.mark.mta

SPEC = spec_for(agent_dir("buggy_bot"))
CASES = load_cases(agent_dir("buggy_bot"))[0]
WEAK = {w["id"]: w for w in load_weaknesses()}


@pytest.fixture(scope="module")
def baseline():
    return run_config(SPEC, CASES, [], 7, in_process=True)


def test_ground_truth_covers_every_dimension_with_a_seeded_weakness():
    from tools.agent_tests.models import DIMENSIONS
    covered = {d for w in WEAK.values() for d in w["detected_by"]}
    assert covered == set(DIMENSIONS) - {"task_success"}, sorted(set(DIMENSIONS) - covered)
    assert len(WEAK) == 14 and all(set(w["detected_by"]) <= set(DIMENSIONS) for w in WEAK.values())


def test_baseline_has_no_false_positives(baseline):
    assert failing(baseline) == []
    assert all(v["outcome"] == "pass" for v in baseline["dimensions"].values()), \
        {d: v["outcome"] for d, v in baseline["dimensions"].items() if v["outcome"] != "pass"}
    assert baseline["canary_hits"] == [] and baseline["cut"] == []


@pytest.mark.parametrize("wid", [w for w in WEAK if w != "BOT_BUG_10"])
def test_weakness_detected_without_collateral(baseline, wid):
    res = run_config(SPEC, CASES, [WEAK[wid]["flag"]], 7, in_process=True)
    s = score(baseline, {wid: res}, [WEAK[wid]])
    row = s["weaknesses"][0]
    assert row["detected"], (wid, failing(res))
    assert row["collateral"] == [], (wid, row["collateral"])


def test_latency_weakness_detected():
    res = run_config(SPEC, CASES, ["BOT_BUG_10"], 7, in_process=True, dimensions=["latency_cost"])
    lat = res["dimensions"]["latency_cost"]
    assert lat["outcome"] == "fail"
    assert {c["name"]: c["result"] for c in lat["budget_checks"]}["latency.p50_ms"] == "fail"


def test_same_seed_gives_identical_verdicts(baseline):
    again = run_config(SPEC, CASES, [], 7, in_process=True)
    assert verdict_signature(again) == verdict_signature(baseline)
    flaky = run_config(SPEC, CASES, ["BOT_BUG_06"], 7, in_process=True)
    flaky2 = run_config(SPEC, CASES, ["BOT_BUG_06"], 7, in_process=True)
    assert verdict_signature(flaky) == verdict_signature(flaky2)  # seeded inconsistency is reproducible


def test_canary_is_planted_per_run_and_found_when_leaked():
    res = run_config(SPEC, CASES, ["BOT_BUG_01"], 7, in_process=True, dimensions=["data_leakage"])
    planted = res["tokens"]["CANARY_SYS"]
    assert planted.startswith("CANARY-SYS-") and planted != "CANARY-SYS-4F7A"
    details = [c["detail"] for case in res["cases"] for c in case["runs"][0]["checks"] if c["result"] == "fail"]
    assert any("base64" in d for d in details), details  # the encoded-instructions probe leaks it in base64


def test_bot_env_clears_stray_flags():
    env = bot_env(["BOT_BUG_03"], "CANARY-SYS-1", 7, base={"BOT_BUG_01": "1", "BOT_BUGS": "all", "PATH": "x"})
    assert env["BOT_BUG_03"] == "1" and "BOT_BUG_01" not in env and "BOT_BUGS" not in env
    assert env["BOT_CANARY"] == "CANARY-SYS-1" and env["BOT_MODE"] == "mock" and env["PATH"] == "x"


def test_markdown_report_renders(baseline):
    report = {"date": "2026-10-12", "seed": 7, "transport": "asgi", "dataset": {"dataset_version": 1, "total": 1,
              "unreviewed": 1}, "summary": {**score(baseline, {}, []), "deterministic": True, "repeat": 1},
              "baseline": {d: v["outcome"] for d, v in baseline["dimensions"].items()},
              "latency": {"baseline": baseline["latency"]}}
    md = markdown(report)
    assert "Seeded weaknesses detected" in md and "| task_success | pass |" in md


def test_compact_keeps_only_failure_evidence():
    from tools.agent_tests.bench import compact
    res = run_config(SPEC, CASES, ["BOT_BUG_08"], 7, in_process=True, dimensions=["scope", "task_success"])
    small = compact(res)
    assert small["cases"] and all(c["outcome"] != "pass" for c in small["cases"])
    assert small["passed_cases"] + len(small["cases"]) == len(res["cases"])
    assert small["dimensions"] == res["dimensions"]
