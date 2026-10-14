"""Phase 8.3 / 8.5 / 8.2-design: coverage report + gap mapping (real coverage.py data), JS coverage summary,
the mutation runner (always restores the file), and code rules flowing into test design with citations."""
import json
import shutil
import sys
import textwrap
from pathlib import Path

import pytest

from tools.whitebox import coverage_gap, js_coverage, mutation

APP = textwrap.dedent('''
    Form = JSONResponse = lambda *a, **k: None; app = type("A", (), {"post": staticmethod(lambda p: (lambda f: f))})()
    def validate(data):
        errors = []
        name = str(data.get("name") or "")
        if not name:
            errors.append("required")
        if len(name) > 5:
            errors.append("too long")
        return errors

    def other():
        return 1

    @app.post("/things")
    def create(request, name: str = Form("")):
        errors = validate({"name": name})
        if errors:
            return JSONResponse({"errors": errors}, status_code=422)
        return {"id": 1}
''')


def _coverage_of(tmp_path, calls):
    import coverage
    mod = tmp_path / "appmod.py"
    mod.write_text(APP, encoding="utf-8")
    sys.path.insert(0, str(tmp_path))
    try:
        cov = coverage.Coverage(data_file=str(tmp_path / ".coverage"), branch=True, source=[str(tmp_path)])
        cov.start()
        import importlib
        m = importlib.import_module("appmod")
        importlib.reload(m)
        for c in calls:
            c(m)
        cov.stop()
        cov.save()
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("appmod", None)
    return str(tmp_path / ".coverage"), mod


def test_report_and_gaps_map_missing_lines_to_routes(tmp_path):
    from tools.whitebox.extract import extract_source
    data, mod = _coverage_of(tmp_path, [lambda m: m.validate({"name": "ab"})])
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "appmod.py").write_text(APP, encoding="utf-8")
    code = extract_source(str(tmp_path / "src"), rel_to=str(tmp_path / "src"))
    # coverage measured tmp/appmod.py; point the code model at that file name
    code["functions"] = {k.replace("appmod.py", "appmod.py"): v for k, v in code["functions"].items()}
    rep = coverage_gap.report(data, code, root=tmp_path)
    assert rep["statement_pct"] < 100 and rep["branch_pct"] is not None and rep["branches"] > 0
    assert rep["files"]["appmod.py"]["missing_lines"]
    crit = {u["function"] for u in rep["uncovered_critical"]}
    assert "validate" in crit and "other" not in crit                 # "other" is no handler / rule function
    found = coverage_gap.gaps(rep, code)
    by = {g["function"]: g for g in found}
    assert by["validate"]["routes"] == ["POST /things"]                # helper -> the route that calls it
    assert "other" not in by                                           # no route reaches it


def test_js_coverage_summary(tmp_path):
    entry = [{"url": "http://h/p", "functions": [
        {"functionName": "a", "ranges": [{"startOffset": 0, "count": 1}]},
        {"functionName": "b", "ranges": [{"startOffset": 10, "count": 0}]}]}]
    (tmp_path / "1.json").write_text(json.dumps(entry))
    entry2 = [{"url": "http://h/p", "functions": [{"functionName": "b", "ranges": [{"startOffset": 10, "count": 2}]}]}]
    (tmp_path / "2.json").write_text(json.dumps(entry2))
    s = js_coverage.summarize(str(tmp_path))
    assert s["functions"] == 2 and s["covered"] == 2 and s["function_pct"] == 100.0


SRC = textwrap.dedent('''
    def check(n, flag=True):
        if n > 10 and flag:
            return False
        if not n:
            return False
        return n >= 3
''')


def test_mutants_cover_every_operator():
    descs = [m.description for m, _ in mutation.mutants(SRC, ["check"])]
    for want in ("Gt -> GtE", "And -> Or", "negate condition", "drop `not`", "GtE -> Gt", "10 -> 11", "True -> False"):
        assert want in descs, (want, descs)
    for _m, src in mutation.mutants(SRC, ["check"]):
        compile(src, "m", "exec")                                       # every mutant is valid Python


def test_runner_scores_and_always_restores(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text(SRC, encoding="utf-8")

    def suite() -> bool:                                                # a decent test: passes only on the original
        ns = {}
        exec(f.read_text(encoding="utf-8"), ns)
        c = ns["check"]
        return c(11) is False and c(0) is False and c(3) is True and c(2) is False and c(10) is True
    res = mutation.run(str(f), ["check"], suite, log=lambda *_: None)
    assert f.read_text(encoding="utf-8") == SRC
    assert not (tmp_path / ("mod.py" + mutation.BACKUP_SUFFIX)).exists()
    assert res["mutants"] >= 7 and res["killed"] >= 5 and 0 < res["score_pct"] <= 100
    assert all(s["status"] == "survived" for s in res["survivors"])


def test_runner_restores_after_a_crash_and_leftover_backup(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text(SRC, encoding="utf-8")
    (tmp_path / ("mod.py" + mutation.BACKUP_SUFFIX)).write_text(SRC, encoding="utf-8")
    f.write_text("broken = (", encoding="utf-8")                        # a previous run died mid-mutant
    calls = []

    def boom() -> bool:
        calls.append(1)
        raise RuntimeError("harness down")
    res = mutation.run(str(f), ["check"], boom, max_mutants=2, log=lambda *_: None)
    assert f.read_text(encoding="utf-8") == SRC and calls
    assert all(r["status"].startswith("error") for r in res["results"]) and res["score_pct"] is None


def test_code_rules_reach_test_design_with_citations(tmp_path):
    from tools.test_design import design as D
    from tools.test_design.inputs import DesignInputs
    from tools.whitebox.extract import extract_source
    src = Path("application_assets/projects/bench_buggy_shop")
    d = tmp_path / "p"
    (d / "test_comprehension").mkdir(parents=True)
    for n in ("requirements", "business_scenarios", "form_model", "app_map", "permission_matrix"):
        if (src / "test_comprehension" / f"{n}.json").exists():
            shutil.copy(src / "test_comprehension" / f"{n}.json", d / "test_comprehension")
    shutil.copy(src / "project.yaml", d)
    (d / "test_comprehension" / "code_rules.json").write_text(
        json.dumps(extract_source("benchmarks/apps/buggy_shop", rel_to=".")), encoding="utf-8")
    inp = DesignInputs.load(str(d), "b")
    price = next(fl for f in inp.forms if f.action == "/products" for fl in f.fields if fl.name == "price")
    assert price.constraints["pattern"]["source"] == "code"                 # only the code states the format
    assert price.constraints["range"]["source"] == "brd"                    # the BRD wins where it speaks
    assert price.citations["pattern"].endswith("app.py:91")
    cases, _ = D.generate_all(inp, {})
    D.cite_code(cases, inp)
    fmt = [c for c in cases if "wrong format" in c["title"] and "price" in c["title"].lower()]
    assert fmt and all(c["source"] == "code" and c["citations"] == ["benchmarks/apps/buggy_shop/app.py:91"] for c in fmt)


def test_saved_coverage_reaches_the_dashboard(tmp_path):
    from tools.reporting.insights import coverage_dashboard
    from tools.whitebox import coverage_gap
    rep = {"statement_pct": 82.9, "branch_pct": 63.8, "statements": 400, "branches": 120, "covered_branches": 77,
           "uncovered_critical": [{"function": "upload", "file": "app.py", "missing_lines": [3, 4]}]}
    path = coverage_gap.save(tmp_path, rep, "nightly")
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["uncovered_critical"] == [{"function": "upload", "file": "app.py", "lines": 2}]
    dash = coverage_dashboard([], None, {}, None, None, None, None, None, saved)
    assert dash["code"].startswith("statements 82.9%, branches 63.8% (coverage.py, nightly")
    assert "1 critical function" in dash["code"]
    assert coverage_dashboard([], None, {}, None, None, None, None)["code"].startswith("not measured")
