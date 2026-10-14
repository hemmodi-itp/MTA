"""Generate a self-contained HTML QA report from the upgraded report dict."""

import html as _html


def _esc(text) -> str:
    return _html.escape(str(text) if text is not None else "")


def _fmt_duration(ms) -> str:
    ms = int(ms or 0)
    if ms <= 0:
        return "—"
    if ms < 1000:
        return f"{ms}ms"
    s = ms / 1000
    if s < 60:
        return f"{s:.1f}s"
    m, sec = divmod(int(s), 60)
    return f"{m}m {sec}s"


def _chip(status: str) -> str:
    cls = {
        "success": "chip-success",
        "passed":  "chip-success",
        "failed":  "chip-failed",
        "skipped": "chip-skipped",
        "flaky":   "chip-flaky",
    }.get((status or "").lower(), "chip-skipped")
    return f'<span class="chip {cls}">{_esc(status.upper() if status else "UNKNOWN")}</span>'


_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: #f0f2f5; color: #1a1a2e; min-height: 100vh; padding-bottom: 48px;
}

/* ── Header ── */
.run-header {
  background: linear-gradient(135deg, #1e3a5f 0%, #2c5282 100%);
  color: white; padding: 28px 40px;
}
.run-header h1 {
  font-size: 1.85rem; font-weight: 700; margin-bottom: 6px;
  display: flex; align-items: center; flex-wrap: wrap; gap: 10px;
}
.run-header .meta { font-size: 0.82rem; opacity: 0.7; margin-top: 10px; }
.run-header .hstats {
  margin-top: 14px; display: flex; gap: 28px; flex-wrap: wrap;
}
.run-header .hstats span { font-size: 0.88rem; color: rgba(255,255,255,0.82); }
.run-header .hstats strong { color: white; }
.spill {
  display: inline-flex; align-items: center;
  padding: 4px 14px; border-radius: 20px; font-weight: 700; font-size: 0.85rem;
}
.spill-success { background: #27ae60; }
.spill-failed  { background: #e74c3c; }
.dpill {
  display: inline-block;
  background: rgba(255,255,255,0.15);
  border-radius: 20px; padding: 3px 12px; font-size: 0.82rem;
}

/* ── Sections ── */
.section {
  background: white; margin: 20px 40px; border-radius: 10px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.07); overflow: hidden;
}
.sec-title {
  padding: 16px 24px; border-bottom: 1px solid #eee;
  font-weight: 700; font-size: 1rem;
  display: flex; align-items: center; justify-content: space-between;
}
.sec-cnt {
  background: #eef2ff; color: #4361ee;
  border-radius: 10px; padding: 2px 10px; font-size: 0.78rem; font-weight: 600;
}

/* ── Tables ── */
table { width: 100%; border-collapse: collapse; }
thead th {
  background: #f8fafc; padding: 10px 20px; text-align: left;
  font-size: 0.74rem; font-weight: 700; color: #64748b;
  letter-spacing: 0.06em; text-transform: uppercase;
  border-bottom: 1px solid #e2e8f0;
}
tbody td {
  padding: 11px 20px; font-size: 0.88rem;
  border-bottom: 1px solid #f1f5f9; vertical-align: middle;
}
tbody tr:last-child td { border-bottom: none; }
tr.row-failed  { background: #fff5f5; }
tr.row-skipped { background: #fafafa; color: #94a3b8; }
tr.tc-hdr { cursor: pointer; }
tr.tc-hdr:hover td { background: #f8faff; }
tr.tc-detail td { padding: 0; }
.tc-inner { padding: 12px 24px; background: #f8fafc; border-bottom: 1px solid #e2e8f0; }

/* ── Status chips ── */
.chip { display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 0.73rem; font-weight: 700; }
.chip-success { background: #d1fae5; color: #065f46; }
.chip-failed  { background: #fee2e2; color: #991b1b; }
.chip-skipped { background: #f1f5f9; color: #64748b; }
.chip-flaky   { background: #fef3c7; color: #b45309; }

/* ── Durations ── */
.dur { color: #94a3b8; font-family: monospace; font-size: 0.82rem; }

/* ── Artifact summary bar ── */
.art-wrapper { padding: 0 24px 24px; }
.art-summary {
  display: flex; gap: 0; padding: 18px 0 20px;
  flex-wrap: wrap; align-items: center;
  border-bottom: 1px solid #e2e8f0; margin-bottom: 20px;
}
.art-summary .s-item {
  display: flex; align-items: baseline; gap: 7px;
  padding: 0 22px; border-right: 1px solid #e2e8f0;
}
.art-summary .s-item:first-child { padding-left: 0; }
.art-summary .s-item:last-child  { border-right: none; }
.art-summary .s-num { font-size: 1.65rem; font-weight: 800; color: #1e3a8a; line-height: 1; }
.art-summary .s-lbl { font-size: 0.76rem; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.04em; }

/* ── Artifact cards ── */
.cards-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
}
.acard {
  border: 1px solid #e2e8f0; border-radius: 10px;
  overflow: hidden; background: white;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  display: flex; flex-direction: column;
}
.acard-hd {
  padding: 10px 14px; background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
}
.acard .slbl {
  font-size: 0.7rem; font-weight: 700; color: #475569;
  text-transform: uppercase; letter-spacing: 0.07em;
}
.acard-bd { padding: 12px 14px; flex: 1; }
.acard ul { list-style: none; }
.acard li { font-size: 0.81rem; padding: 2px 0; color: #374151; word-break: break-all; }
.acard li::before { content: "› "; color: #94a3b8; }
.acard.csuccess .acard-hd { background: #f0fdf4; border-color: #bbf7d0; }
.acard.csuccess .slbl { color: #15803d; }
.acard.cfailed { border-color: #fca5a5; }
.acard.cfailed .acard-hd { background: #fff5f5; border-color: #fca5a5; }
.acard.cfailed .slbl { color: #dc2626; }
.acard.cskipped .acard-hd { background: #f8fafc; }
.acard.cskipped .slbl { color: #94a3b8; }
.acard.cskipped .acard-bd { color: #94a3b8; }

/* ── Test suite bar ── */
.suite-bar {
  display: flex; gap: 32px; padding: 16px 24px;
  border-bottom: 1px solid #eee; background: #fafafa;
}
.stat-block .num { font-size: 2rem; font-weight: 800; line-height: 1; }
.stat-block .lbl { font-size: 0.72rem; font-weight: 600; color: #64748b; text-transform: uppercase; }
.npass { color: #059669; }
.nfail { color: #dc2626; }
.nflaky { color: #d97706; }
.nskip { color: #64748b; }
.ntot  { color: #1e40af; }

/* ── Step details inside TC rows ── */
.step-row {
  display: flex; gap: 14px; align-items: flex-start;
  padding: 5px 0; font-size: 0.82rem;
  border-bottom: 1px solid #f1f5f9;
}
.step-row:last-child { border-bottom: none; }
.s-num    { color: #94a3b8; font-family: monospace; min-width: 70px; }
.s-status { min-width: 65px; }
.s-action { min-width: 60px; font-weight: 600; }
.s-col    { display: flex; flex-direction: column; gap: 2px; }
.s-loc    { color: #64748b; font-family: monospace; font-size: 0.78rem; }
.s-err    { color: #dc2626; font-size: 0.78rem; }

/* ── Controls ── */
.controls {
  padding: 8px 24px; display: flex; gap: 8px; justify-content: flex-end;
}
.ctrl-btn {
  background: #f8fafc; border: 1px solid #e2e8f0;
  padding: 4px 12px; border-radius: 6px; cursor: pointer;
  font-size: 0.78rem; color: #64748b;
}
.ctrl-btn:hover { background: #eef2ff; color: #4361ee; border-color: #c7d2fe; }

/* ── Errors ── */
.err-block { padding: 14px 24px; border-bottom: 1px solid #fee2e2; }
.err-block:last-child { border-bottom: none; }
.err-step  { font-weight: 700; color: #dc2626; font-size: 0.88rem; margin-bottom: 6px; }
.err-msg {
  font-family: 'Courier New', monospace; font-size: 0.8rem;
  background: #fef2f2; border: 1px solid #fca5a5; border-radius: 4px;
  padding: 8px 12px; white-space: pre-wrap; word-break: break-all;
}
"""

_JS = """<script>
function toggleRow(id) {
  var el = document.getElementById('td-' + id);
  if (el) el.style.display = el.style.display === 'none' ? 'table-row' : 'none';
}
function expandAll()  { document.querySelectorAll('.tc-detail').forEach(function(e){ e.style.display='table-row'; }); }
function collapseAll(){ document.querySelectorAll('.tc-detail').forEach(function(e){ e.style.display='none'; }); }
function filterTable(id, q) {
  q = (q || '').toLowerCase();
  document.querySelectorAll('#' + id + ' tbody tr').forEach(function(r){
    r.style.display = r.textContent.toLowerCase().indexOf(q) >= 0 ? '' : 'none';
  });
}
function sortTable(id, col) {
  var t = document.getElementById(id), body = t.tBodies[0];
  var dir = t.getAttribute('data-sort') === col + ':asc' ? -1 : 1;
  t.setAttribute('data-sort', col + (dir === 1 ? ':asc' : ':desc'));
  Array.prototype.slice.call(body.rows).sort(function(a, b){
    var x = a.cells[col].textContent.trim(), y = b.cells[col].textContent.trim();
    return x.localeCompare(y, undefined, {numeric: true}) * dir;
  }).forEach(function(r){ body.appendChild(r); });
}
</script>"""


# ──────────────────────────────────────────────
# Section builders
# ──────────────────────────────────────────────

def _header(report: dict) -> str:
    project      = _esc(report.get("project", "Unknown"))
    run_id       = report.get("run_id", "")
    generated_at = report.get("generated_at", "")
    ts_display   = (generated_at[:19].replace("T", " ") + " UTC") if generated_at else ""

    ws       = report.get("workflow_status", {})
    status   = ws.get("status", "unknown")
    total_ms = ws.get("total_duration_ms", 0)
    workflow = _esc(ws.get("workflow", ""))

    ter      = report.get("test_execution_report", {})

    pill_cls  = "spill-success" if status == "success" else "spill-failed"
    pill_lbl  = "✓ PASSED" if status == "success" else "✗ FAILED"
    run_short = (run_id[:8] + "…") if len(run_id) > 8 else run_id

    test_stat = ""
    if ter.get("executed"):
        test_stat = (
            f'<span>Tests: <strong>{ter["passed"]} passed</strong>'
            + (f' / {ter["flaky"]} flaky' if ter.get("flaky") else "")
            + f' / {ter["failed"]} failed'
            f' &nbsp;({_esc(ter.get("pass_rate", "N/A"))})</span>'
        )

    return f"""<div class="run-header">
  <h1>{project}
    <span class="spill {pill_cls}">{pill_lbl}</span>
    <span class="dpill">⏱ {_fmt_duration(total_ms)}</span>
  </h1>
  <div class="meta">Run ID: {_esc(run_short)} &nbsp;·&nbsp; Workflow: {workflow} &nbsp;·&nbsp; {_esc(ts_display)}</div>
  <div class="hstats">
    <span>Pipeline: <strong>{ws.get("steps_passed", 0)} passed</strong>
      / {ws.get("steps_failed", 0)} failed
      / {ws.get("steps_skipped", 0)} skipped</span>
    {test_stat}
  </div>
</div>"""


def _pipeline_section(pipeline_execution: list) -> str:
    if not pipeline_execution:
        return """<div class="section">
  <div class="sec-title">⚙ 1. Process / Workflow Status</div>
  <div style="padding:20px 24px;color:#94a3b8;font-size:0.88rem">No workflow steps recorded for this run.</div>
</div>"""

    rows = []
    for e in pipeline_execution:
        step   = e.get("step", "")
        status = e.get("status", "unknown")
        dur    = _fmt_duration(e.get("duration_ms", 0))
        reason = _esc(e.get("reason") or "—")
        rc     = "row-failed" if status == "failed" else ("row-skipped" if status == "skipped" else "")
        rows.append(
            f'    <tr class="{rc}">'
            f'<td><strong>{_esc(step.replace("_", " ").title())}</strong></td>'
            f'<td>{_chip(status)}</td>'
            f'<td><span class="dur">{dur}</span></td>'
            f'<td style="font-size:0.82rem;color:#64748b;max-width:420px">{reason}</td>'
            f'</tr>'
        )

    return f"""<div class="section">
  <div class="sec-title">⚙ 1. Process / Workflow Status <span class="sec-cnt">{len(pipeline_execution)} steps</span></div>
  <table>
    <thead><tr><th>Step</th><th>Status</th><th>Duration</th><th>Notes</th></tr></thead>
    <tbody>
{chr(10).join(rows)}
    </tbody>
  </table>
</div>"""


def _artifact_card(step: str, status: str, artifacts) -> str:
    label = step.replace("_", " ").title()

    if status == "skipped":
        return (
            f'<div class="acard cskipped">'
            f'<div class="acard-hd"><div class="slbl">{_esc(label)}</div></div>'
            f'<div class="acard-bd"><ul><li>Skipped — upstream failure</li></ul></div>'
            f'</div>'
        )

    if not artifacts:
        if status == "failed":
            return (
                f'<div class="acard cfailed">'
                f'<div class="acard-hd"><div class="slbl">{_esc(label)}</div></div>'
                f'<div class="acard-bd"><ul><li>Step failed — no artifacts produced</li></ul></div>'
                f'</div>'
            )
        return ""

    items = []
    for key, val in artifacts.items():
        if key == "files":
            continue
        if isinstance(val, int):
            human = key.replace("_", " ").strip()
            items.append(f"<li>{val} {_esc(human)}</li>")
        elif isinstance(val, bool):
            items.append(f"<li>{_esc(key.replace('_', ' '))}: {val}</li>")

    for fpath in (artifacts.get("files") or []):
        if fpath:
            fname = str(fpath).replace("\\", "/").split("/")[-1]
            items.append(f"<li>📄 {_esc(fname)}</li>")

    body = "\n  ".join(items) if items else "<li>—</li>"
    status_cls = "csuccess" if status in ("success", "passed") else ""
    return (
        f'<div class="acard {status_cls}">'
        f'<div class="acard-hd"><div class="slbl">{_esc(label)}</div></div>'
        f'<div class="acard-bd"><ul>\n  {body}\n</ul></div>'
        f'</div>'
    )


def _artifacts_section(artifacts_generated: dict) -> str:
    per_step = artifacts_generated.get("per_step", [])
    summary  = artifacts_generated.get("summary", {})

    cards = [_artifact_card(e.get("step", ""), e.get("status", ""), e.get("artifacts"))
             for e in per_step]
    cards = [c for c in cards if c]

    summary_html = ""
    if any(v for v in summary.values()):
        s_items = "".join(
            f'<div class="s-item"><span class="s-num">{v}</span>'
            f'<span class="s-lbl">{_esc(k.replace("_", " "))}</span></div>'
            for k, v in summary.items() if v
        )
        summary_html = f'<div class="art-summary">{s_items}</div>'

    body = f'<div class="cards-grid">\n{chr(10).join(cards)}\n</div>' if cards else \
        '<div style="padding:20px 0;color:#94a3b8;font-size:0.88rem">No test artifacts generated in this session.</div>'

    return f"""<div class="section">
  <div class="sec-title">📦 2. Artifacts Generated</div>
  <div class="art-wrapper">
    {summary_html}
    {body}
  </div>
</div>"""


def _failure_summary_section(failure_summary: list) -> str:
    """Groups failures sharing one root cause (e.g. one bad locator behind
    13 of 21 failures) into a single row with a count, instead of leaving the
    reader to scroll through N separately-collapsed raw stack traces that all
    say the same thing to notice the pattern themselves."""
    if not failure_summary:
        return ""

    rows = []
    for g in failure_summary:
        tc_ids = ", ".join(g["test_case_ids"])
        rows.append(f"""    <tr>
      <td><span class="chip chip-failed">{g["count"]}×</span></td>
      <td><code>{_esc(g["signature"])}</code></td>
      <td style="color:#64748b;font-size:0.82rem">{_esc(tc_ids)}</td>
    </tr>""")

    return f"""  <div class="sec-title" style="font-size:0.95rem;margin-top:8px">🔎 Failure Summary (by root cause)</div>
  <table>
    <thead><tr><th>Count</th><th>Root cause</th><th>Affected tests</th></tr></thead>
    <tbody>
{chr(10).join(rows)}
    </tbody>
  </table>
"""


def _test_section(ter: dict) -> str:
    test_results = ter.get("results", [])
    executed     = ter.get("executed", False)

    if not executed:
        return """<div class="section">
  <div class="sec-title">🧪 3. Test Execution Report</div>
  <div style="padding:20px 24px;color:#94a3b8;font-size:0.88rem">No tests were executed in this session.</div>
</div>"""

    total  = ter.get("total", len(test_results))
    passed = ter.get("passed", 0)
    failed = ter.get("failed", total - passed)

    rows = []
    for r in test_results:
        tc_id   = r.get("test_case_id", "")
        tc_name = r.get("test_case_name", "")
        bs_id   = r.get("business_scenario_id", "")
        status  = r.get("status", "unknown")
        steps   = r.get("steps") or []
        errors  = r.get("errors") or []

        safe_id = _esc(tc_id).replace("-", "_").replace(" ", "_")
        rc = "row-failed" if status == "failed" else ""

        step_rows = []
        for s in (steps if isinstance(steps, list) else []):
            if not isinstance(s, dict):
                continue
            s_id     = _esc(s.get("step_id", ""))
            s_action = _esc(s.get("action", ""))
            s_status = s.get("status", "unknown")
            s_loc    = _esc(s.get("locator_id") or "")
            details  = s.get("details") or {}
            s_err    = _esc(str(details.get("error", ""))) if details.get("error") else ""
            err_html = f'<span class="s-err">{s_err}</span>' if s_err else ""
            step_rows.append(
                f'<div class="step-row">'
                f'<span class="s-num">{s_id}</span>'
                f'<span class="s-status">{_chip(s_status)}</span>'
                f'<span class="s-action">{s_action}</span>'
                f'<div class="s-col"><span class="s-loc">{s_loc}</span>{err_html}</div>'
                f'</div>'
            )

        if step_rows:
            step_body = "\n".join(step_rows)
        elif errors:
            # ui_execution results have no "steps" shape — render the flat
            # errors list instead of silently dropping it.
            error_rows = "\n".join(
                f'<div class="step-row"><span class="s-err">{_esc(str(e))}</span></div>'
                for e in errors
            )
            step_body = error_rows
        else:
            step_body = '<div style="color:#94a3b8;font-size:0.82rem">No step details available</div>'

        rows.append(f"""    <tr class="tc-hdr {rc}" onclick="toggleRow('{safe_id}')">
      <td>{_chip(status)}</td>
      <td><strong>{_esc(tc_id)}</strong></td>
      <td>{_esc(tc_name)}</td>
      <td style="color:#64748b">{_esc(bs_id)}</td>
      <td style="color:#94a3b8;font-size:0.75rem">▼</td>
    </tr>
    <tr id="td-{safe_id}" class="tc-detail" style="display:none">
      <td colspan="5"><div class="tc-inner">{step_body}</div></td>
    </tr>""")

    return f"""<div class="section">
  <div class="sec-title">🧪 3. Test Execution Report <span class="sec-cnt">{total} tests</span></div>
  <div class="suite-bar">
    <div class="stat-block"><div class="num npass">{passed}</div><div class="lbl">Passed</div></div>
    <div class="stat-block"><div class="num nflaky">{ter.get("flaky", 0)}</div><div class="lbl">⚠ Flaky</div></div>
    <div class="stat-block"><div class="num nfail">{failed}</div><div class="lbl">Failed</div></div>
    <div class="stat-block"><div class="num nskip">{ter.get("skipped", 0)}</div><div class="lbl">○ Skipped</div></div>
    <div class="stat-block"><div class="num ntot">{total}</div><div class="lbl">Total</div></div>
  </div>
{_failure_summary_section(ter.get("failure_summary") or [])}
  <div class="controls">
    <button class="ctrl-btn" onclick="expandAll()">Expand All</button>
    <button class="ctrl-btn" onclick="collapseAll()">Collapse All</button>
  </div>
  <table>
    <thead><tr><th></th><th>TC ID</th><th>Test Name</th><th>Scenario</th><th></th></tr></thead>
    <tbody>
{chr(10).join(rows)}
    </tbody>
  </table>
</div>"""


def _healing_phase6(hr: dict) -> str:
    """Phase 6: triage verdicts, product defects (never healed), heals refused for review, reverts, proposals, burn-in."""
    parts = []
    tc = hr.get("triage_counts") or {}
    if tc:
        chips = " · ".join(f"{_esc(k)}: <strong>{_esc(v)}</strong>" for k, v in sorted(tc.items()))
        parts.append(f'<div><b>Triage</b> — {chips}'
                     + (f' · mode: {_esc(hr.get("mode"))}' if hr.get("mode") else "") + "</div>")
    if hr.get("skipped_reason"):
        parts.append(f'<div style="color:#d97706"><b>Healing skipped</b> — {_esc(hr["skipped_reason"])}</div>')
    for d in hr.get("defects") or []:
        parts.append(f'<div style="color:#dc2626">Product defect (not healed): {_esc(d.get("spec_file"))} — '
                     f'{_esc(d.get("test_name"))} <span class="s-err">{_esc("; ".join(d.get("evidence") or []))}</span></div>')
    for r in hr.get("needs_review") or []:
        parts.append(f'<div style="color:#d97706">Needs review: locator <code>{_esc(r.get("key"))}</code> — '
                     f'{_esc(r.get("reason"))}</div>')
    for r in hr.get("reverted") or []:
        parts.append(f'<div style="color:#d97706">Reverted fix for <code>{_esc(r.get("key"))}</code> — it broke '
                     f'{_esc(", ".join(r.get("broke") or []))}</div>')
    for pr in hr.get("proposals") or []:
        parts.append(f'<div>Proposed (not applied): {_esc(pr.get("target"))} → <a href="{_esc(pr.get("diff"))}">diff</a></div>')
    bi = hr.get("burn_in") or {}
    if bi.get("stable") or bi.get("unstable"):
        parts.append(f'<div><b>Burn-in</b> (--repeat-each=3) — healed: {_esc(", ".join(bi.get("stable") or []) or "none")}'
                     f' · unstable: {_esc(", ".join(bi.get("unstable") or []) or "none")}</div>')
    if hr.get("audit_log"):
        parts.append(f'<div style="color:#64748b">Audit log: {_esc(hr["audit_log"])}</div>')
    if not parts:
        return ""
    return '<div style="padding:8px 24px;font-size:0.88rem;line-height:1.7">' + "".join(parts) + "</div>"


def _healing_section(hr: dict) -> str:
    if not hr:
        return ""

    rounds = hr.get("rounds", [])
    not_healable = hr.get("not_healable", [])
    final = hr.get("final_result", {})

    round_blocks = []
    for r in rounds:
        rnum = r.get("round", "?")
        specs_html = ", ".join(_esc(s) for s in r.get("spec_files", [])) or "—"
        if not r.get("ran", False):
            body = f'<div class="err-msg" style="margin-top:6px">{_esc(r.get("error", "run failed"))}</div>'
        else:
            body = (
                f'<div class="suite-bar" style="padding:10px 0;border-bottom:none;background:transparent">'
                f'<div class="stat-block"><div class="num npass">{r.get("passed", 0)}</div><div class="lbl">Passed</div></div>'
                f'<div class="stat-block"><div class="num nfail">{r.get("failed", 0)}</div><div class="lbl">Failed</div></div>'
                f'<div class="stat-block"><div class="num ntot">{r.get("remaining_after", 0)}</div><div class="lbl">Still Failing</div></div>'
                f'</div>'
            )
        round_blocks.append(f"""    <div class="err-block" style="border-color:#e2e8f0">
      <div class="err-step" style="color:#1e3a8a">Round {rnum} — {specs_html}</div>
      {body}
    </div>""")

    rounds_html = "\n".join(round_blocks) if round_blocks else \
        '  <div style="padding:16px 24px;color:#94a3b8;font-size:0.88rem">Healing ran but completed no verification rounds.</div>'

    not_healable_html = ""
    if not_healable:
        nh_rows = "\n".join(
            f'<div class="step-row"><div class="s-col">'
            f'<strong>{_esc(n.get("spec_file",""))}</strong> — {_esc(n.get("test_name",""))}'
            f'<span class="s-err">{_esc(n.get("reason",""))}</span></div></div>'
            for n in not_healable
        )
        not_healable_html = f"""
  <div class="tc-inner" style="margin:0 24px 20px">
    <div style="font-weight:700;color:#dc2626;margin-bottom:8px">Not Healable ({len(not_healable)})</div>
    {nh_rows}
  </div>"""

    phase6_html = _healing_phase6(hr)
    return f"""<div class="section">
  <div class="sec-title">🩹 4. Healing Report <span class="sec-cnt">{len(rounds)} round(s)</span></div>
{phase6_html}
{rounds_html}
{not_healable_html}
  <div class="suite-bar" style="border-top:2px solid #e2e8f0">
    <div class="stat-block"><div class="num npass">{final.get("passed", 0)}</div><div class="lbl">Final Passed</div></div>
    <div class="stat-block"><div class="num nfail">{final.get("failed", 0)}</div><div class="lbl">Final Failed</div></div>
    <div class="stat-block"><div class="num ntot">{final.get("total", 0)}</div><div class="lbl">Final Total</div></div>
    <div class="stat-block"><div class="num" style="color:#4361ee">{_esc(final.get("pass_rate", "N/A"))}</div><div class="lbl">Pass Rate</div></div>
  </div>
</div>"""


def _traceability_section(tr: dict) -> str:
    """Phase 1.2: requirement coverage — every AC, its tests and latest result; zero-test ACs with the reason."""
    if not tr:
        return ""
    s = tr.get("summary") or {}
    pct = s.get("coverage_pct")
    pct_html = f"{pct}%" if pct is not None else "N/A"

    rows = []
    for a in tr.get("acs") or []:
        tests = a.get("tests") or []
        tests_html = "<br>".join(
            f'{_esc(t.get("tc_id"))} {_chip(t.get("status") or "not_run")} '
            f'<span style="color:#64748b">{_esc(t.get("link"))}</span>' for t in tests) or "—"
        reason = a.get("uncovered_reason") or {}
        reason_html = (f'<strong>{_esc(reason.get("code"))}</strong> {_esc(reason.get("detail"))}'
                       if reason else "")
        indent = "padding-left:22px" if a.get("parent_id") else ""
        rows.append(
            f'<tr><td style="{indent}"><strong>{_esc(a.get("id"))}</strong></td>'
            f'<td>{_esc(a.get("priority"))}</td><td>{_esc(a.get("testability"))}</td>'
            f'<td>{_esc(a.get("statement"))}</td><td>{_esc(a.get("status"))}</td>'
            f'<td>{tests_html}</td><td>{reason_html}</td></tr>')

    unlinked = tr.get("unlinked_tests") or []
    unlinked_html = ""
    if unlinked:
        items = "".join(f'<div class="step-row"><div class="s-col">{_esc(u.get("tc_id"))} — '
                        f'{_esc(u.get("title"))} <span class="s-err">{_esc(u.get("spec_file"))}</span>'
                        f'</div></div>' for u in unlinked)
        unlinked_html = (f'<div class="tc-inner" style="margin:0 24px 20px"><div style="font-weight:700;'
                         f'color:#dc2626;margin-bottom:8px">Tests linked to no acceptance criterion '
                         f'({len(unlinked)})</div>{items}</div>')

    by_reason = s.get("by_reason") or {}
    reasons_html = ", ".join(f"{_esc(k)}: {v}" for k, v in by_reason.items()) or "none"
    return f"""<div class="section" id="traceability">
  <div class="sec-title">📋 Requirements Traceability <span class="sec-cnt">{len(tr.get("uncovered") or [])} AC(s) with no test</span></div>
  <div class="suite-bar">
    <div class="stat-block"><div class="num" style="color:#4361ee">{pct_html}</div><div class="lbl">AC Coverage (automatable)</div></div>
    <div class="stat-block"><div class="num ntot">{s.get("acs_covered", 0)}/{s.get("acs_automatable", 0)}</div><div class="lbl">Covered</div></div>
    <div class="stat-block"><div class="num npass">{s.get("acs_passing", 0)}</div><div class="lbl">ACs Passing</div></div>
    <div class="stat-block"><div class="num nfail">{s.get("acs_failing", 0)}</div><div class="lbl">ACs Failing</div></div>
  </div>
  <div style="padding:8px 24px;color:#475569;font-size:0.85rem">Not tested, by reason: {reasons_html}</div>
  <div style="padding:4px 24px"><input type="search" placeholder="Filter the matrix (AC, text, status, test id)…"
    oninput="filterTable('trace-matrix', this.value)" style="width:100%;max-width:480px;padding:6px 8px;border:1px solid #cbd5e1;border-radius:6px"></div>
  <table id="trace-matrix">
    <thead><tr>{''.join(f'<th onclick="sortTable(\'trace-matrix\', {i})" style="cursor:pointer" title="Sort">{h} ⇅</th>' for i, h in enumerate(("AC", "Priority", "Testability", "Criterion", "Status", "Tests (latest result)", "Why untested")))}</tr></thead>
    <tbody>
{chr(10).join(rows)}
    </tbody>
  </table>
{unlinked_html}
</div>"""


def _errors_section(ev: dict) -> str:
    errors   = ev.get("errors", [])
    warnings = ev.get("warnings", [])

    blocks = []
    for e in errors:
        step   = _esc(e.get("step", "unknown"))
        reason = _esc(e.get("reason", "No details available"))
        blocks.append(
            f'  <div class="err-block">'
            f'<div class="err-step">✗ {step}</div>'
            f'<div class="err-msg">{reason}</div>'
            f'</div>'
        )
    for w in warnings:
        blocks.append(
            f'  <div class="err-block" style="border-color:#fde68a">'
            f'<div class="err-step" style="color:#d97706">⚠ Warning</div>'
            f'<div class="err-msg" style="background:#fffbeb;border-color:#fde68a">{_esc(str(w))}</div>'
            f'</div>'
        )

    cnt_lbl = f"{len(errors)} error(s), {len(warnings)} warning(s)"
    body = chr(10).join(blocks) if blocks else \
        '  <div style="padding:20px 24px;color:#94a3b8;font-size:0.88rem">No errors or validation issues.</div>'

    return f"""<div class="section">
  <div class="sec-title" style="color:#dc2626">⚠ 5. Errors &amp; Validation <span class="sec-cnt">{cnt_lbl}</span></div>
{body}
</div>"""


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

def _quality_sections(q: dict) -> str:
    """Phase 11: executive summary (every number links to its evidence below), risk areas, trend, defects with
    evidence, not-tested list, potential defects, coverage dashboard and the 29119-3 test summary report."""
    if not q:
        return ""
    sm, gt = q.get("summary") or {}, q.get("gates") or {}
    verdict = gt.get("verdict", "NO_GATES")
    color = {"PASS": "#16a34a", "FAIL": "#dc2626"}.get(verdict, "#64748b")
    na = lambda v: "n/a" if v is None else _esc(v)  # noqa: E731
    link = lambda anchor, text: f'<a href="#{anchor}">{text}</a>'  # noqa: E731
    gates = "".join(
        f'<div>{"✓" if g["ok"] else "✗"} <strong>{_esc(g["gate"])}</strong>: {na(g["actual"])} '
        f'(need {"≤" if g.get("kind") == "max" else "≥"} {_esc(g["threshold"])})</div>'
        for g in gt.get("gates") or []) or "No quality gates configured."
    cov = sm.get("requirement_coverage")
    prio = " &nbsp;".join(f'{p}: {("%s%% (%s/%s)" % (v["rate"], v["passed"], v["executed"])) if v else "n/a"}'
                          for p, v in (sm.get("pass_rate_by_priority") or {}).items())
    sev = sm.get("defects_by_severity") or {}
    sev_html = " · ".join(f"{_esc(k)} {link('defects', _esc(v))}" for k, v in sev.items()) or "none"
    dims = sm.get("agent_dimensions")
    dims_html = ", ".join(f"{_esc(d)}: {_esc(o)}" for d, o in dims.items()) if dims else "n/a"
    files = " · ".join(f'<a href="{_esc(q[k])}">{label}</a>' for k, label in
                       (("csv_path", "traceability CSV"), ("xlsx_path", "XLSX"), ("tsr_path", "test summary report (md)"))
                       if q.get(k))
    exports = " · ".join(f'<a href="{_esc(v)}">{_esc(k)} export</a>' for k, v in (q.get("exports") or {}).items())
    nt = q.get("not_tested") or []
    summary = f"""<div class="section" id="summary">
  <div class="sec-title">Executive Summary <span class="sec-cnt" style="color:{color}">Verdict: {verdict}</span></div>
  <div style="padding:8px 24px;font-size:0.9rem;line-height:1.7">{gates}
    <div>Requirement (AC) coverage: <strong>{link('traceability', na(cov) + ('%' if cov is not None else ''))}</strong> ({na(sm.get("acs_covered"))}/{na(sm.get("acs_automatable"))}) · not tested: {link('not-tested', str(len(nt)))}</div>
    <div>Pass rate by priority: {prio}</div>
    <div>Product defects: <strong>{link('defects', na(sm.get("product_defects")))}</strong> — by severity: {sev_html} · potential (BRD vs observed): {link('potential-defects', na(sm.get("potential_defects")))}</div>
    <div>Critical a11y: <strong>{na(sm.get("critical_a11y"))}</strong> · High security: <strong>{na(sm.get("high_security"))}</strong> · Worst perf regression: {na(sm.get("perf_regression_pct"))}% · Flaky rate: {na(sm.get("flaky_rate"))}% · Weak oracles: {na(sm.get("weak_oracle"))} · Low-confidence (LLM-inferred) oracles: {na(sm.get("low_confidence_oracles"))}</div>
    <div>AI-agent dimensions: {dims_html}</div>
    <div style="color:#64748b">{files}{(' · ' + exports) if exports else ''}</div></div>
</div>"""
    return (summary + _risk_trend_html(q) + _defects_html(q.get("defects") or []) + _not_tested_html(nt)
            + _potential_html(q.get("potential_defects") or []) + _coverage_html(q.get("coverage")) + _tsr_html(q))


def _risk_trend_html(q: dict) -> str:
    risks = q.get("risk_areas") or []
    rows = "".join(f'<tr><td>{_esc(r["area"])}</td><td>{_esc(r["score"])}</td><td>{_esc(", ".join(r["why"]))}</td></tr>'
                   for r in risks)
    risk = (f'<div class="section" id="risk"><div class="sec-title">Top risk areas</div><table><thead><tr><th>Area</th>'
            f'<th>Risk score</th><th>Why</th></tr></thead><tbody>{rows}</tbody></table></div>') if risks else ""
    tr = q.get("trend") or {}
    runs = tr.get("runs") or []
    delta = tr.get("delta") or {}
    arrow = lambda v: "" if v is None else (f' <span style="color:#64748b">({"+" if v > 0 else ""}{v})</span>')  # noqa: E731
    trows = "".join(f'<tr><td>{_esc(r.get("run"))}</td><td>{_esc(r.get("pass_rate"))}</td>'
                    f'<td>{_esc(r.get("requirement_coverage"))}</td><td>{_esc(r.get("product_defects"))}</td>'
                    f'<td>{_esc(r.get("flaky"))}</td><td>{_esc(r.get("verdict"))}</td></tr>' for r in runs)
    trend = ""
    if runs or delta:
        trend = (f'<div class="section" id="trend"><div class="sec-title">Trend vs the last {len(runs)} run(s)</div>'
                 f'<div style="padding:8px 24px;font-size:0.88rem">Change since the previous run: pass rate'
                 f'{arrow(delta.get("pass_rate"))} · coverage{arrow(delta.get("requirement_coverage"))} · defects'
                 f'{arrow(delta.get("product_defects"))} · flaky{arrow(delta.get("flaky"))}</div>'
                 f'<table><thead><tr><th>Run</th><th>Pass %</th><th>Coverage %</th><th>Defects</th><th>Flaky</th>'
                 f'<th>Verdict</th></tr></thead><tbody>{trows}</tbody></table></div>')
    return risk + trend


def _defects_html(defects: list) -> str:
    if not defects:
        return ""
    blocks = ""
    for d in defects:
        ev = d.get("evidence") or {}
        files = " · ".join(f'<a href="{_esc(ev[k])}">{k}</a>' for k in ("screenshot", "trace", "video", "har", "console")
                           if ev.get(k)) or "no evidence files"
        ctx = " · ".join(f"{k}: {_esc(ev[k])}" for k in ("browser", "role", "environment", "run") if ev.get(k))
        har = "".join(f"<li>{_esc(x)}</li>" for x in ev.get("har_excerpt") or [])
        steps = "".join(f"<li>{_esc(x)}</li>" for x in d.get("steps") or [])
        blocks += (f'<div class="tc-inner" style="margin:0 24px 14px"><strong>{_esc(d.get("title"))}</strong> '
                   f'{_chip("failure")} <span style="color:#64748b">severity {_esc(d.get("severity"))} · '
                   f'AC: {_esc(", ".join(d.get("ac_ids") or []) or "unlinked")}</span>'
                   f'<ol>{steps}</ol><div><b>Expected</b> ({_esc(d.get("expected_source") or "")}): {_esc(d.get("expected"))}</div>'
                   f'<div><b>Actual:</b> {_esc(d.get("actual"))}</div><div>{files}</div>'
                   + (f'<div style="color:#64748b">{ctx}</div>' if ctx else "")
                   + (f'<div>Failed requests:<ul>{har}</ul></div>' if har else "") + '</div>')
    return (f'<div class="section" id="defects"><div class="sec-title" style="color:#dc2626">Defects '
            f'<span class="sec-cnt">{len(defects)}</span></div>{blocks}</div>')


def _not_tested_html(nt: list) -> str:
    if not nt:
        return ""
    rows = "".join(f'<tr><td>{_esc(n["id"])}</td><td>{_esc(n["priority"])}</td><td>{_esc(n["code"])}</td>'
                   f'<td>{_esc(n["detail"])}</td></tr>' for n in nt)
    return (f'<div class="section" id="not-tested"><div class="sec-title">Not tested &amp; why <span class="sec-cnt">'
            f'{len(nt)} AC(s)</span></div><table><thead><tr><th>AC</th><th>Priority</th><th>Reason</th><th>Detail</th>'
            f'</tr></thead><tbody>{rows}</tbody></table></div>')


def _potential_html(pd: list) -> str:
    if not pd:
        return ""
    rows = "".join(f'<tr><td>{_esc(c.get("ac_id"))}</td><td>{_esc(c.get("where"))}</td><td>{_esc(c.get("field"))}</td>'
                   f'<td>{_esc(c.get("brd"))}</td><td>{_esc(c.get("observed"))}</td></tr>' for c in pd)
    return (f'<div class="section" id="potential-defects"><div class="sec-title" style="color:#d97706">Potential defects — '
            f'BRD vs observed <span class="sec-cnt">{len(pd)} for human review</span></div>'
            f'<table><thead><tr><th>AC</th><th>Where</th><th>Field / role</th><th>BRD says</th><th>App did</th></tr>'
            f'</thead><tbody>{rows}</tbody></table></div>')


def _coverage_html(cov) -> str:
    if not cov:
        return ""
    pct = lambda d: f'{_esc(d.get("pct"))}%' if d and d.get("pct") is not None else "n/a"  # noqa: E731
    tech = " · ".join(f'{_esc(k)} {v.get("selected", 0)}/{v.get("selected", 0) + v.get("cut", 0)}'
                      for k, v in (cov.get("technique") or {}).items()) or "no test design (test_cases.json)"
    ps = cov.get("page_state") or {}
    untested = ", ".join(_esc(x) for x in ps.get("untested") or [])
    rows = [
        ("Requirement (AC)", f'{_esc((cov.get("requirement") or {}).get("covered"))}/{_esc((cov.get("requirement") or {}).get("total"))} — {pct(cov.get("requirement"))}'),
        ("Technique (selected / designed)", tech),
        ("Element (locator keys used)", f'{_esc((cov.get("element") or {}).get("used"))}/{_esc((cov.get("element") or {}).get("total"))} — {pct(cov.get("element"))}'),
        ("Page / state", f'{_esc(ps.get("tested"))}/{_esc(ps.get("total"))} — {pct(ps)}' + (f'<br><span style="color:#64748b">untested: {untested}</span>' if untested else "")),
        ("Transition", f'{_esc((cov.get("transition") or {}).get("cases"))} state-transition case(s), {_esc((cov.get("transition") or {}).get("known"))} known transition(s)'),
        ("API endpoint", f'{_esc((cov.get("api") or {}).get("referenced"))}/{_esc((cov.get("api") or {}).get("total"))} — {pct(cov.get("api"))}'),
        ("Role matrix", f'{_esc(", ".join((cov.get("role_matrix") or {}).get("roles") or []) or "none")} ({_esc((cov.get("role_matrix") or {}).get("cases"))} case(s))'),
        ("Browser / device", " · ".join(f"{_esc(k)}: {v}" for k, v in (cov.get("browser") or {}).items()) or "n/a"),
        ("Test type", " · ".join(f"{_esc(k)}: {v}" for k, v in (cov.get("test_type") or {}).items()) or "n/a"),
        ("Code", _esc(cov.get("code"))),
    ]
    body = "".join(f"<tr><td><strong>{k}</strong></td><td>{v}</td></tr>" for k, v in rows)
    return (f'<div class="section" id="coverage"><div class="sec-title">Coverage dashboard</div>'
            f'<table><tbody>{body}</tbody></table></div>')


def _tsr_html(q: dict) -> str:
    t = q.get("test_summary_report")
    if not t:
        return ""
    r = t.get("results") or {}
    lis = lambda xs: "".join(f"<li>{_esc(x)}</li>" for x in xs) or "<li>none</li>"  # noqa: E731
    sev = ", ".join(f"{_esc(k)} {v}" for k, v in ((t.get("defects") or {}).get("by_severity") or {}).items())
    return f"""<div class="section" id="tsr">
  <div class="sec-title">Test Summary Report <span class="sec-cnt">ISO/IEC/IEEE 29119-3</span></div>
  <div style="padding:8px 24px;font-size:0.88rem;line-height:1.6">
    <div><b>Scope.</b> {_esc(t.get("scope"))}</div>
    <div><b>Approach.</b> {_esc(t.get("approach"))}</div>
    <div><b>Deviations.</b><ul>{lis(t.get("deviations") or [])}</ul></div>
    <div><b>Results.</b> {r.get("executed", 0)} executed: {r.get("passed", 0)} passed, {r.get("failed", 0)} failed, {r.get("flaky", 0)} flaky, {r.get("skipped", 0)} skipped.</div>
    <div><b>Defects.</b> {(t.get("defects") or {}).get("total", 0)} ({sev})</div>
    <div><b>Residual risk.</b><ul>{lis(t.get("residual_risk") or [])}</ul></div>
    <div><b>Recommendation.</b> <strong>{_esc(t.get("verdict"))}</strong> — {_esc(t.get("recommendation"))}</div>
  </div>
</div>"""

def build_html_report(report: dict) -> str:
    """Return a complete self-contained HTML QA report string."""
    project = _esc(report.get("project", "Unknown"))
    ws    = report.get("workflow_status", {})
    ag    = report.get("artifacts_generated", {})
    ter   = report.get("test_execution_report", {})
    hr    = report.get("healing_report")
    tr    = report.get("traceability")
    ev    = report.get("errors_and_validation", {})
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{project} · QA Report</title>
  <style>{_CSS}</style>
</head>
<body>
{_header(report)}
{_quality_sections(report.get("quality"))}
{_pipeline_section(ws.get("steps", []))}
{_artifacts_section(ag)}
{_test_section(ter)}
{_healing_section(hr)}
{_traceability_section(tr)}
{_errors_section(ev)}
{_JS}
</body>
</html>"""
