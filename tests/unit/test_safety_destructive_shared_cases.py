"""Phase 4.4 — the run-time destructive guard (application_assets/_shared/runtime/destructive.ts) and the plan-time
classifier (tools/safety/action_classifier.py) share tests/fixtures/destructive_cases.json and one rule file."""

import json
import os

import pytest

from tools.safety.action_classifier import classify_step

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SHARED = json.load(open(os.path.join(ROOT, "tests", "fixtures", "destructive_cases.json"), encoding="utf-8"))


@pytest.mark.parametrize("case", SHARED["cases"], ids=[c["name"] for c in SHARED["cases"]])
def test_shared_case(case):
    v = classify_step(case["step"], SHARED["locator_map"])
    assert (v.destructive, v.category) == (case["destructive"], case["category"])


def test_the_ts_guard_reads_the_same_rule_file():
    ts = open(os.path.join(ROOT, "application_assets", "_shared", "runtime", "destructive.ts"), encoding="utf-8").read()
    assert "path.join('tools', 'safety', 'destructive_rules.yaml')" in ts
