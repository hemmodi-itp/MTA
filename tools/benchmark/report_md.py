"""report_md.py — Markdown summary of a scored benchmark run."""

from typing import Any, Dict, Optional


def _pct(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def render_markdown(metrics: Dict[str, Any], meta: Dict[str, Any]) -> str:
    det = metrics["seeded_bug_detection"]
    cov = metrics["requirement_coverage"]
    llm = metrics["llm"]
    heal = metrics["heal_precision"]
    rt = metrics["runtime_s"]
    cost = "unpriced" if llm["cost_usd"] is None else f"${llm['cost_usd']:.4f}"
    lines = [
        f"# Benchmark — {metrics.get('app')} — {meta.get('date', '')}",
        "",
        f"MTA commit `{meta.get('commit', '?')}` · label `{meta.get('label', '')}` · "
        f"{metrics['tests_executed']} tests executed of {metrics['tests_total']} generated",
        "",
        "| KPI | Value |",
        "|---|---|",
        f"| Requirement (AC) coverage | {_pct(cov['pct'])} ({len(cov['covered'])}/{cov['total_acs']}) |",
        f"| AC coverage, direct links only | {_pct(cov.get('direct_pct'))} "
        f"({len(cov.get('covered_direct') or [])}/{cov['total_acs']}) |",
        f"| **Seeded-bug detection rate** | **{_pct(det['rate'])}** ({det['caught']}/{det['evaluated']} evaluated, {det['enabled']} seeded) |",
        f"| False-failure rate (bug-free build) | {_pct(metrics['false_failure']['rate'])} |",
        f"| Flaky rate ({metrics['flaky']['clean_runs']} bug-free runs) | {_pct(metrics['flaky']['rate'])} |",
        f"| Heal precision | {_pct(heal['precision'])} ({heal['applied']} applied, {heal['wrong']} wrong)"
        f"{'' if heal['measured'] else ' — not measured'} |",
        f"| Generation runtime | {rt['generation'] if rt['generation'] is not None else 'n/a'} s |",
        f"| Total runtime | {rt['total'] if rt['total'] is not None else 'n/a'} s |",
        f"| LLM calls / cache hits | {llm['calls']} / {llm['cache_hits']} |",
        f"| LLM tokens in / out | {llm['input_tokens']:,} / {llm['output_tokens']:,} |",
        f"| LLM cost | {cost} |",
    ]
    if metrics.get("ac_extraction_recall") is not None:
        lines.append(f"| AC extraction recall (vs acs.yaml) | {_pct(metrics['ac_extraction_recall'])} |")
    lines += [
        "",
    ]
    if cov.get("note"):
        lines += [f"> AC coverage note: {cov['note']}", ""]
    if llm["unpriced_models"]:
        lines += [f"> Cost not computed — no price in benchmarks/pricing.yaml for: {', '.join(llm['unpriced_models'])}", ""]
    lines += ["## Detection by category", "", "| Category | Caught / enabled |", "|---|---|"]
    for cat, c in sorted(det["by_category"].items()):
        lines.append(f"| {cat} | {c['caught']} / {c['enabled']} |")
    lines += ["", "## Per bug", "", "| Bug | Category | Severity | AC | Caught | By | How detectable |",
              "|---|---|---|---|---|---|---|"]
    for b in det["bugs"]:
        state = "not run" if not b["evaluated"] else ("yes" if b["caught"] else "no")
        by = ", ".join(t.split("::")[-1][:40] for t in b["caught_by"][:2]) + (" …" if len(b["caught_by"]) > 2 else "")
        lines.append(f"| {b['id']} | {b['category']} | {b['severity']} | {b['affected_ac']} | {state} | {by} | {b['how_detectable']} |")
    if metrics["false_failure"]["failing_tests"]:
        lines += ["", "## Tests failing on the bug-free build", ""]
        lines += [f"- `{t}`" for t in metrics["false_failure"]["failing_tests"]]
    if cov["uncovered"]:
        lines += ["", "## ACs with no linked executed test", "", ", ".join(cov["uncovered"])]
    for note in meta.get("notes") or []:
        lines += ["", f"> {note}"]
    return "\n".join(lines) + "\n"
