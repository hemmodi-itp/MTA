"""
Judge calibration (tools/agent_tests/calibration.py, Phase 9.3) — acceptance criterion 4:
export a labelling sheet → (labels) → Cohen's κ per dimension → calibration.json → the Judge counts only verified
dimensions. Uses the synthetic labelled example (hand-computed κ) and a fully synthetic end-to-end loop.
"""

import csv
import os

import pytest

from tools.agent_tests.calibration import (Calibration, cohens_kappa, compute, export_sheet, judged_items, read_labels,
                                           save, stratified)
from tools.agent_tests.dataset import REPO_ROOT

pytestmark = pytest.mark.mta

SYNTHETIC = os.path.join(REPO_ROOT, "tools", "agent_tests", "examples", "calibration_synthetic.csv")


def test_kappa_reference_values():
    # 6 agree-pass, 4 agree-fail, 2 disagreements: p_o = 10/12, p_e = (7/12)^2 + (5/12)^2 → κ = 0.6571
    a = ["pass"] * 6 + ["fail"] * 4 + ["pass", "fail"]
    b = ["pass"] * 6 + ["fail"] * 4 + ["fail", "pass"]
    assert cohens_kappa(a, b) == pytest.approx(0.6571, abs=1e-4)
    assert cohens_kappa(["pass", "fail"], ["fail", "pass"]) == pytest.approx(-1.0)
    assert cohens_kappa(["pass"] * 4, ["pass"] * 4) == 1.0      # p_e = 1: perfect agreement by convention
    assert cohens_kappa([], []) is None
    with pytest.raises(ValueError):
        cohens_kappa(["pass"], [])


def test_synthetic_example_kappa_per_dimension():
    rep = compute(read_labels(SYNTHETIC))
    dims = rep["dimensions"]
    assert dims["task_success"] == {"n": 12, "agreement": 0.8333, "kappa": 0.6571, "status": "verified"}
    assert dims["scope"]["kappa"] == pytest.approx(0.0909, abs=1e-4) and dims["scope"]["status"] == "unverified"
    assert dims["hallucination"]["status"] == "insufficient_labels"
    assert "groundedness" not in dims and rep["skipped_rows"] == 3   # blank / skip / judge-unsure rows ignored
    assert rep["labelled_items"] == 26 and rep["enough_items"] is False


def _fake_result(n_per_dim=20, run_id="r1"):
    cases = []
    for dim in ("task_success", "scope", "hallucination"):
        for i in range(n_per_dim):
            verdict = "pass" if i % 3 else "fail"
            cases.append({"id": f"AT-X-{dim[:4]}{i:03d}", "dimension": dim, "rubric": "r", "runs": [{
                "outcome": "unverified_judge", "judge": {"verdict": verdict, "score": 80, "reasoning": "why"},
                "transcript": [{"session": "A", "user": "q", "reply": "a"}]}]})
    return {"run_id": run_id, "cases": cases}


def test_export_is_stratified_deterministic_and_at_least_50(tmp_path):
    items = judged_items([_fake_result()])
    assert len(items) == 60
    picked = stratified(items, 50, seed=1)
    assert len(picked) == 50 and {i["dimension"] for i in picked} == {"task_success", "scope", "hallucination"}
    assert [i["item_id"] for i in picked] == [i["item_id"] for i in stratified(judged_items([_fake_result()]), 50, 1)]
    out = tmp_path / "sheet.csv"
    written, available = export_sheet([_fake_result()], str(out), target=50)
    assert (written, available) == (50, 60)
    rows = list(csv.DictReader(open(out, encoding="utf-8")))
    assert len(rows) == 50 and all(r["human_label"] == "" for r in rows) and rows[0]["conversation"].startswith("USER")


def test_end_to_end_export_label_compute_and_judge_uses_it(tmp_path):
    sheet = tmp_path / "sheet.csv"
    export_sheet([_fake_result()], str(sheet), target=60)
    rows = list(csv.DictReader(open(sheet, encoding="utf-8")))
    # a "human" agrees with the judge on task_success and contradicts it on scope
    for r in rows:
        if r["dimension"] == "task_success":
            r["human_label"] = r["judge_verdict"]
        elif r["dimension"] == "scope":
            r["human_label"] = "fail" if r["judge_verdict"] == "pass" else "pass"
    with open(sheet, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    report = compute(read_labels(str(sheet)))
    assert report["dimensions"]["task_success"]["status"] == "verified"
    assert report["dimensions"]["scope"]["status"] == "unverified" and report["dimensions"]["scope"]["kappa"] < 0
    save(str(tmp_path), report, "judge-model-a")
    cal = Calibration.load(str(tmp_path))
    assert cal.is_verified("task_success") and not cal.is_verified("scope") and not cal.is_verified("hallucination")
    assert cal.applies_to("judge-model-a") and not cal.applies_to("judge-model-b")
    assert Calibration.load(str(tmp_path / "nowhere")).verified_dimensions() == []


def test_cli_calibrate_export_and_compute(tmp_path, monkeypatch, capsys):
    import json
    import shutil

    from tools.agent_tests import cli
    (tmp_path / "bot").mkdir()
    shutil.copy(os.path.join(REPO_ROOT, "eval_sets", "buggy_bot", "agent.yaml"), tmp_path / "bot" / "agent.yaml")
    res = tmp_path / "run.json"
    res.write_text(json.dumps(_fake_result()), encoding="utf-8")
    sheet = tmp_path / "s.csv"
    assert cli.main(["--root", str(tmp_path), "calibrate", "export", "--agent", "bot", "--from", str(res),
                     "--out", str(sheet)]) == 0
    assert cli.main(["--root", str(tmp_path), "calibrate", "compute", "--agent", "bot", "--labels", SYNTHETIC]) == 0
    out = capsys.readouterr().out
    assert "Wrote 50 item(s)" in out and "task_success" in out and "verified" in out
    assert (tmp_path / "bot" / "calibration.json").exists()


def test_default_export_target_covers_every_dimension(tmp_path):
    out = tmp_path / "s.csv"
    written, available = export_sheet([_fake_result(n_per_dim=20)], str(out))  # 3 dimensions × 20
    assert (written, available) == (50, 60)          # max(50, 3 × 10)
    many = {"run_id": "r", "cases": [{**c, "dimension": f"d{i % 8}"} for i, c in
                                     enumerate(_fake_result(n_per_dim=40)["cases"])]}
    written, _ = export_sheet([many], str(out))
    assert written == 80                             # 8 dimensions × 10 > 50
