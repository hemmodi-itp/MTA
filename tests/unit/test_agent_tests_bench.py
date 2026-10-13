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


def test_failing_counts_uncalibrated_judge_failures_only_on_request():
    res = {"dimensions": {d: {"outcome": "pass"} for d in ("scope", "hallucination")},
           "cases": [{"dimension": "hallucination", "runs": [{"outcome": "unverified_judge",
                                                              "judge": {"verdict": "fail"}}]}]}
    res["dimensions"]["scope"]["outcome"] = "fail"
    assert failing(res) == ["scope"]
    assert failing(res, include_unverified=True) == ["hallucination", "scope"]


def test_markdown_llm_renders(baseline):
    from tools.agent_tests import stats
    from tools.agent_tests.bench import markdown_llm
    from tools.agent_tests.runner import pass_rates, raw_pass_rates
    dims = list(baseline["dimensions"])
    row = {d: {"outcome": "pass", "verdict": "pass", "pass_rate": pass_rates(baseline)[d], "ci_low": 0.8,
               "ci_high": 1.0, "n": 10, "unverified_judge_runs": 0, "raw_pass_rate": raw_pass_rates(baseline)[d]}
           for d in dims}
    sc = score(baseline, {}, [])
    report = {"date": "2026-10-12", "bot_model": "bot", "judge_model": "judge", "judge_calls": 3,
              "calibrated_dimensions": [], "k": "per_dimension", "requests": 100,
              "summary": {"verified": sc, "including_unverified_judge": sc, "repeat": 2,
                          "stability_verified": stats.stability({d: [1.0, 1.0] for d in dims}, 0.01),
                          "stability_including_unverified_judge": stats.stability({d: [1.0, 0.9] for d in dims}, 0.01)},
              "baseline": [row, row]}
    md = markdown_llm(report)
    assert "real LLM" in md and "| task_success | pass | pass |" in md and "EXCEEDED" not in md.split("\n")[8]


def test_rescore_of_a_compacted_report_is_exact(baseline):
    from tools.agent_tests.bench import compact, rescore_llm
    flagged = {w: run_config(SPEC, CASES, [WEAK[w]["flag"]], 7, in_process=True) for w in ("BOT_BUG_03", "BOT_BUG_08")}
    weak = [WEAK[w] for w in flagged]
    full_v, full_u = score(baseline, flagged, weak), score(baseline, flagged, weak, include_unverified=True)
    report = {"summary": {}, "runs": {"baseline#1": compact(baseline), **{k: compact(v) for k, v in flagged.items()}}}
    again = rescore_llm(report)["summary"]
    assert again["verified"] == full_v and again["including_unverified_judge"] == full_u
