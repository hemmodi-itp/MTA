"""Phase 12.6: mutation testing of MTA itself (tools/selftest/mutate_mta.py) and the runner's time box."""

import time

from tools.selftest import mutate_mta as mm
from tools.whitebox import mutation

SRC = "def f(x):\n    if x > 3:\n        return 1\n    return 0\n"


def test_every_target_and_its_tests_exist():
    for name, (src, tests) in mm.TARGETS.items():
        assert (mm.ROOT / src).is_file(), name
        assert tests and all((mm.ROOT / t).is_file() for t in tests), name


def test_time_box_stops_new_mutants_and_restores(tmp_path):
    f = tmp_path / "m.py"
    f.write_text(SRC, encoding="utf-8")
    res = mutation.run(str(f), ["f"], lambda: False, log=lambda *_: None, deadline=time.monotonic() - 1)
    assert res["mutants"] == 0 and res["not_run"] == len(mutation.mutants(SRC, ["f"])) > 0
    assert f.read_text(encoding="utf-8") == SRC
    res = mutation.run(str(f), ["f"], lambda: False, log=lambda *_: None)
    assert res["not_run"] == 0 and res["killed"] == res["mutants"] > 0 and f.read_text(encoding="utf-8") == SRC


def test_markdown_lists_scores_and_survivors():
    res = {"date": "2026-10-15", "max_mutants": 2, "time_box_min": 1, "seconds": 9, "restored": True,
           "total": {"mutants": 3, "killed": 2, "survived": 1, "score_pct": 66.7, "not_run": 0},
           "targets": {"bva": {"file": "tools/test_design/bva.py", "mutants": 3, "killed": 2, "survived": 1,
                               "score_pct": 66.7, "survivors": [{"line": 12, "function": "numeric_points",
                                                                 "description": "Lt -> LtE"}]}}}
    md = mm.markdown(res)
    assert "2/3 mutants killed (**66.7%**)" in md and "git diff empty" in md
    assert "- bva `tools/test_design/bva.py:12` in `numeric_points`: Lt -> LtE" in md
