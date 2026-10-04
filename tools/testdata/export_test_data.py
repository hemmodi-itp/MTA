import json
import os
from typing import Dict, List

from tools.testdata.models import ScenarioTestData


def export_test_data(
    datasets: List[ScenarioTestData],
    output_dir: str,
    project_name: str,
) -> Dict[str, str]:
    """
    Write test data to JSON and Markdown files under output_dir.
    Returns a dict with the output paths.
    """
    os.makedirs(output_dir, exist_ok=True)

    json_path = os.path.join(output_dir, "test_data.json")
    md_path = os.path.join(output_dir, "test_data.md")

    _write_json(datasets, json_path)
    _write_markdown(datasets, md_path, project_name)

    return {"json": json_path, "markdown": md_path}


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------

def _write_json(datasets: List[ScenarioTestData], path: str) -> None:
    payload = [ds.model_dump() for ds in datasets]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

def _write_markdown(
    datasets: List[ScenarioTestData], path: str, project_name: str
) -> None:
    lines = [
        f"# Test Data — {project_name}",
        "",
        f"Total: **{len(datasets)} dataset(s)**",
        "",
        "---",
        "",
    ]

    for ds in datasets:
        lines += [
            f"## {ds.testdata_id}: {ds.scenario_id} — {ds.scenario_title}",
            "",
            f"**Actor:** {ds.actor}",
            "",
        ]

        # Positive
        lines += ["### Positive Dataset", ""]
        if ds.positive_dataset:
            lines += [
                "| Field | Type | Value |",
                "|---|---|---|",
            ]
            for f in ds.positive_dataset:
                lines.append(f"| {f.field_name} | {f.field_type} | {f.value} |")
        else:
            lines.append("_No input fields identified for this scenario._")
        lines.append("")

        # Negative
        lines += ["### Negative Variants", ""]
        for nv in ds.negative_variants:
            error_note = (
                f"  \n*Expected error: {nv.expected_error}*" if nv.expected_error else ""
            )
            lines += [
                f"#### {nv.variant_id} (`{nv.variant_type}`) — {nv.description}{error_note}",
                "",
                "| Field | Type | Value |",
                "|---|---|---|",
            ]
            for f in nv.fields:
                display_val = f.value if f.value != "" else '`""`'
                lines.append(f"| {f.field_name} | {f.field_type} | {display_val} |")
            lines.append("")

        lines += ["---", ""]

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
