"""Phase 12.2: golden snapshots for spec_renderer (plan -> .spec.ts).

Each tests/golden/spec_renderer/<case>.json holds the renderer's inputs; <case>.spec.ts is the expected output
(<case>.flows.ts for a case with `flows`). A renderer change that alters any output fails here with a diff.
After an intended change, re-record and review the diff in git:

    MTA_UPDATE_GOLDEN=1 python -m pytest tests/unit/test_phase12_golden.py
"""

import difflib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.test_creation.script_generator.spec_renderer import render_flows_module, render_spec_from_plan

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests" / "golden" / "spec_renderer"
CASES = sorted(p.stem for p in GOLDEN.glob("*.json"))
UPDATE = os.environ.get("MTA_UPDATE_GOLDEN") == "1"


def _render(case: str) -> dict:
    doc = json.loads((GOLDEN / f"{case}.json").read_text(encoding="utf-8"))
    out = {f"{case}.spec.ts": render_spec_from_plan(
        doc["plan"], doc["scenario"], doc["base_url"], doc["spec_rel_path"], project=doc.get("project"),
        flows_meta=doc.get("flows_meta"), test_steps=doc.get("test_steps", False),
        locator_map=doc.get("locator_map"), oracles=doc.get("oracles", False))}
    if doc.get("flows"):
        out[f"{case}.flows.ts"] = render_flows_module(doc["flows"], doc["project"])
    return out


@pytest.mark.parametrize("case", CASES)
def test_golden(case):
    for name, text in _render(case).items():
        path = GOLDEN / name
        if UPDATE or not path.exists():
            path.write_text(text, encoding="utf-8", newline="\n")
            continue
        expected = path.read_text(encoding="utf-8")
        if text != expected:
            diff = "".join(difflib.unified_diff(expected.splitlines(True), text.splitlines(True),
                                                f"golden/{name}", "rendered", n=2))
            pytest.fail(f"{name} differs from its golden snapshot "
                        f"(MTA_UPDATE_GOLDEN=1 to re-record after an intended change):\n{diff[:4000]}")


def test_golden_cases_cover_every_action():
    from tools.test_creation.script_generator.spec_renderer import ARG_BUILDERS
    used = set()
    for case in CASES:
        def walk(steps):
            for s in steps:
                used.add(s["action"])
                walk(s.get("steps") or [])
        doc = json.loads((GOLDEN / f"{case}.json").read_text(encoding="utf-8"))
        for t in doc["plan"]["tests"]:
            walk(t["steps"])
    assert set(ARG_BUILDERS) - used == set(), "add the new action to tests/golden/spec_renderer/every_action.json"


@pytest.mark.skipif(shutil.which("npx") is None or not (ROOT / "node_modules").is_dir(),
                    reason="needs node_modules (npm ci)")
def test_golden_specs_type_check():
    """Every golden spec compiles against the real ActionEngine fixture (tsc --noEmit)."""
    tmp = ROOT / "application_assets" / "projects" / "_golden_tsc"
    scripts = tmp / "test_creation" / "test_scripts" / "M01"
    shutil.rmtree(tmp, ignore_errors=True)
    scripts.mkdir(parents=True)
    cfg = ROOT / ".tsconfig.golden.tmp.json"
    try:
        for case in CASES:
            for name in _render(case):
                src = (GOLDEN / name).read_text(encoding="utf-8")
                if name.endswith(".flows.ts"):
                    (tmp / "test_creation" / "flows.generated.ts").write_text(src, encoding="utf-8")
                else:
                    (scripts / f"test_{case}.spec.ts").write_text(src, encoding="utf-8")
        cfg.write_text(json.dumps({"extends": "./tsconfig.json", "include": [
            "application_assets/_shared/**/*.ts", "application_assets/projects/_golden_tsc/**/*.ts"]}), encoding="utf-8")
        res = subprocess.run("npx tsc --noEmit -p .tsconfig.golden.tmp.json", cwd=ROOT, shell=True,
                             capture_output=True, text=True, timeout=300)
        # Only the goldens are judged: the shared runtime's own type debt is not this test's subject.
        errors = [ln for ln in (res.stdout + res.stderr).splitlines() if "_golden_tsc" in ln]
        assert not errors, "\n".join(errors[:40])
        assert "error ts" in res.stdout.lower() or res.returncode == 0 or not res.stderr, res.stderr[-2000:]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        cfg.unlink(missing_ok=True)
