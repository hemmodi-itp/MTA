"""
fallback_core.py — Deterministic Python fallbacks for all LLM-based agents.

Each function produces output in the IDENTICAL JSON format as its LLM counterpart.
Downstream agents cannot tell which path ran. Content is reduced in coverage but
always syntactically valid and safe to consume.

Functions:
    fallback_semantic_map       — keyword-score scenario→element mapping
    fallback_generate_test_data — 3 fixed test-data variants per scenario
    fallback_generate_script    — minimal .spec.ts (1 positive + skips)
    fallback_report             — minimal JSON report

These are called by agents as their Tier-2 route when both LLM (Tier 0) and
NSHTTPConnector (Tier 1) fail.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# 1. Semantic map fallback
# ─────────────────────────────────────────────────────────────────────────────

def fallback_semantic_map(
    scenarios: List[Dict[str, Any]],
    elements: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Keyword-overlap semantic mapping: for each scenario, find the DOM elements
    whose tag / placeholder / description text overlaps most with the scenario steps.

    Returns:
        {
            "BS-007": {
                "scenario_title": "...",
                "relevant_elements": [
                    {"locator_id": "LOC-0002", "playwright_expr": "...", "relevance": "keyword match"}
                ]
            }
        }
    """
    result: Dict[str, Any] = {}
    for scenario in scenarios:
        sid = scenario.get("scenario_id", "")
        title = scenario.get("title", scenario.get("scenario_name", sid))
        steps_text = " ".join(
            s if isinstance(s, str) else str(s.get("description", "")) + " " + str(s.get("action", ""))
            for s in scenario.get("steps", [])
        ).lower()
        step_tokens = set(re.findall(r"\w+", steps_text))

        scored = []
        for el in elements:
            el_text = " ".join(filter(None, [
                el.get("tag", ""),
                el.get("placeholder", ""),
                el.get("description", ""),
                el.get("aria_label", ""),
                el.get("text_content", ""),
            ])).lower()
            el_tokens = set(re.findall(r"\w+", el_text))
            overlap = len(step_tokens & el_tokens)
            if overlap > 0:
                scored.append((overlap, el))

        scored.sort(key=lambda x: -x[0])
        top_elements = []
        for _, el in scored[:5]:
            playwright_expr = _extract_playwright_expr(el)
            if playwright_expr:
                top_elements.append({
                    "locator_id": el.get("locator_id", ""),
                    "playwright_expr": playwright_expr,
                    "relevance": "keyword match (fallback)",
                })

        result[sid] = {
            "scenario_title": title,
            "relevant_elements": top_elements,
            "fallback": True,
        }
    return result


def _extract_playwright_expr(el: Dict[str, Any]) -> Optional[str]:
    """Extract the best Playwright expression from a dom_elements.json element entry."""
    pw = el.get("playwright_locators") or {}
    if pw.get("get_by_placeholder"):
        ph = pw["get_by_placeholder"].get("placeholder", "")
        return f'page.getByPlaceholder("{ph}")' if ph else None
    if pw.get("get_by_role"):
        role = pw["get_by_role"].get("role", "")
        name = pw["get_by_role"].get("name", "")
        return f'page.getByRole("{role}", {{ name: "{name}" }})' if role else None
    if pw.get("get_by_text"):
        text = pw["get_by_text"].get("text", "")
        return f'page.getByText("{text}")' if text else None
    rec = el.get("recommended_locator") or {}
    v = rec.get("value") or {}
    t = rec.get("type", "")
    if t == "id" and v.get("id"):
        return f'page.locator("#{v["id"]}")'
    if t == "name" and v.get("name"):
        return f'page.locator(\'[name="{v["name"]}"]\')'
    css = (el.get("technical_locators") or {}).get("css", "")
    return f'page.locator("{css}")' if css else None


# ─────────────────────────────────────────────────────────────────────────────
# 2. Test data fallback
# ─────────────────────────────────────────────────────────────────────────────

def fallback_generate_test_data(scenarios: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    3 fixed variants per scenario: positive, empty-field-negative, boundary-max.

    Output format matches test_data.json ScenarioTestData schema exactly.
    """
    results = []
    for scenario in scenarios:
        sid = scenario.get("scenario_id", "")
        title = scenario.get("title", scenario.get("scenario_name", sid))
        results.append({
            "scenario_id": sid,
            "scenario_name": title,
            "positive_dataset": {
                "description": "Positive case — all required fields with valid values",
                "data": {},
            },
            "negative_variants": [
                {
                    "variant_id": f"{sid}-NEG-001",
                    "variant_type": "empty_required_field",
                    "description": "All required fields left blank",
                    "data": {},
                },
                {
                    "variant_id": f"{sid}-NEG-002",
                    "variant_type": "boundary_max_length",
                    "description": "All text fields filled with 255-character string",
                    "data": {"__all_text_fields__": "a" * 255},
                },
            ],
            "fallback": True,
        })
    return results


# ─────────────────────────────────────────────────────────────────────────────
# 3. Script generation fallback
# ─────────────────────────────────────────────────────────────────────────────

_TS_FALLBACK_TEMPLATE = """\
import {{ test, expect }} from '@playwright/test';

const BASE_URL = process.env.BASE_URL || '{base_url}';

test.describe('{scenario_title} ({scenario_id}) [degraded fallback]', () => {{

  test('positive — navigate to page and verify title is non-empty', async ({{ page }}) => {{
    await page.goto(BASE_URL);
    const title = await page.title();
    expect(title, 'Page title must be non-empty after navigation').toBeTruthy();
  }});

{skips}
}});
"""

_TS_SKIP_TEMPLATE = """\
  test.skip('{step_label}', () => {{
    // degraded fallback — locator unknown for: {step_desc}
  }});
"""


def fallback_generate_script(
    scenario: Dict[str, Any],
    elements: List[Dict[str, Any]],
    test_data: Optional[Dict[str, Any]],
    base_url: str = "",
) -> str:
    """
    Generate a valid TypeScript Playwright .spec.ts file.

    Produces 1 positive test (goto + title assertion) plus skip stubs for each
    step that lacks a confirmed locator. The file is syntactically valid and
    collects correctly under npx playwright test.
    """
    sid = scenario.get("scenario_id", "BS-000")
    title = scenario.get("title", scenario.get("scenario_name", sid))
    steps = scenario.get("steps", [])

    skips = []
    for i, step in enumerate(steps, start=1):
        # BusinessScenario.steps is List[str] in the live comprehension schema,
        # but older/other callers may pass List[dict] — handle both.
        if isinstance(step, dict):
            desc = step.get("description", step.get("action", f"step {i}"))
        else:
            desc = str(step) if step else f"step {i}"
        label = f"step {i:02d} — {desc[:60]}"
        skips.append(_TS_SKIP_TEMPLATE.format(
            step_label=label.replace("'", "\\'"),
            step_desc=desc.replace("'", "\\'"),
        ))

    return _TS_FALLBACK_TEMPLATE.format(
        base_url=base_url or "http://localhost:3000",
        scenario_title=title.replace("'", "\\'"),
        scenario_id=sid,
        skips="\n".join(skips),
    )


def fallback_generate_script_filename(scenario_id: str, title: str) -> str:
    """Return the canonical .spec.ts filename for a scenario."""
    safe = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return f"test_{scenario_id}_{safe}.spec.ts"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Report fallback
# ─────────────────────────────────────────────────────────────────────────────

def fallback_report(playwright_json_path: str, output_dir: str) -> Optional[str]:
    """
    Write a minimal report_fallback.json from raw Playwright JSON results.

    Returns the path of the written file, or None if playwright_json_path does
    not exist.
    """
    if not os.path.exists(playwright_json_path):
        return None

    with open(playwright_json_path, encoding="utf-8") as f:
        data = json.load(f)

    passed = 0
    failed = 0
    failing_tests: List[str] = []

    for suite in data.get("suites", []):
        for spec in suite.get("specs", []):
            for test in spec.get("tests", []):
                if test.get("status") == "passed":
                    passed += 1
                else:
                    failed += 1
                    failing_tests.append(f"{spec.get('file', '')}::{spec.get('title', '')}")

    report = {
        "fallback": True,
        "passed": passed,
        "failed": failed,
        "total": passed + failed,
        "failing_tests": failing_tests,
    }

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "report_fallback.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return out_path
