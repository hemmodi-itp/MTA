"""
export_scenarios — writes business_scenarios.json and business_scenarios.md
to the designated output directory.
"""

import json
import os
from typing import Dict, List

from tools.comprehension.models import BusinessScenario, TraceabilityReference


def load_existing_titles_by_module(output_dir: str) -> Dict[str, List[dict]]:
    """Return {module_id: [{"scenario_id": ..., "title": ...}, ...]} from an
    already-written business_scenarios.json, or {} if none exists yet.

    Used to tell the scenario-generation LLM what already exists for a
    module before it runs again on an updated BRD, so it doesn't re-propose
    scenarios that are already covered.
    """
    json_path = os.path.join(output_dir, "business_scenarios.json")
    if not os.path.exists(json_path):
        return {}
    try:
        with open(json_path, encoding="utf-8") as fh:
            payload = json.load(fh) or {}
    except Exception:
        return {}

    by_module: Dict[str, List[dict]] = {}
    for s in payload.get("scenarios", []):
        module_id = s.get("module_id")
        if not module_id:
            continue
        by_module.setdefault(module_id, []).append({
            "scenario_id": s.get("scenario_id", ""),
            "title": s.get("title", ""),
        })
    return by_module


def _traceability_line(ref: TraceabilityReference) -> str:
    parts = []
    if ref.source_file:
        parts.append(f"File: {ref.source_file}")
    if ref.requirement_id:
        parts.append(f"Req: {ref.requirement_id}")
    if ref.jira_story_id:
        parts.append(f"Jira: {ref.jira_story_id}")
    if ref.confluence_page_id:
        parts.append(f"Confluence: {ref.confluence_page_id}")
    if ref.section:
        parts.append(f"Section: {ref.section}")
    if ref.page_number is not None:
        parts.append(f"Page: {ref.page_number}")
    if ref.method_name:
        parts.append(f"Method: {ref.method_name}")
    return " | ".join(parts) if parts else "—"


def _scenario_to_md(scenario: BusinessScenario) -> str:
    lines = [
        f"## {scenario.scenario_id}: {scenario.title}",
        "",
        f"**Business Objective:** {scenario.business_objective}",
        f"**Actor:** {scenario.actor}",
        f"**Confidence:** {scenario.confidence_score:.0%}",
        "",
    ]

    if scenario.preconditions:
        lines.append("**Preconditions:**")
        for pc in scenario.preconditions:
            lines.append(f"- {pc}")
        lines.append("")

    lines.append("**Steps:**")
    for i, step in enumerate(scenario.steps, 1):
        lines.append(f"{i}. {step}")
    lines.append("")

    lines.append(f"**Expected Result:** {scenario.expected_result}")

    if scenario.business_rules:
        lines.append("")
        lines.append(
            f"**Business Rules:** {', '.join(scenario.business_rules)}"
        )

    if scenario.traceability:
        lines.append("")
        lines.append("**Traceability:**")
        for ref in scenario.traceability:
            lines.append(f"- {_traceability_line(ref)}")

    return "\n".join(lines)


def export_scenarios(
    scenarios: List[BusinessScenario],
    output_dir: str,
    project_name: str,
    module_ids: List[str] = None,
    merge: bool = True,
) -> dict:
    """
    Write business_scenarios.json and business_scenarios.md to output_dir.

    When *merge* is True (default), scenarios already on disk for OTHER
    modules/runs are preserved rather than clobbered — a run that only
    processes one module (e.g. a newly added M03) no longer discards the
    scenarios previously written for M01/M02. Scenario IDs are module-
    prefixed and content-signature-derived (see tools.state.artifact_registry),
    so merging is a safe upsert keyed by scenario_id.

    Returns:
        {"json": "<path>", "markdown": "<path>"}
    """
    os.makedirs(output_dir, exist_ok=True)

    json_path = os.path.join(output_dir, "business_scenarios.json")
    md_path = os.path.join(output_dir, "business_scenarios.md")

    merged_by_id: Dict[str, dict] = {}
    merged_module_ids: List[str] = []

    if merge and os.path.exists(json_path):
        try:
            with open(json_path, encoding="utf-8") as fh:
                existing_payload = json.load(fh) or {}
            for s in existing_payload.get("scenarios", []):
                sid = s.get("scenario_id")
                if sid:
                    merged_by_id[sid] = s
            merged_module_ids = list(existing_payload.get("modules", []))
        except Exception:
            merged_by_id = {}
            merged_module_ids = []

    for s in scenarios:
        merged_by_id[s.scenario_id] = s.model_dump()

    for mid in (module_ids or []):
        if mid not in merged_module_ids:
            merged_module_ids.append(mid)

    merged_scenarios = [
        BusinessScenario.model_validate(d) for d in merged_by_id.values()
    ]
    merged_scenarios.sort(key=lambda s: s.scenario_id)

    # --- JSON ---
    payload = {
        "project": project_name,
        "total_scenarios": len(merged_scenarios),
        "scenarios": [s.model_dump() for s in merged_scenarios],
    }
    if merged_module_ids:
        payload["modules"] = merged_module_ids
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)

    # --- Markdown ---
    md_lines = [
        f"# Business Scenarios — {project_name}",
        "",
        f"Total: **{len(merged_scenarios)} scenario(s)**",
        "",
        "---",
        "",
    ]
    for scenario in merged_scenarios:
        md_lines.append(_scenario_to_md(scenario))
        md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md_lines))

    return {"json": json_path, "markdown": md_path}
