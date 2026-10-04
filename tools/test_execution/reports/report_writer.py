"""Assembles the structured report dict from workflow state and agent outputs."""

import re
from datetime import datetime
from typing import Optional

_LOCATOR_KEY_RE = re.compile(r"\[locator_key=([^\]]+)\]")


def _failure_signature(error_text: str) -> str:
    """Collapse a raw Playwright error into a short, groupable signature.

    Prefers the `[locator_key=...]` tag ActionEngine.run() stamps onto every
    failure (see application_assets/_shared/runtime/ActionEngine.ts) — this is
    what actually ties unrelated-looking failures together (e.g. 13 different
    scenarios all failing because they were pointed at the same wrong
    locator). Falls back to the first line of the error message when no
    locator_key is present (page-level assertions like verifyUrl/verifyTitle
    don't carry one).
    """
    if not error_text:
        return "unknown error"
    match = _LOCATOR_KEY_RE.search(error_text)
    if match:
        return f"locator_key={match.group(1)}"
    first_line = error_text.strip().splitlines()[0] if error_text.strip() else ""
    return first_line[:120] or "unknown error"


def build_failures_log_text(report: dict) -> str:
    """Plain-text failure digest for a dedicated failures_<ts>.log file — the
    persistent, at-a-glance reference the JSON/HTML report's full detail
    doesn't give you: what failed, grouped by shared root cause, with the
    affected test ids and one example error per group."""
    ter = report.get("test_execution_report") or {}
    lines = [
        f"Project: {report.get('project', 'unknown')}   Run: {report.get('run_id', '')}",
        f"Generated: {report.get('generated_at', '')}",
        f"Result: {ter.get('passed', 0)} passed / {ter.get('failed', 0)} failed / {ter.get('total', 0)} total ({ter.get('pass_rate', 'N/A')})",
        "",
    ]
    failure_summary = ter.get("failure_summary") or []
    if not failure_summary:
        lines.append("No failures.")
        return "\n".join(lines)

    lines.append(f"{len(failure_summary)} distinct root cause(s) behind {ter.get('failed', 0)} failure(s):")
    lines.append("")
    for i, group in enumerate(failure_summary, 1):
        lines.append(f"[{i}] {group['count']}x — {group['signature']}")
        lines.append(f"    affected: {', '.join(group['test_case_ids'])}")
        if group.get("example_error"):
            example = group["example_error"].strip().splitlines()[0]
            lines.append(f"    example : {example}")
        lines.append("")
    return "\n".join(lines)


def build_failure_summary(test_results: list) -> list:
    """Group failed test_results by _failure_signature so N failures sharing
    one root cause (a bad locator, a brittle assertion) show up as one entry
    with a count and the list of affected test_case_ids, instead of N
    separately-scrolled raw stack traces that all say the same thing.

    Returns a list of {signature, count, test_case_ids, example_error} sorted
    by count descending — the biggest lever to fix first, first.
    """
    groups: dict = {}
    for r in test_results:
        if r.get("status") != "failed":
            continue
        errors = r.get("errors") or []
        signature = _failure_signature(errors[0] if errors else "")
        group = groups.setdefault(signature, {"signature": signature, "count": 0, "test_case_ids": [], "example_error": errors[0] if errors else ""})
        group["count"] += 1
        tc_id = r.get("test_case_id", "")
        if tc_id and tc_id not in group["test_case_ids"]:
            group["test_case_ids"].append(tc_id)

    return sorted(groups.values(), key=lambda g: g["count"], reverse=True)


def _extract_step_artifacts(step_name: str, output: Optional[dict], status: str) -> Optional[dict]:
    """Return artifact counts/paths for a completed step, or None."""
    if status == "skipped" or not output:
        return None
    if output.get("status") == "failed" or (
        "error" in output and "status" not in output
    ):
        return None

    if step_name == "discovery":
        arts: dict = {
            "scenarios_count":  output.get("scenarios_count", 0),
            "dom_intents_count": output.get("dom_intents_count", 0),
        }
        files = [f for f in [output.get("intents_path"), output.get("dom_intents_path")] if f]
        if files:
            arts["files"] = files
        return arts

    if step_name == "artifact_generator_intents":
        return {
            "intents_generated":  output.get("intents_generated", 0),
            "scenarios_processed": output.get("scenarios_processed", 0),
            "files": [v for v in (output.get("output") or {}).values() if v],
        }

    if step_name == "testdata":
        return {
            "datasets_generated":  output.get("datasets_generated", 0),
            "scenarios_processed": output.get("scenarios_processed", 0),
            "files": [v for v in (output.get("output") or {}).values() if v],
        }

    if step_name == "artifact_generator_testcases":
        return {
            "test_cases_generated": output.get("test_cases_generated", 0),
            "intents_enriched":     output.get("intents_enriched", 0),
            "files": [v for v in (output.get("output") or {}).values() if v],
        }

    if step_name == "locator":
        arts = {
            "intents_newly_grounded": output.get("intents_newly_grounded", 0),
            "intents_total":          output.get("intents_total", 0),
        }
        if output.get("locators_path"):
            arts["files"] = [output["locators_path"]]
        return arts

    if step_name == "script_generation":
        script_map = output.get("output") or {}
        return {
            "scripts_generated": output.get("scripts_generated", 0),
            "files":             list(script_map.values()),
        }

    if step_name in ("execution", "ui_execution"):
        # ExecutionAgent (legacy "execution" step) nests these under "summary";
        # UIExecutionAgent (current "ui_execution" step) returns them flat —
        # read whichever is present.
        s = output.get("summary") or output
        return {
            "scenarios_executed": s.get("scenarios_executed", 0),
            "passed":             s.get("passed", 0),
            "failed":             s.get("failed", 0),
        }

    if step_name == "healing":
        return {
            "specs_healed": output.get("specs_healed", 0),
            "tests_healed": output.get("tests_healed", 0),
            "not_healable_count": len(output.get("not_healable") or []),
            "rounds_run": len(output.get("rounds") or []),
        }

    return None


def build_report_dict(
    project_name: str,
    run_id: str,
    workflow: str,
    execution_trace: list,
    errors: list,
    outputs: dict,
    generated_at: datetime,
) -> dict:
    """
    Assemble the full structured report dict from workflow state.
    Always produces four top-level sections regardless of what ran.
    No LLM calls — pure data transformation.
    """
    # ── Section 1: Workflow Status ─────────────────────────────────────────
    steps_passed  = sum(1 for t in execution_trace if t.get("status") == "success")
    steps_failed  = sum(1 for t in execution_trace if t.get("status") == "failed")
    steps_skipped = sum(1 for t in execution_trace if t.get("status") == "skipped")
    overall_status    = "failed" if steps_failed else "success"
    total_duration_ms = sum(t.get("duration_ms", 0) for t in execution_trace)

    pipeline_steps = []
    for trace_entry in execution_trace:
        step        = trace_entry.get("step", "")
        step_status = trace_entry.get("status", "")
        artifacts   = _extract_step_artifacts(step, outputs.get(step), step_status)
        enriched    = dict(trace_entry)
        enriched["artifacts"] = artifacts
        pipeline_steps.append(enriched)

    # ── Section 2: Artifacts Generated ────────────────────────────────────
    disc_out = outputs.get("discovery") or {}
    ai_out   = outputs.get("artifact_generator_intents") or {}
    atc_out  = outputs.get("artifact_generator_testcases") or {}
    td_out   = outputs.get("testdata") or {}
    sg_out   = outputs.get("script_generation") or {}

    artifact_summary = {
        "business_scenarios": disc_out.get("scenarios_count", 0),
        "intents":            atc_out.get("intents_enriched", ai_out.get("intents_generated", 0)),
        "test_cases":         atc_out.get("test_cases_generated", 0),
        "test_data_sets":     td_out.get("datasets_generated", 0),
        "test_scripts":       sg_out.get("scripts_generated", 0),
    }
    artifact_per_step = [
        {"step": e.get("step", ""), "status": e.get("status", ""), "artifacts": e.get("artifacts")}
        for e in pipeline_steps
    ]

    # ── Section 3: Test Execution Report ──────────────────────────────────
    # ExecutionAgent (legacy "execution" step) and UIExecutionAgent (current
    # "ui_execution" step) both populate a flat "results" list — read
    # whichever step actually ran.
    exec_output  = outputs.get("execution") or outputs.get("ui_execution") or {}
    raw_results  = exec_output.get("results") or []
    test_results = []
    for r in raw_results:
        test_results.append({
            "test_case_id":         r.get("test_case_id", ""),
            "test_case_name":       r.get("test_title", r.get("test_case_name", "")),
            "business_scenario_id": r.get("business_scenario_id", ""),
            "status":               r.get("status", "unknown"),
            "flaky":                r.get("flaky", False),
            "errors":               r.get("errors") or [],
        })

    # ExecutionAgent nests these under "summary"; UIExecutionAgent returns them flat.
    exec_summary = exec_output.get("summary") or exec_output
    tc_passed    = exec_summary.get("passed", 0)
    tc_failed    = exec_summary.get("failed", 0)
    tc_total     = exec_summary.get("scenarios_executed", 0)
    pass_rate    = f"{round(tc_passed / tc_total * 100)}%" if tc_total else "N/A"

    # ── Section 3b: Healing Report (per-iteration + reconstructed final tally) ──
    # Deliberately does NOT use healing_out["tests_healed"] for the final tally:
    # that field counts apply_patch() *calls*, not verified-passing tests (a
    # patch can be applied and never re-verified, or re-verified and still
    # fail). remaining_failing_count (== HealingRunContext.remaining_total() at
    # the end of the run) only decreases when a test is actually observed
    # passing or explicitly marked not-healable — the correct source for
    # "how many of the original failures are still failing."
    healing_out = outputs.get("healing")
    healing_report = None
    if healing_out is not None:
        rounds = [
            {
                "round":           r.get("round", i + 1),
                "spec_files":      r.get("spec_files", []),
                "ran":             r.get("ran", False),
                "passed":          r.get("passed", 0),
                "failed":          r.get("failed", 0),
                "remaining_after": r.get("remaining_after"),
                "error":           r.get("error"),
            }
            for i, r in enumerate(healing_out.get("rounds") or [])
        ]

        still_failing = healing_out.get("remaining_failing_count")
        if still_failing is None:
            # Healing crashed before any run_tests() call ever executed (or
            # this healing output predates this field) — nothing was
            # verified fixed, so the pre-healing baseline is the only
            # honest final tally.
            still_failing = tc_failed

        resolved_count = max(tc_failed - still_failing, 0)
        final_passed = tc_passed + resolved_count
        final_failed = still_failing
        final_total  = final_passed + final_failed

        healing_report = {
            "status":         healing_out.get("status", "unknown"),
            "rounds":         rounds,
            "specs_healed":   healing_out.get("specs_healed", 0),
            "tests_healed":   healing_out.get("tests_healed", 0),
            "not_healable":   healing_out.get("not_healable") or [],
            "before_healing": {
                "passed": tc_passed,
                "failed": tc_failed,
                "total":  tc_total,
            },
            "final_result": {
                "passed":    final_passed,
                "failed":    final_failed,
                "total":     final_total,
                "pass_rate": f"{round(final_passed / final_total * 100)}%" if final_total else "N/A",
            },
        }

    # ── Section 4: Errors and Validation ──────────────────────────────────
    # Collect validation warnings from step outputs (orphaned intents, etc.)
    warnings = []
    for step_out in outputs.values():
        if isinstance(step_out, dict):
            for w in step_out.get("warnings", []):
                warnings.append(w)

    return {
        "run_id":       run_id,
        "project":      project_name,
        "generated_at": generated_at.isoformat(),

        "workflow_status": {
            "workflow":           workflow,
            "status":             overall_status,
            "total_duration_ms":  total_duration_ms,
            "steps_passed":       steps_passed,
            "steps_failed":       steps_failed,
            "steps_skipped":      steps_skipped,
            "steps":              pipeline_steps,
        },

        "artifacts_generated": {
            "summary":   artifact_summary,
            "per_step":  artifact_per_step,
        },

        "test_execution_report": {
            "executed":        bool(raw_results),
            "total":           tc_total,
            "passed":          tc_passed,
            "failed":          tc_failed,
            "pass_rate":       pass_rate,
            "results":         test_results,
            "failure_summary": build_failure_summary(test_results),
        },

        "healing_report": healing_report,

        "errors_and_validation": {
            "errors":   errors,
            "warnings": warnings,
        },
    }
