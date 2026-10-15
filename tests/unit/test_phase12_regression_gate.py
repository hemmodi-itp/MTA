"""Phase 12.5: benchmark metric regression gates (tools/benchmark/regression_gate.py)."""

import json

from tools.benchmark import regression_gate as rg


def _e2e(rate=0.5, ff=0.1, flaky=0.0, precision=None, recall=0.7):
    return {"metrics": {"seeded_bug_detection": {"rate": rate}, "false_failure": {"rate": ff}, "flaky": {"rate": flaky},
                        "heal_precision": {"precision": precision}, "ac_extraction_recall": recall}}


def _healing(detected=10, bugs=10, healed=9, wrong=0, clean_failed=0, success=90.0):
    return {"summary": {"bugs_detected": detected, "bugs": bugs, "healed": healed, "wrong_element_heals": wrong,
                        "heal_success_pct": success}, "clean": {"passed": 14, "failed": clean_failed}}


def _write(d, name, doc):
    (d / name).write_text(json.dumps(doc), encoding="utf-8")


def _setup(tmp_path, e2e_new, healing_new=None):
    res = tmp_path / "results"
    res.mkdir(parents=True)
    _write(res, "2026-10-01_buggy_shop_final.json", _e2e())
    _write(res, "2026-10-01_buggy_shop_phase6_healing.json", _healing())
    base = tmp_path / "baselines.json"
    rg.update(res, base)
    _write(res, "2026-10-02_buggy_shop_nightly.json", e2e_new)             # any label: recognised by structure
    if healing_new is not None:
        _write(res, "2026-10-02_buggy_shop_phase6_healing.json", healing_new)
    return res, base


def test_unchanged_metrics_pass(tmp_path):
    res, base = _setup(tmp_path, _e2e())
    code, rows, _notes = rg.gate(res, base)
    assert code == 0 and {r["file"] for r in rows if r["kind"] == "e2e"} == {"2026-10-02_buggy_shop_nightly.json"}


def test_detection_drop_fails_and_names_the_metric(tmp_path, capsys):
    res, base = _setup(tmp_path, _e2e(rate=0.4))
    assert rg.main(["--results", str(res), "--baselines", str(base)]) == 1
    out = capsys.readouterr().out
    assert "[FAIL] e2e.detection_rate = 0.4 (must not drop below 0.5)" in out
    assert "REGRESSION: e2e.detection_rate" in out


def test_false_failure_rise_fails(tmp_path):
    res, base = _setup(tmp_path, _e2e(ff=0.2))
    code, rows, _ = rg.gate(res, base)
    assert code == 1 and [r["metric"] for r in rows if not r["ok"]] == ["false_failure_rate"]


def test_improvements_pass(tmp_path):
    res, base = _setup(tmp_path, _e2e(rate=0.9, ff=0.0, recall=0.9))
    assert rg.gate(res, base)[0] == 0


def test_heal_precision_floor(tmp_path):
    res, base = _setup(tmp_path, _e2e(precision=0.9), _healing(healed=20, wrong=2))
    code, rows, _ = rg.gate(res, base)
    bad = {(r["kind"], r["metric"]) for r in rows if not r["ok"]}
    assert code == 1 and bad == {("e2e", "heal_precision"), ("phase6_healing", "heal_precision")}
    res2, base2 = _setup(tmp_path / "b", _e2e(precision=None))
    code, rows, _ = rg.gate(res2, base2)
    row = next(r for r in rows if r["kind"] == "e2e" and r["metric"] == "heal_precision")
    assert code == 0 and row["ok"] and row["note"] == "not measured in this run"


def test_required_kind_without_result_fails(tmp_path):
    res, base = _setup(tmp_path, _e2e())
    assert rg.gate(res, base, require=("phase7_nfr",))[0] == 1
    assert rg.gate(res, base, require=("phase6_healing",))[0] == 0


def test_kinds_by_name_and_structure(tmp_path):
    p = tmp_path / "2026-10-14_buggy_shop_phase6_healing_loc04_rerun.json"
    p.write_text(json.dumps(_healing()), encoding="utf-8")
    assert rg.kind_of(p) is None                                             # a one-off re-run is not the benchmark
    q = tmp_path / "2026-10-14_buggy_shop_phase8_whitebox.json"
    q.write_text("{}", encoding="utf-8")
    assert rg.kind_of(q) == "phase8_whitebox"


def test_repository_results_pass_their_baselines():
    code, rows, notes = rg.gate()
    assert code == 0, [r for r in rows if not r["ok"]]
    assert {r["kind"] for r in rows} == set(rg.KINDS), notes                # every kind has a committed result
