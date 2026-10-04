"""
final.py — Final Evaluation Report.

    report   = build_report(ctx)           # ctx = the pipeline request after every step
    markdown = render_markdown(report)
    html     = render_html(report)         # standalone, printable (browser "Save as PDF")

One deterministic report per run, assembled only from what earlier engines recorded: no LLM, so nothing in it
can be more confident than the evidence. Sections:

  decision        outcome (Compliant / Compliant with warnings / Partially compliant / Not compliant /
                  Not assessable) from the compliance score and gates, with the reason
  summary         executive summary sentences built from the numbers
  application     what was evaluated: repo, commit, live app, its type and how it was tested
  requirements    the compliance matrix: requirement → criterion → verdict, strength, basis, discrepancy
  runtime         runtime verdicts: failed tests with reasons and screenshots, inconclusive, not run (grouped by reason)
  discrepancies   code vs runtime disagreements
  findings        critical / high repository-review findings
  gates, recommendations
  coverage        evidence mix (runtime vs code vs none) and criteria without evidence
  limitations     what this report could not establish, stated explicitly
  method          the evidence ladder and pipeline that produced it

Decision rules: no scorable requirements → Not assessable; a blocking gate → Not compliant; otherwise by
compliance score: ≥ 75 Compliant (with warnings if any warning gate), 50–75 Partially compliant, < 50 Not compliant.
"""

import html
import time
from typing import Any, Dict, List, Optional

REPORT_VERSION = "final-report-1.0"
_OUTCOME_RANK = ["Not assessable", "Not compliant", "Partially compliant", "Compliant with warnings", "Compliant"]
_MODE = {"brd_and_live": "BRD in the repository + live app", "live_only": "Live app only (BRD generated)",
         "brd_only": "BRD only (not deployed)"}
_VERDICT_LABEL = {
    "verified_pass": "Verified at runtime", "verified_fail": "Failed at runtime", "implemented_static": "Implemented (code)",
    "partial": "Partial", "contested": "Contested", "not_implemented": "Not implemented",
    "insufficient_evidence": "Insufficient evidence", "not_technically_verifiable": "Not technically verifiable",
    "verified": "Verified", "implemented": "Implemented", "failed": "Failed",
}


def build_report(ctx: Dict[str, Any]) -> Dict[str, Any]:
    sc = ctx.get("score") or {}
    pf = ctx.get("pass_fail") or {}
    bc = ctx.get("brd_compliance") or {}
    cls = ctx.get("app_classification") or {}
    prof = ctx.get("runtime_profile") or {}
    gates = sc.get("gates") or []
    live_url = ctx.get("live_url") or prof.get("live_url")
    deployed = ctx.get("mode") != "brd_only" and bool(live_url or prof)

    decision = _decision(sc, gates, deployed)
    runtime = _runtime(pf, ctx.get("run_id"))
    limitations = _limitations(ctx, sc, pf, bc, prof, deployed)
    report = {
        "report_version": REPORT_VERSION,
        "generated_at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "meta": {
            "run_id": ctx.get("run_id"), "repository": ctx.get("repo_full_name") or ctx.get("github_url"),
            "github_url": ctx.get("github_url"), "branch": ctx.get("branch"), "commit": ctx.get("commit_sha"),
            "mode": _MODE.get(ctx.get("mode"), ctx.get("mode")), "live_url": live_url if deployed else None,
            "brd_source": ctx.get("brd_source"), "brd_path": ctx.get("brd_path"),
            "agent_name": (ctx.get("agent_profile") or {}).get("agent_name"),
            "purpose": (ctx.get("agent_profile") or {}).get("purpose"),
            "scoring_version": sc.get("scoring_version"),
        },
        "decision": decision,
        "application": {
            "type": cls.get("app_type") or prof.get("app_type"), "components": cls.get("components") or [],
            "confidence": cls.get("confidence"), "basis": cls.get("basis"),
            "testing_strategy": [s["strategy"] for s in cls.get("testing_strategy") or []],
            "pages_inspected": prof.get("pages_inspected"), "authentication": prof.get("authentication"),
            "logged_in": bool((prof.get("login") or {}).get("succeeded")), "needs_credentials": bool(prof.get("needs_credentials")),
            "forms": prof.get("forms"), "downloads": prof.get("downloads"), "chat_interface": prof.get("chat_interface"),
        } if (cls or prof) else None,
        "requirements": _requirements(ctx.get("traced_requirements") or ctx.get("requirements") or [], bc),
        "runtime": runtime,
        "discrepancies": bc.get("discrepancies") or [],
        "findings": [{k: f.get(k) for k in ("severity", "dimension", "title", "file", "start_line", "fix")}
                     for f in sorted(ctx.get("findings") or [], key=lambda f: ["critical", "high"].index(f["severity"])
                                     if f.get("severity") in ("critical", "high") else 9)
                     if f.get("severity") in ("critical", "high")][:15],
        "gates": gates,
        "recommendations": [{k: r.get(k) for k in ("severity", "category", "summary")} for r in (ctx.get("recommendations") or [])[:15]],
        "coverage": {"evidence_mix": bc.get("evidence_mix"), "counts": bc.get("counts"),
                     "without_evidence": [c["code"] for r in bc.get("matrix") or [] if r.get("scored") for c in r["criteria"]
                                          if c.get("strength") in (None, "E1") and c.get("resolved_verdict") != "not_technically_verifiable"]},
        "limitations": limitations,
        "method": [
            "Requirements and atomic acceptance criteria are extracted from the BRD (quotes verified against the document) or, "
            "without a BRD, inferred from the live app and marked as inferred.",
            "Each criterion is traced to code (hybrid retrieval, two independent verifier samples, citations checked against the "
            "repository) and, when the app is deployed, tested at runtime in a real browser.",
            "Evidence ladder: E5 runtime + deterministic check · E4 runtime, judged with verified quotes · E3 code wired to an entry "
            "point · E2 code only · E1 unverified (no credit). Runtime failure outranks everything; insufficient evidence earns 0.",
            "Compliance = priority-weighted mean of requirement scores (high 3, medium 2, low 1); the interval is a 90% bootstrap.",
        ],
    }
    report["summary"] = _summary(report, sc, pf, bc, deployed)
    return report


# ── sections ────────────────────────────────────────────────────────────────

def _decision(sc: Dict, gates: List[Dict], deployed: bool = False) -> Dict[str, Any]:
    comp = sc.get("compliance")
    blocks = [g for g in gates if g.get("level") == "block"]
    warns = [g for g in gates if g.get("level") == "warn"]
    if comp is None:
        outcome, reason = "Not assessable", "No scorable requirements (no BRD, and none could be inferred from a live app)."
    elif blocks:
        outcome, reason = "Not compliant", "Blocking gate: " + "; ".join(g["reason"] for g in blocks[:3])
    elif comp >= 75:
        outcome = "Compliant with warnings" if warns else "Compliant"
        reason = (f"Compliance {comp:.0f} ≥ 75" + (f"; {len(warns)} warning(s): " + "; ".join(g["gate"].replace("_", " ") for g in warns[:4])
                                                 if warns else "; no warnings"))
    elif comp >= 50:
        outcome, reason = "Partially compliant", f"Compliance {comp:.0f} is between 50 and 75"
    else:
        outcome, reason = "Not compliant", f"Compliance {comp:.0f} < 50"
    if comp is not None and deployed and sc.get("evidence_basis") == "code_only" and outcome.startswith("Compliant"):
        # the app is deployed but nothing was proven on it: a code reading alone cannot certify compliance
        outcome = "Not verified at runtime"
        reason = (f"Compliance {comp:.0f} rests on code evidence only; no acceptance criterion was proven on the live app "
                  "(see Limitations for why). Fix the cause and re-run to verify behaviour.")
    return {"outcome": outcome, "evidence_basis": sc.get("evidence_basis"), "reason": reason, "compliance": comp, "ci_low": sc.get("ci_low"), "ci_high": sc.get("ci_high"),
            "score_kind": sc.get("score_kind"), "risk_level": sc.get("risk_level"),
            "verification_depth": sc.get("verification_depth"), "blocking_gates": len(blocks), "warning_gates": len(warns)}


def _requirements(reqs: List[Dict], bc: Dict) -> List[Dict[str, Any]]:
    rows = {m["code"]: m for m in bc.get("matrix") or []}
    out = []
    for r in reqs:
        m = rows.get(r["code"]) or {}
        crit = m.get("criteria") or [{"code": c["code"], "statement": c.get("statement")} for c in r.get("criteria") or []]
        out.append({"code": r["code"], "title": r.get("title"), "priority": r.get("priority"), "origin": r.get("origin", "brd"),
                    "scored": m.get("scored", r.get("origin", "brd") == "brd"), "verdict": r.get("verdict"), "score": r.get("score"),
                    "criteria": [{"code": c["code"], "statement": c.get("statement"), "verdict": c.get("resolved_verdict"),
                                  "strength": c.get("strength"), "basis": c.get("basis"), "discrepancy": c.get("discrepancy"),
                                  "tests": [{k: t.get(k) for k in ("test_code", "verdict", "score", "strength")}
                                            for t in ((c.get("runtime") or {}).get("tests") or [])]} for c in crit]})
    return out


def _runtime(pf: Dict, run_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not pf:
        return None
    tests = [t for t in pf.get("tests") or [] if t.get("scored")]

    def item(t):
        shot = (t.get("artifacts") or {}).get("screenshot")
        return {"test_code": t.get("test_code"), "title": t.get("title"), "criterion_code": t.get("criterion_code"),
                "score": t.get("score"), "strength": t.get("strength"), "reasons": t.get("reasons") or [],
                "screenshot": f"/api/runs/{run_id}/execution-files/{shot}" if shot and run_id else None,
                "documents": [d.get("name") for d in (t.get("artifacts") or {}).get("documents") or []]}

    not_run: Dict[str, int] = {}
    for t in tests:
        if t["verdict"] == "not_executed":
            key = ((t.get("reasons") or ["not executed"])[0])[:160]
            not_run[key] = not_run.get(key, 0) + 1
    return {"counts": pf.get("counts"), "pass_rate": pf.get("pass_rate"),
            "failed": [item(t) for t in tests if t["verdict"] == "failed"],
            "inconclusive": [item(t) for t in tests if t["verdict"] == "inconclusive"],
            "passed": [{"test_code": t.get("test_code"), "title": t.get("title"), "criterion_code": t.get("criterion_code"),
                        "score": t.get("score"), "strength": t.get("strength")} for t in tests if t["verdict"] == "passed"],
            "not_run": [{"reason": k, "count": v} for k, v in sorted(not_run.items(), key=lambda kv: -kv[1])]}


def _limitations(ctx, sc, pf, bc, prof, deployed) -> List[str]:
    out = []
    if not deployed:
        out.append("The app is not deployed: every criterion was judged from the code only (at most E3); nothing was run.")
    elif prof.get("needs_credentials") and (prof.get("login") or {}).get("attempted"):
        out.append(f"MTA tried to log in with the project's test account but it failed "
                   f"({(prof.get('login') or {}).get('error') or 'login failed'}), so no runtime test ran. Check the account on "
                   "the live app's login page and re-run.")
    elif prof.get("needs_credentials"):
        out.append("The live app is behind a login and no test account was configured, so no runtime test ran; add a test "
                   "account to the project and re-run to verify behaviour.")
    elif not prof:
        out.append("The live app could not be inspected (runtime discovery produced no profile); results rest on code evidence.")
    if prof.get("crawl_stopped_by"):
        out.append(f"Runtime discovery stopped after {prof['crawl_stopped_by']} ({prof.get('pages_inspected', 0)} page(s) "
                   "inspected); features on pages it did not reach could not be tested.")
    for f in ctx.get("step_failures") or []:
        out.append(f"Step '{f['label']}' failed ({str(f['error'])[:200]}); the evaluation continued without it.")
    static_only = ctx.get("static_only_criteria") or []
    if static_only and deployed:
        reasons: Dict[str, int] = {}
        for c in static_only:
            key = c.get("reason") or "judged from the code"
            reasons[key] = reasons.get(key, 0) + 1
        out.append(f"{len(static_only)} criteria were not tested on the live app: "
                   + "; ".join(f"{n}: {r}" for r, n in sorted(reasons.items(), key=lambda kv: -kv[1])[:4]) + ".")
    for lim in ctx.get("limitations") or []:  # from BRD extraction (caps, ungrounded criteria, ...)
        out.append(str(lim))
    cov = ctx.get("repo_coverage") or {}
    if cov.get("truncated") or cov.get("skipped_total"):
        out.append(f"Repository coverage: {cov.get('fetched', '?')} of {cov.get('in_tree', '?')} files were read"
                   + (" (GitHub truncated the file list)" if cov.get("truncated") else "")
                   + "; code evidence for the rest could not be checked.")
    if sc.get("llm_unavailable"):
        out.append(f"{len(sc['llm_unavailable'])} criteria could not be checked because the language model was unavailable; "
                   "they are excluded from the score.")
    c = (pf or {}).get("counts") or {}
    if c.get("inconclusive"):
        out.append(f"{c['inconclusive']} runtime test(s) were inconclusive (MTA could not drive the UI or judge the output); "
                   "they were not counted for or against the app.")
    if c.get("not_executed") and not prof.get("needs_credentials"):
        why: Dict[str, int] = {}
        for t in (pf or {}).get("tests") or []:
            if t.get("scored") and t.get("verdict") == "not_executed":
                key = ((t.get("reasons") or ["not executed"])[0])[:140]
                why[key] = why.get(key, 0) + 1
        out.append(f"{c['not_executed']} runtime test(s) were not executed: "
                   + "; ".join(f"{n}: {r}" for r, n in sorted(why.items(), key=lambda kv: -kv[1])[:3]) + ".")
    mix = (bc or {}).get("evidence_mix") or {}
    if deployed and mix and mix.get("runtime_share", 0) < 0.5 and not prof.get("needs_credentials"):
        out.append(f"Only {mix['runtime_share']:.0%} of criteria were proven on the live app; the rest rest on code reading.")
    if sc.get("score_kind") == "inferred_conformance":
        out.append("No BRD was supplied: requirements were inferred from the live app and the score measures conformance "
                   "to that inferred intent, not to an approved BRD.")
    unscored = len(sc.get("excluded_requirements") or [])
    if unscored:
        out.append(f"{unscored} requirement(s) were descriptive (derived from the code) and are not scored.")
    if (bc or {}).get("counts", {}).get("criteria_without_evidence"):
        out.append(f"{bc['counts']['criteria_without_evidence']} criteria have no verifiable evidence and earn 0 credit.")
    if sc.get("ci_low") is not None and sc.get("ci_high") is not None and sc["ci_high"] - sc["ci_low"] > 25:
        out.append(f"The score's 90% interval is wide ({sc['ci_low']:.0f}–{sc['ci_high']:.0f}); treat the point estimate with care.")
    return out


def _summary(rep: Dict, sc: Dict, pf: Dict, bc: Dict, deployed: bool) -> List[str]:
    d, meta = rep["decision"], rep["meta"]
    s = []
    what = meta.get("agent_name") or meta.get("repository") or "The application"
    if d["compliance"] is None:
        s.append(f"{what} could not be scored for BRD compliance: {d['reason']}")
    else:
        kind = "BRD compliance" if d["score_kind"] == "brd_compliance" else "Conformance to inferred intent"
        s.append(f"{what}: {d['outcome']}. {kind} {d['compliance']:.0f}/100"
                 + (f" (90% interval {d['ci_low']:.0f}–{d['ci_high']:.0f})" if d.get("ci_low") is not None else "")
                 + f", risk {d.get('risk_level') or 'n/a'}.")
    reqs = [r for r in rep["requirements"] if r.get("scored")]
    if reqs:
        counts: Dict[str, int] = {}
        for r in reqs:
            counts[r.get("verdict") or "pending"] = counts.get(r.get("verdict") or "pending", 0) + 1
        s.append(f"{len(reqs)} scored requirements: " + ", ".join(f"{n} {_VERDICT_LABEL.get(k, k).lower()}"
                                                                for k, n in sorted(counts.items(), key=lambda kv: -kv[1])) + ".")
    app = rep.get("application")
    if app and app.get("type"):
        s.append(f"Evaluated as a {app['type']}" + (f" ({' + '.join(app['components'])})" if app.get("components") else "")
                 + (", logged in with the test account" if app.get("logged_in") else "") + ".")
    c = (pf or {}).get("counts")
    if c and c.get("tests"):
        s.append(f"Runtime: {c['passed']} of {c['tests']} BRD tests passed, {c['failed']} failed, {c['inconclusive']} inconclusive, "
                 f"{c['not_executed']} not run" + (f" (pass rate {pf['pass_rate']}%)." if pf.get("pass_rate") is not None else "."))
    elif deployed:
        s.append("No runtime test could be run against the live app.")
    mix = (bc or {}).get("evidence_mix")
    if mix:
        s.append(f"{mix['runtime_share']:.0%} of criteria are proven on the live app; "
                 f"{mix['credit_by_basis']['code']:.0%} of the earned credit comes from code evidence.")
    broken = [x for x in rep["discrepancies"] if x["kind"] == "broken_at_runtime"]
    if broken:
        s.append(f"{len(broken)} criteria are implemented in the code but fail when the app runs: "
                 + ", ".join(x["criterion_code"] for x in broken[:6]) + ".")
    crit = [f for f in rep["findings"] if f["severity"] == "critical"]
    if crit:
        s.append(f"{len(crit)} critical review finding(s), e.g. {crit[0]['title']}.")
    return s


# ── renderers ───────────────────────────────────────────────────────────────

def _pct(x: Optional[float]) -> str:
    return "—" if x is None else f"{x * 100:.0f}%"


def render_markdown(rep: Dict[str, Any]) -> str:
    m, d = rep["meta"], rep["decision"]
    L = [f"# Final Evaluation Report — {m.get('agent_name') or m.get('repository')}", "",
         f"**Outcome: {d['outcome']}** — {d['reason']}", ""]
    if d["compliance"] is not None:
        L.append(f"Compliance **{d['compliance']:.0f}/100**" + (f" (90% interval {d['ci_low']:.0f}–{d['ci_high']:.0f})" if d.get("ci_low") is not None else "")
                 + f" · risk {d.get('risk_level')} · verification depth {_pct(d.get('verification_depth'))}")
        L.append("")
    L += ["## Summary", ""] + [f"- {x}" for x in rep["summary"]] + [""]
    L += ["## What was evaluated", "", "| | |", "|---|---|",
          f"| Repository | {m.get('repository')}{' @ ' + m['branch'] if m.get('branch') else ''}{' · ' + m['commit'][:7] if m.get('commit') else ''} |",
          f"| Mode | {m.get('mode')} |", f"| Live app | {m.get('live_url') or '—'} |",
          f"| BRD | {m.get('brd_path') or m.get('brd_source') or '—'} |"]
    app = rep.get("application")
    if app:
        L.append(f"| App type | {app.get('type')}{' (' + ' + '.join(app['components']) + ')' if app.get('components') else ''}"
                 f"{' · from ' + app['basis'] if app.get('basis') else ''} |")
    L += [f"| Scoring | {m.get('scoring_version')} · report {rep['report_version']} · {rep['generated_at']} |", ""]

    L += ["## Requirements", "", "| Requirement | Priority | Verdict | Score |", "|---|---|---|---|"]
    for r in rep["requirements"]:
        L.append(f"| {r['code']} {r['title']}{'' if r['scored'] else ' *(not scored)*'} | {r.get('priority')} | "
                 f"{_VERDICT_LABEL.get(r.get('verdict'), r.get('verdict') or '—')} | {_pct(r.get('score'))} |")
    L.append("")
    for r in rep["requirements"]:
        if not r["criteria"]:
            continue
        L.append(f"**{r['code']} {r['title']}**")
        for c in r["criteria"]:
            tests = ", ".join(f"{t['test_code']} {t['verdict']}" for t in c.get("tests") or [])
            L.append(f"- {c['code']} — {_VERDICT_LABEL.get(c.get('verdict'), c.get('verdict') or 'pending')}"
                     f"{' · ' + c['strength'] if c.get('strength') else ''}{' · ' + c['basis'] if c.get('basis') else ''}"
                     f"{' · ⚠ ' + c['discrepancy'].replace('_', ' ') if c.get('discrepancy') else ''}: {c.get('statement') or ''}"
                     + (f" (tests: {tests})" if tests else ""))
        L.append("")

    rt = rep.get("runtime")
    if rt:
        c = rt["counts"]
        L += ["## Runtime results", "", f"{c['passed']} passed · {c['failed']} failed · {c['inconclusive']} inconclusive · "
                                        f"{c['not_executed']} not run" + (f" · pass rate {rt['pass_rate']}%" if rt.get("pass_rate") is not None else ""), ""]
        for t in rt["failed"]:
            L.append(f"- **{t['test_code']} failed** ({t['criterion_code']}): {t['title']} — {'; '.join(t['reasons'])[:400]}"
                     + (f" [screenshot]({t['screenshot']})" if t.get("screenshot") else ""))
        for t in rt["inconclusive"]:
            L.append(f"- {t['test_code']} inconclusive ({t['criterion_code']}): {'; '.join(t['reasons'])[:300]}")
        for n in rt["not_run"]:
            L.append(f"- {n['count']} not run: {n['reason']}")
        L.append("")
    if rep["discrepancies"]:
        L += ["## Code vs runtime", ""] + [f"- **{x['kind'].replace('_', ' ')}** {x['criterion_code']} ({x['requirement_code']}): {x['detail']}"
                                             for x in rep["discrepancies"]] + [""]
    if rep["findings"]:
        L += ["## Critical and high findings", ""] + [f"- **{f['severity']}** {f['title']}" + (f" ({f['file']}:{f['start_line']})" if f.get("file") else "")
                                                        + (f" — fix: {f['fix']}" if f.get("fix") else "") for f in rep["findings"]] + [""]
    L += ["## Gates", ""] + [f"- **{g['level']}** {g['gate'].replace('_', ' ')}: {g['reason']}" for g in rep["gates"]] + [""]
    if rep["recommendations"]:
        L += ["## Recommendations", ""] + [f"{i}. **{r['severity']}** {r['summary']}" for i, r in enumerate(rep["recommendations"], 1)] + [""]
    mix = (rep["coverage"] or {}).get("evidence_mix")
    if mix:
        b = mix["by_strength"]
        L += ["## Evidence coverage", "", f"E5 {b['E5']} · E4 {b['E4']} · E3 {b['E3']} · E2 {b['E2']} · E1/none {b['E1'] + b['none']} "
                                          f"— {mix['runtime_share']:.0%} of criteria proven at runtime.", ""]
    if rep["limitations"]:
        L += ["## Limitations", ""] + [f"- {x}" for x in rep["limitations"]] + [""]
    L += ["## Method", ""] + [f"- {x}" for x in rep["method"]] + [""]
    return "\n".join(L)


_CSS = """
:root{--fg:#1d2433;--muted:#5b6475;--line:#e3e6ec;--bg:#fff;--card:#f7f8fa;--ok:#137a4b;--warn:#9a6700;--bad:#b42318;--accent:#2f5bd3}
@media (prefers-color-scheme: dark){:root{--fg:#e7eaf0;--muted:#9aa3b2;--line:#2b3140;--bg:#12151c;--card:#1a1f29;--ok:#4fc38a;--warn:#e3b341;--bad:#f97066;--accent:#7aa2ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:980px;margin:0 auto;padding:28px 20px 60px}h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 10px;
padding-bottom:6px;border-bottom:1px solid var(--line)}.muted{color:var(--muted)}.hero{display:flex;flex-wrap:wrap;gap:16px;align-items:center;
margin:18px 0;padding:16px;border:1px solid var(--line);border-radius:10px;background:var(--card)}.score{font-size:40px;font-weight:700;line-height:1}
.pill{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:1px 9px;font-size:12px;white-space:nowrap}
.ok{color:var(--ok);border-color:currentColor}.warn{color:var(--warn);border-color:currentColor}.bad{color:var(--bad);border-color:currentColor}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600}ul{padding-left:18px}li{margin:3px 0}a{color:var(--accent)}code{font-size:12px}
.crit td{font-size:12px;color:var(--muted)}.crit td:first-child{padding-left:22px}@media print{main{max-width:none;padding:0}a{color:inherit}
.hero{break-inside:avoid}h2{break-after:avoid}}
"""


def _cls(outcome_or_verdict: str) -> str:
    v = outcome_or_verdict or ""
    if v in ("Compliant", "verified_pass", "verified", "implemented", "implemented_static", "passed", "pass"):
        return "ok"
    if v in ("Not compliant", "verified_fail", "failed", "not_implemented", "block"):
        return "bad"
    if v in ("Not assessable", "insufficient_evidence", "not_technically_verifiable", None, ""):
        return ""
    return "warn"


def render_html(rep: Dict[str, Any]) -> str:
    e = html.escape
    m, d = rep["meta"], rep["decision"]
    title = f"Evaluation report — {m.get('agent_name') or m.get('repository')}"
    H = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>{e(title)}</title><style>{_CSS}</style></head><body><main>",
         f"<h1>{e(title)}</h1><p class='muted'>{e(m.get('repository') or '')}"
         f"{' · ' + e(m['commit'][:7]) if m.get('commit') else ''} · {e(m.get('mode') or '')} · generated {e(rep['generated_at'])}</p>",
         "<div class='hero'>",
         f"<div class='score'>{'—' if d['compliance'] is None else format(d['compliance'], '.0f')}</div>",
         f"<div><span class='pill {_cls(d['outcome'])}'>{e(d['outcome'])}</span><div class='muted' style='margin-top:6px'>{e(d['reason'])}</div>"
         f"<div class='muted'>"
         + (f"90% interval {d['ci_low']:.0f}–{d['ci_high']:.0f} · " if d.get("ci_low") is not None else "")
         + f"risk {e(str(d.get('risk_level') or '—'))} · verification depth {_pct(d.get('verification_depth'))}</div></div></div>",
         "<h2>Summary</h2><ul>" + "".join(f"<li>{e(x)}</li>" for x in rep["summary"]) + "</ul>"]

    rows = [("Repository", f"<a href='{e(m['github_url'])}'>{e(m.get('repository') or '')}</a>" if m.get("github_url") else e(m.get("repository") or "")),
            ("Branch / commit", e(" · ".join(x for x in (m.get("branch"), (m.get("commit") or "")[:7]) if x)) or "—"),
            ("Mode", e(m.get("mode") or "")), ("Live app", e(m.get("live_url") or "—")),
            ("BRD", e(m.get("brd_path") or m.get("brd_source") or "—"))]
    app = rep.get("application")
    if app:
        rows.append(("Application type", e(f"{app.get('type')}" + (f" ({' + '.join(app['components'])})" if app.get("components") else "")
                                           + (f" · from {app['basis']}" if app.get("basis") else "")
                                           + (" · logged in with the test account" if app.get("logged_in") else ""))))
        if app.get("testing_strategy"):
            rows.append(("Tested by", e("; ".join(app["testing_strategy"]))))
    rows.append(("Scoring", e(f"{m.get('scoring_version')} · {rep['report_version']}")))
    H.append("<h2>What was evaluated</h2><table>" + "".join(f"<tr><th style='width:180px'>{k}</th><td>{v}</td></tr>" for k, v in rows) + "</table>")

    H.append("<h2>Requirements</h2><table><tr><th>Requirement</th><th>Priority</th><th>Verdict</th><th>Score</th></tr>")
    for r in rep["requirements"]:
        H.append(f"<tr><td><code>{e(r['code'])}</code> {e(r.get('title') or '')}{'' if r['scored'] else ' <span class=muted>(not scored)</span>'}</td>"
                 f"<td>{e(r.get('priority') or '')}</td><td><span class='pill {_cls(r.get('verdict'))}'>{e(_VERDICT_LABEL.get(r.get('verdict'), r.get('verdict') or '—'))}</span></td>"
                 f"<td>{_pct(r.get('score'))}</td></tr>")
        for c in r["criteria"]:
            tests = ", ".join(f"{t['test_code']} {t['verdict']}" for t in c.get("tests") or [])
            H.append(f"<tr class='crit'><td><code>{e(c['code'])}</code> {e(c.get('statement') or '')}"
                     + (f"<br>tests: {e(tests)}" if tests else "") + "</td>"
                     f"<td>{'evidence: ' + e(c['basis']) if c.get('basis') else ''}</td><td><span class='pill {_cls(c.get('verdict'))}'>{e(_VERDICT_LABEL.get(c.get('verdict'), c.get('verdict') or 'pending'))}</span>"
                     + (f" <span class='pill warn'>{e(c['discrepancy'].replace('_', ' '))}</span>" if c.get("discrepancy") else "")
                     + f"</td><td>{'strength ' + e(c['strength']) if c.get('strength') else ''}</td></tr>")
    H.append("</table>")

    rt = rep.get("runtime")
    if rt:
        c = rt["counts"]
        H.append(f"<h2>Runtime results</h2><p>{c['passed']} passed · {c['failed']} failed · {c['inconclusive']} inconclusive · {c['not_executed']} not run"
                 + (f" · pass rate {rt['pass_rate']}%" if rt.get("pass_rate") is not None else "") + "</p><ul>")
        for t in rt["failed"]:
            H.append(f"<li><span class='pill bad'>failed</span> <code>{e(t['test_code'] or '')}</code> ({e(t.get('criterion_code') or '')}) "
                     f"{e(t.get('title') or '')} — {e('; '.join(t['reasons'])[:500])}"
                     + (f" · <a href='{e(t['screenshot'])}'>screenshot</a>" if t.get("screenshot") else "") + "</li>")
        for t in rt["inconclusive"]:
            H.append(f"<li><span class='pill warn'>inconclusive</span> <code>{e(t['test_code'] or '')}</code> {e('; '.join(t['reasons'])[:300])}</li>")
        for n in rt["not_run"]:
            H.append(f"<li><span class='pill'>not run ×{n['count']}</span> {e(n['reason'])}</li>")
        for t in rt["passed"]:
            H.append(f"<li><span class='pill ok'>passed</span> <code>{e(t['test_code'] or '')}</code> ({e(t.get('criterion_code') or '')}) "
                     f"{e(t.get('title') or '')} · {t.get('score')} · {e(t.get('strength') or '')}</li>")
        H.append("</ul>")
    if rep["discrepancies"]:
        H.append("<h2>Code vs runtime</h2><ul>" + "".join(
            f"<li><span class='pill {'bad' if x['severity'] == 'high' else 'warn' if x['severity'] == 'warning' else ''}'>{e(x['kind'].replace('_', ' '))}</span> "
            f"<code>{e(x['criterion_code'])}</code> {e(x['requirement_code'])} — {e(x['detail'])}</li>" for x in rep["discrepancies"]) + "</ul>")
    if rep["findings"]:
        H.append("<h2>Critical and high findings</h2><ul>" + "".join(
            f"<li><span class='pill {'bad' if f['severity'] == 'critical' else 'warn'}'>{e(f['severity'])}</span> {e(f['title'])}"
            + (f" <code>{e(str(f['file']))}:{e(str(f.get('start_line')))}</code>" if f.get("file") else "")
            + (f" — fix: {e(f['fix'])}" if f.get("fix") else "") + "</li>" for f in rep["findings"]) + "</ul>")
    H.append("<h2>Gates</h2><ul>" + "".join(f"<li><span class='pill {_cls(g['level'])}'>{e(g['level'])}</span> "
                                             f"{e(g['gate'].replace('_', ' '))}: {e(g['reason'])}</li>" for g in rep["gates"]) + "</ul>")
    if rep["recommendations"]:
        H.append("<h2>Recommendations</h2><ol>" + "".join(f"<li><span class='pill {'bad' if r['severity'] == 'critical' else 'warn' if r['severity'] == 'warning' else ''}'>"
                                                         f"{e(r['severity'])}</span> {e(r['summary'])}</li>" for r in rep["recommendations"]) + "</ol>")
    mix = (rep["coverage"] or {}).get("evidence_mix")
    if mix:
        b = mix["by_strength"]
        H.append(f"<h2>Evidence coverage</h2><p>E5 {b['E5']} · E4 {b['E4']} · E3 {b['E3']} · E2 {b['E2']} · E1/none {b['E1'] + b['none']} — "
                 f"{mix['runtime_share']:.0%} of criteria proven at runtime; {mix['credit_by_basis']['code']:.0%} of earned credit from code evidence.</p>")
    if rep["limitations"]:
        H.append("<h2>Limitations</h2><ul>" + "".join(f"<li>{e(x)}</li>" for x in rep["limitations"]) + "</ul>")
    H.append("<h2>Method</h2><ul>" + "".join(f"<li class='muted'>{e(x)}</li>" for x in rep["method"]) + "</ul>")
    H.append("</main></body></html>")
    return "".join(H)
