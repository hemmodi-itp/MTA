import json
import os
from datetime import datetime
from typing import List, Dict, Any


def write_ns_agents_report(
    project: str,
    run_id: str,
    workflow: str,
    started_at: datetime,
    ns_call_trace: List[Dict[str, Any]],
) -> str:
    """Write nsAgents.md to application_assets/projects/{project}/reports/ns/"""
    report_dir = os.path.join("application_assets", "projects", project, "test_execution", "reports", "ns")
    os.makedirs(report_dir, exist_ok=True)

    timestamp = started_at.strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(report_dir, f"{timestamp}_{run_id[:8]}_nsAgents.md")

    lines = [
        "# NS Agent Call Report",
        "",
        f"- **Run ID**: `{run_id}`",
        f"- **Project**: {project}",
        f"- **Workflow**: {workflow}",
        f"- **Date**: {started_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"- **Agents called**: {len(ns_call_trace)}",
        "",
        "---",
        "",
    ]

    for i, call in enumerate(ns_call_trace, 1):
        status_badge = "SUCCESS" if call["status"] not in ("failed", "error") else "FAILED"
        lines += [
            f"## {i}. `{call['step']}`",
            "",
            f"| | |",
            f"|---|---|",
            f"| **Endpoint** | `{call['method']} {call['url']}` |",
            f"| **Status** | {status_badge} — `{call['status']}` |",
            "",
        ]

        # Input
        lines.append("**Input sent:**")
        lines.append("```json")
        lines.append(json.dumps(call.get("input") or {}, indent=2, default=str))
        lines.append("```")
        lines.append("")

        # Output
        if call.get("error"):
            lines.append(f"**Error:** `{call['error']}`")
        else:
            lines.append("**Response received:**")
            lines.append("```json")
            lines.append(json.dumps(call.get("response") or {}, indent=2, default=str))
            lines.append("```")
        lines.append("")
        lines.append("---")
        lines.append("")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return report_path
