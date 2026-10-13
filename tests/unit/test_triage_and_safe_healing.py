import json
import logging
import os

import pytest

from agents.test_execution.healing.tools import HealingRunContext, _apply_patch
from tools.triage.triage import classify, triage_report

SAMPLES = [
    ("test_defect.locator", "failed", "Error: strict mode violation: getByRole('button') resolved to 2 elements", []),
    ("test_defect.locator", "failed", "[locator_key=login_btn] Timeout 30000ms exceeded. waiting for getByRole('button')", []),
    ("test_defect.data", "failed", "Error: user already exists (duplicate email)", []),
    ("product_defect", "failed", "expect(received).toHaveText(expected)\nExpected: 'Total: $10'\nReceived: 'Total: $12'", []),
    ("product_defect", "failed", "expect(response.status()).toBe(200)\nReceived: 500 Internal Server Error", []),
    ("product_defect", "failed", "Error: expect(consoleErrors.length).toBe(0)", [{"type": "console_new_error", "description": "TypeError: x"}]),
    ("environment", "failed", "page.goto: net::ERR_CONNECTION_REFUSED at http://localhost:3000", []),
    ("environment", "failed", "Error: 503 Service Unavailable from gateway", []),
    ("flaky", "flaky", "", []),
]


@pytest.mark.parametrize("expected,status,err,ann", SAMPLES)
def test_triage_classification(expected, status, err, ann):
    r = classify(status, err, ann)
    assert r["verdict"] == expected and r["evidence"]


def test_triage_report_reads_playwright_json(tmp_path):
    rep = {"suites": [{"specs": [{"file": "x/test_creation/test_scripts/M1/a.spec.ts", "title": "t1", "tests": [
        {"status": "unexpected", "results": [{"error": {"message": "strict mode violation: foo"}}]}]}]}]}
    p = tmp_path / "r.json"
    p.write_text(json.dumps(rep))
    out = triage_report(str(p))
    assert out["tests"][0]["spec_file"] == "M1/a.spec.ts" and out["tests"][0]["verdict"] == "test_defect.locator"


SPEC = "import { test } from '@playwright/test';\ntest('t1', async ({ page }) => {\n  await page.click('#a');\n});\n"
NEW = "test('t1', async ({ page }) => {\n  await page.locator('#b').click();\n});"


def _ctx(tmp_path, mode):
    (tmp_path / "a.spec.ts").write_text(SPEC)
    return HealingRunContext("p", str(tmp_path), "", "", [], {}, "", {}, {}, logging.getLogger("t"),
                             mode=mode, proposals_dir=str(tmp_path / "prop"))


def test_propose_mode_writes_diff_and_leaves_spec(tmp_path):
    ctx = _ctx(tmp_path, "propose")
    r = _apply_patch(ctx, "a.spec.ts", "t1", NEW)
    assert r["proposed"] and not r["applied"]
    assert (tmp_path / "a.spec.ts").read_text() == SPEC
    assert "#b" in open(r["diff"], encoding="utf-8").read()


def test_auto_mode_applies(tmp_path):
    ctx = _ctx(tmp_path, "auto")
    assert _apply_patch(ctx, "a.spec.ts", "t1", NEW)["applied"]


def test_apply_patch_rejects_wait_for_timeout(tmp_path):
    for mode in ("auto", "propose"):
        ctx = _ctx(tmp_path, mode)
        bad = NEW.replace("});", "  await page.waitForTimeout(2000);\n});")
        r = _apply_patch(ctx, "a.spec.ts", "t1", bad)
        assert not r["applied"] and "fixed sleep" in r["reason"] and not r.get("proposed")
        assert (tmp_path / "a.spec.ts").read_text() == SPEC
