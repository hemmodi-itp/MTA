"""Phase 12.1: property-based tests (hypothesis) for the generators and the renderer.

Each property states what must hold for EVERY input, not a few examples:
  renderer      any test name / value / message renders to a file whose strings are valid literals, whose brackets
                balance, and whose test titles parse back (selective / NFR title regexes)
  API rules     generated boundary values sit exactly where the rule says (accepted at the bound, rejected past it)
  paths         path templating is idempotent and maps every placeholder style to the same template
  quarantine    the failure signature is stable; a test is released exactly after `release_after` passes in a row
  selective     a fingerprint never differs from itself; the --grep pattern matches every chosen title
  mutation      every mutant parses and differs from the original
  linter        never crashes on plan-shaped input; score in 0..100
"""

import ast
import json
import os
import re
from datetime import date

from hypothesis import HealthCheck, assume, given, settings, strategies as st

from tools.execution import quarantine as qz
from tools.execution.selective import _TITLE_RE, _spec_titles, diff
from tools.test_creation.assertion_linter import lint_plan
from tools.test_creation.script_generator.spec_renderer import render_spec_from_plan
from tools.triage.service import grep_for_titles
from tools.whitebox.api_tests import _bad_cases, concrete_template
from tools.whitebox.mutation import mutants
from tools.whitebox.python_rules import template_path

# 150 examples per property keeps the whole file under ~10 s; MTA_HYPOTHESIS_EXAMPLES=3000 for a deep (nightly) run
EXAMPLES = int(os.environ.get("MTA_HYPOTHESIS_EXAMPLES") or 150)
FAST = settings(max_examples=EXAMPLES, deadline=None, suppress_health_check=[HealthCheck.too_slow])
text = st.text(st.characters(blacklist_categories=("Cs",)), min_size=0, max_size=40)
words = st.text(st.characters(whitelist_categories=("Ll", "Lu", "Nd")), min_size=1, max_size=12)
STRING = re.compile(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'|`(?:[^`\\]|\\.)*`')


def _code_only(ts: str) -> str:
    """The spec without string literals and // comments — what is left must be balanced code.
    Split on "\\n" only: str.splitlines() also breaks on \\x85, \\x0b, \\x1c… which are not JS line terminators, and
    U+2028/U+2029 are legal inside JS/TS string literals (ES2019; tsc accepts them) — json.dumps keeps \\r and \\n escaped."""
    out = []
    for line in ts.split("\n"):
        line = STRING.sub('""', line)
        out.append(line.split("//", 1)[0])
    return "\n".join(out)


# ── renderer ─────────────────────────────────────────────────────────

@FAST
@given(name=text.filter(lambda s: s.strip()), value=text, message=text, scenario_title=text,
       steps=st.booleans(), oracles=st.booleans())
def test_renderer_any_strings_stay_inside_literals(name, value, message, scenario_title, steps, oracles):
    plan = {"tests": [{"name": name, "type": "negative", "steps": [
        {"action": "navigate", "value": "/x"},
        {"action": "enterText", "locator_key": "field", "value": value},
        {"action": "verifyContainsText", "locator_key": "out", "value": value, "message": message or None}]}]}
    ts = render_spec_from_plan(plan, {"scenario_id": "M01_BS_001", "title": scenario_title}, "http://h",
                               "projects/p/test_creation/test_scripts/M01/t.spec.ts", test_steps=steps, oracles=oracles)
    code = _code_only(ts)
    assert '"' not in code.replace('""', ""), "a quote escaped its string literal"
    for o, c in ("()", "{}", "[]"):
        assert code.count(o) == code.count(c), f"unbalanced {o}{c}"
    assert f"action.enterText(\"field\", {json.dumps(value, ensure_ascii=False)})" in ts
    titles = _spec_titles(ts)
    assert len(titles) == 1 and name.strip()[:20] in titles[0].replace("\n", "\n")


@FAST
@given(titles=st.lists(text.filter(lambda s: s.strip()), min_size=1, max_size=5, unique=True))
def test_title_regex_round_trips_any_title(titles):
    body = "\n".join(f"  test({json.dumps(t, ensure_ascii=False)}, async ({{ page }}) => {{}});" for t in titles)
    assert _spec_titles(body) == titles
    from tools.nonfunctional.generate import _TITLE_RE as NFR_TITLE
    assert [json.loads(m) for m in NFR_TITLE.findall(body)] == titles
    assert [json.loads(m) for m in _TITLE_RE.findall(body)] == titles


@FAST
@given(titles=st.lists(text.filter(lambda s: s.strip()), min_size=1, max_size=6, unique=True))
def test_grep_matches_every_selected_title(titles):
    pattern = re.compile(grep_for_titles(titles))
    assert all(pattern.search(t) for t in titles)


# ── API boundary values ──────────────────────────────────────────────

def _num(expr: str) -> float:
    return float(json.loads(expr))


@FAST
@given(lo=st.decimals(min_value=-1000, max_value=1000, places=3, allow_nan=False),
       span=st.decimals(min_value="0.01", max_value=1000, places=3, allow_nan=False), integer=st.booleans())
def test_range_cases_sit_on_the_right_side_of_the_bound(lo, span, integer):
    lo, hi = float(lo), float(lo + span)
    if integer:
        lo, hi = float(int(lo)), float(int(lo) + max(1, int(span)))
    cases = {re.sub(r" \(?-?[\d.]+\)?$", "", label): (expr, exp)
             for label, expr, exp in _bad_cases({"field": "q", "kind": "range", "value": {
                 "min": lo, "max": hi, "integer": integer}}, "4xx")}
    at_min, below = cases["q at min"], cases["q below min"]
    at_max, above = cases["q at max"], cases["q above max"]
    assert at_min[1] == at_max[1] == "ACCEPT" and below[1] == above[1] == "4xx"
    assert lo <= _num(at_min[0]) <= hi and lo <= _num(at_max[0]) <= hi
    assert _num(below[0]) < lo and _num(above[0]) > hi
    for label, expr, _exp in _bad_cases({"field": "q", "kind": "range", "value": {"min": lo, "max": hi,
                                                                                 "integer": integer}}, "4xx"):
        if "(" in label:                                  # "q below min (-0.001)": the label states the value sent
            assert float(label.rsplit("(", 1)[1].rstrip(")")) == _num(expr), (label, expr)


@FAST
@given(lo=st.integers(0, 60), extra=st.integers(0, 60))
def test_length_cases_sit_on_the_right_side_of_the_bound(lo, extra):
    hi = lo + extra
    out = _bad_cases({"field": "n", "kind": "length", "value": {"min": lo, "max": hi}}, "4xx")
    sizes = {label: (int(re.search(r"sized\((\d+)\)", e).group(1)), exp) for label, e, exp in out}
    for label, (n, exp) in sizes.items():
        ok = lo <= n <= hi
        assert (exp == "ACCEPT") == ok, (label, n, exp)


# ── paths ────────────────────────────────────────────────────────────

segment = st.text(st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-_"), min_size=1, max_size=8)


@FAST
@given(parts=st.lists(st.tuples(segment, st.sampled_from(["", "brace", "flask", "colon", "num"])), min_size=1, max_size=5))
def test_path_templating_is_idempotent_and_style_independent(parts):
    styles = {"brace": "{pid}", "flask": "<int:pid>", "colon": ":pid"}
    raw, expected, concrete = [], [], []
    for seg, kind in parts:
        assume(not seg.isdigit())
        raw.append(styles.get(kind, seg) if kind != "num" else "7")
        expected.append("{id}" if kind in styles else ("7" if kind == "num" else seg))
        concrete.append("{id}" if kind in styles or kind == "num" else seg)
    path = "/" + "/".join(raw)
    t = template_path(path)
    assert t == "/" + "/".join(expected)
    assert template_path(t) == t
    assert concrete_template(path) == "/" + "/".join(concrete)


# ── quarantine ───────────────────────────────────────────────────────

@FAST
@given(err=text)
def test_signature_is_stable(err):
    s = qz.signature(err)
    assert qz.signature(s) == s and len(s) <= 160 and not re.search(r"\d", s)


@settings(max_examples=max(20, EXAMPLES // 3), deadline=None)          # real quarantine.yaml I/O per run
@given(runs=st.lists(st.sampled_from(["passed", "failed", "flaky", "skipped"]), min_size=1, max_size=14),
       release_after=st.integers(1, 5))
def test_quarantine_releases_exactly_after_n_passes_in_a_row(tmp_path_factory, runs, release_after):
    d = str(tmp_path_factory.mktemp("q"))
    q = qz.load(d)
    q["release_after"] = release_after
    key = qz.test_key("M01/a.spec.ts", "t")
    qz.add(q, key, "manual")
    qz.save(d, q)
    streak, released_at = 0, None
    for i, status in enumerate(runs):
        out = qz.record_run(d, [{"spec_file": "M01/a.spec.ts", "test_title": "t", "status": status}],
                            today=date(2026, 10, 1))
        if released_at is None:
            streak = streak + 1 if status == "passed" else (0 if status in ("failed", "flaky") else streak)
            if streak >= release_after:
                released_at = i
                assert out["released"] == [key]
            else:
                assert out["released"] == [] and qz.keys(qz.load(d)) == {key}
                assert qz.load(d)["tests"][0]["stable_runs"] == streak


# ── selective ────────────────────────────────────────────────────────

fp_part = st.dictionaries(words, st.text("0123456789abcdef", min_size=4, max_size=4), max_size=5)
fingerprint = st.fixed_dictionaries({k: fp_part for k in ("pages", "acs", "endpoints", "specs", "sources")})


@FAST
@given(a=fingerprint, b=fingerprint)
def test_fingerprint_diff(a, b):
    assert all(v == [] for v in diff(a, a).values())
    d = diff(a, b)
    for part, keys in d.items():
        assert set(keys) <= set(b[part]) and all(a[part].get(k) != b[part][k] for k in keys)


# ── mutation ─────────────────────────────────────────────────────────

@FAST
@given(lo=st.integers(-50, 50), hi=st.integers(-50, 50), flag=st.booleans(),
       op=st.sampled_from(["<", "<=", ">", ">=", "==", "!="]), join=st.sampled_from(["and", "or"]))
def test_every_mutant_parses_and_differs(lo, hi, flag, op, join):
    src = (f"def check(x, y):\n    if x {op} {lo} {join} not y:\n        return {flag}\n"
           f"    return x > {hi}\n\n\ndef other(z):\n    return z < 3\n")
    out = mutants(src, ["check"])
    assert out
    for m, mutated in out:
        ast.parse(mutated)
        assert mutated != src and m.function == "check"
        assert "return z < 3" in mutated                 # functions not selected are never touched


# ── linter ───────────────────────────────────────────────────────────

step = st.fixed_dictionaries({"action": st.sampled_from(
    ["navigate", "click", "enterText", "verifyText", "verifyContainsText", "verifyVisible", "verifyUrlContains",
     "reloadAndVerify", "rememberCount", "verifyCountChangedBy", "unknownAction"])},
    optional={"locator_key": words, "value": text, "steps": st.just([{"action": "verifyText", "value": "x"}])})


@FAST
@given(tests=st.lists(st.fixed_dictionaries({"steps": st.lists(step, max_size=8)},
                                            optional={"name": text, "type": st.sampled_from(
                                                ["positive", "negative", "boundary", None])}), max_size=4))
def test_linter_never_crashes_and_scores_in_range(tests):
    out = lint_plan({"tests": tests})
    assert len(out["results"]) == len(tests)
    assert all(0 <= r["score"] <= 100 for r in out["results"]) and 0 <= out["median"] <= 100
