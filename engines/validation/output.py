"""
output.py — Output Validation Engine.

    checks = deterministic_checks(bundle, artifact_dir)
    payload = judge_payload(bundle, artifact_dir)              # sent to the LLM judge by the agent
    judged = ground_judgement(raw_judgement, bundle, artifact_dir)
    validation = assemble(bundle, checks, judged)

Compares what an evidence bundle (engines/runtime/evidence.py) observed with what the test and its BRD
acceptance criterion expect. Two oracles, kept apart because the Pass/Fail Engine weighs them differently:

  * deterministic — computed from the evidence itself: the flow ran to the end; a document was produced,
    readable, non-empty and in the requested format; it reflects the test's input; a reply / 2xx response /
    page change appeared; a negative test was visibly rejected; no server errors; stated time limits.
  * semantic — the LLM judge rates each pass criterion against the observed output (reply, page output,
    or the document's full extracted text). Every "met" must quote the output verbatim; a quote that is not
    in the output is downgraded to "cannot_tell" and flagged, so the judge cannot invent evidence.

No final verdict here: the Pass/Fail Engine combines these into test and criterion verdicts.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

DOC_TEXT_FOR_JUDGE = 12_000
MIN_DOC_WORDS = 50
_NEGATIVE = {"negative", "security", "robustness", "out_of_scope"}
_ERROR_WORDS = re.compile(r"\b(error|invalid|required|must|not allowed|denied|rejected|cannot|can't|unable|failed|"
                          r"please (enter|fill|provide|select)|too (long|short)|forbidden|unauthori[sz]ed)\b", re.I)
_BROKEN_REPLY = re.compile(r"\b(traceback|exception|internal server error|something went wrong|stack trace|undefined|"
                           r"null pointer|\[object object\])\b", re.I)
_FORMATS = {"docx": r"\b(docx|word)\b", "pdf": r"\bpdf\b", "xlsx": r"\b(xlsx|excel|spreadsheet)\b",
            "pptx": r"\b(pptx|powerpoint|slides?|deck)\b", "md": r"\b(markdown|\.md)\b", "csv": r"\bcsv\b"}
_TIME_LIMIT = re.compile(r"\b(?:within|under|less than|below|at most|no more than|<=?|in)\s*(\d+(?:\.\d+)?)\s*"
                         r"(ms|milliseconds?|s|secs?|seconds?|min|minutes?)\b", re.I)
_STOP = set("""about above after again against because before being below between could does doing during each
further having into more most other over same should such than that their them then there these they this those
through under until very what when where which while will with would your yours from have were been also only just
the and for are but not you all any can her was one our out use test user users input inputs value values""".split())


# ── deterministic oracle ────────────────────────────────────────────────────

def deterministic_checks(b: Dict[str, Any], artifact_dir: Path) -> List[Dict[str, Any]]:
    status = b["execution_status"]
    if status not in ("completed", "failed"):
        return []
    obs, comp = b["observed"], b["completeness"]
    kind = comp.get("expected_output")
    negative = (b.get("variant") or "") in _NEGATIVE
    checks: List[Dict[str, Any]] = []

    def add(cid, name, result, detail, weight="core"):
        checks.append({"id": cid, "name": name, "oracle": "deterministic", "result": result, "detail": detail, "weight": weight})

    add("executed", "The test's actions ran to the end", "pass" if status == "completed" else "fail",
        "all steps passed" if status == "completed" else f"stopped at step {b.get('failed_step')}: {b.get('error')}")

    docs = [d for d in obs.get("documents") or [] if d.get("readable")]
    expect_text = " ".join([b.get("expected_behavior") or "", b.get("criterion_statement") or "",
                            *[e.get("expectation") or "" for e in b.get("expectations") or []],
                            *[c for e in b.get("expectations") or [] for c in e.get("pass_criteria") or []]])
    if kind == "document" and not negative:
        add("document_produced", "A document was produced and downloaded", "pass" if obs.get("documents") else "fail",
            ", ".join(d.get("name") or "?" for d in obs.get("documents") or []) or "no file was downloaded")
        if obs.get("documents"):
            add("document_readable", "The document opens and can be read", "pass" if docs else "fail",
                "; ".join(f"{d.get('name')}: {'ok' if d.get('readable') else d.get('error')}" for d in obs["documents"]),
                "supporting")
        if docs:
            words = max(d.get("words") or 0 for d in docs)
            add("document_not_empty", f"The document has substantive content (≥{MIN_DOC_WORDS} words)",
                "pass" if words >= MIN_DOC_WORDS else "fail", f"{words} words", "supporting")
            wanted = [f for f, rx in _FORMATS.items() if re.search(rx, expect_text, re.I)]
            if wanted:
                got = {(d.get("format") or "").lower() for d in docs}
                add("document_format", f"The document is in the requested format ({', '.join(wanted)})",
                    "pass" if got & set(wanted) else "fail", f"got {', '.join(sorted(got)) or 'none'}")
            reflected = _input_reflected(b, " ".join(_full_doc_text(d, artifact_dir) for d in docs))
            if reflected:
                hit, total, missing = reflected
                add("input_reflected", "The document reflects what the test entered",
                    "pass" if hit / total >= 0.5 else "fail",
                    f"{hit}/{total} key terms from the input appear" + (f"; missing: {', '.join(missing[:6])}" if missing else ""),
                    "supporting")
    if kind == "reply":
        reply = obs.get("reply") or ""
        add("reply_present", "A reply appeared", "pass" if reply.strip() else "fail", f"{len(reply)} characters")
        if reply.strip():
            broken = _BROKEN_REPLY.search(reply)
            add("reply_not_error", "The reply is not an error or crash message", "fail" if broken else "pass",
                f"contains “{broken.group(0)}”" if broken else "no error markers", "supporting")
    if kind == "http_response":
        resp = obs.get("http_response") or {}
        st = resp.get("status")
        add("http_2xx", "The endpoint answered successfully (2xx)", "pass" if st and 200 <= st < 300 else "fail",
            f"HTTP {st}" if st else "no response")
    if kind == "ui_output" and not negative:
        changed = bool(obs.get("ui_output")) or bool(obs.get("messages"))
        add("page_changed", "The page responded to the actions", "pass" if changed else "fail",
            {"reordered": "content was re-ordered", "added": "new content appeared"}.get(obs.get("page_change") or "",
                                                                                         "a message appeared" if changed else "nothing changed"))
    if negative:
        msgs = [m for m in obs.get("messages") or [] if _ERROR_WORDS.search(m)]
        no_doc = kind == "document" and not obs.get("documents")
        add("rejected_visibly", "The app visibly rejected or flagged the input",
            "pass" if msgs else ("pass" if no_doc else "unknown"),
            f"message: “{msgs[0]}”" if msgs else ("no document was generated" if no_doc else "no rejection message seen; left to the judge"))
    server = [c for c in (b.get("observations") or {}).get("api_failures") or [] if (c.get("status") or 0) >= 500]
    if server:
        add("no_server_errors", "No server errors during the test", "fail",
            "; ".join(f"{c['method']} {c['path']} → {c['status']}" for c in server[:3]), "supporting")
    elif (b.get("observations") or {}).get("api_calls"):
        add("no_server_errors", "No server errors during the test", "pass", f"{b['observations']['api_calls']} API call(s), none 5xx", "supporting")
    if (b.get("observations") or {}).get("page_errors"):
        add("no_page_errors", "No uncaught JavaScript errors", "fail", b["observations"]["page_errors"][0][:200], "supporting")
    limit = _time_limit_ms(expect_text)
    if limit:
        measured = ((b.get("observations") or {}).get("slowest_call") or {}).get("ms") or b.get("duration_ms")
        source = "slowest API call" if ((b.get("observations") or {}).get("slowest_call") or {}).get("ms") else "whole test"
        if measured is not None:
            add("time_limit", f"Responds within the stated limit ({limit / 1000:g}s)", "pass" if measured <= limit else "fail",
                f"{source}: {measured / 1000:.1f}s")
    return checks


def _input_reflected(b: Dict[str, Any], doc_text: str):
    """Distinctive words the test itself entered (not filler data) that the output should carry over."""
    given = " ".join(i.get("value") or "" for i in b.get("inputs") or [] if not i.get("synthetic") and i.get("action") != "check")
    terms = sorted({w for w in re.findall(r"[a-z][a-z0-9-]{4,}", given.lower()) if w not in _STOP})
    if len(terms) < 3 or not doc_text:
        return None
    low = doc_text.lower()
    missing = [t for t in terms if t not in low]
    return len(terms) - len(missing), len(terms), missing


def _time_limit_ms(text: str) -> Optional[float]:
    m = _TIME_LIMIT.search(text or "")
    if not m:
        return None
    value, unit = float(m.group(1)), m.group(2).lower()
    return value if unit.startswith("ms") or unit.startswith("milli") else value * 60_000 if unit.startswith("min") else value * 1000


def _view_text(v: Dict[str, Any], artifact_dir: Path, n_views: int) -> str:
    """A result tab's text, sized so all tabs fit the judge's budget together."""
    budget = max(2_000, DOC_TEXT_FOR_JUDGE // max(1, n_views))
    if v.get("text_file") and artifact_dir:
        try:
            return (artifact_dir / v["text_file"]).read_text(encoding="utf-8")[:budget]
        except Exception:
            pass
    return (v.get("text_excerpt") or "")[:budget]


def _full_doc_text(d: Dict[str, Any], artifact_dir: Path) -> str:
    if d.get("text_file"):
        p = artifact_dir / d["text_file"]
        try:
            return p.read_text(encoding="utf-8")
        except Exception:
            pass
    return d.get("text_excerpt") or ""


# ── semantic oracle (LLM judge) ─────────────────────────────────────────────

def needs_judge(b: Dict[str, Any]) -> bool:
    if b["execution_status"] not in ("completed", "failed") or not b.get("scored"):
        return False
    o = b["observed"]
    return bool(o.get("reply") or o.get("ui_output") or o.get("page_text_excerpt") or o.get("documents") or o.get("views")
                or o.get("http_response"))


def observed_corpus(b: Dict[str, Any], artifact_dir: Path) -> Dict[str, Any]:
    """The observed output the judge sees and quotes are checked against."""
    o = b["observed"]
    docs = [{"name": d.get("name"), "format": d.get("format"), "words": d.get("words"), "headings": (d.get("headings") or [])[:40],
             "embedded_images": d.get("images"), "is_image": d.get("kind") == "image",
             "text": _full_doc_text(d, artifact_dir)[:DOC_TEXT_FOR_JUDGE]} for d in o.get("documents") or [] if d.get("readable")]
    return {"output_kind": b["completeness"].get("expected_output"), "reply": o.get("reply"),
            "page_output": o.get("ui_output") or (o.get("page_text_excerpt") if not o.get("reply") else None),
            "page_change": o.get("page_change"), "messages": o.get("messages") or [], "documents": docs,
            "result_views": [{"name": v.get("name"), "text": _view_text(v, artifact_dir, len(o.get("views") or []))}
                             for v in o.get("views") or []],
            "http_response": o.get("http_response"),
            "unreadable_documents": [d.get("name") for d in o.get("documents") or [] if not d.get("readable")],
            "execution": b["execution_status"] + (f" (stopped at step {b['failed_step']}: {b.get('error')})" if b.get("failed_step") else "")}


def judge_payload(b: Dict[str, Any], artifact_dir: Path) -> Dict[str, Any]:
    exp = (b.get("expectations") or [{}])[0]
    return {"bundle_id": b["bundle_id"], "test": b.get("title"), "variant": b.get("variant"),
            "criterion": b.get("criterion_statement"), "test_input": b.get("test_input"),
            "inputs_sent": [{"field": i.get("field"), "value": (i.get("value") or "")[:500]} for i in b.get("inputs") or []
                            if not i.get("synthetic")],
            "expected_behavior": b.get("expected_behavior") or exp.get("expectation"),
            "pass_criteria": exp.get("pass_criteria") or [], "observed": observed_corpus(b, artifact_dir)}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def ground_judgement(raw: Optional[Dict[str, Any]], b: Dict[str, Any], artifact_dir: Path) -> Optional[Dict[str, Any]]:
    """Keep the judge honest: a 'met' needs a verbatim quote that exists in the observed output."""
    if not raw:
        return None
    corpus = observed_corpus(b, artifact_dir)
    haystack = _norm(" \n ".join([corpus.get("reply") or "", corpus.get("page_output") or "", " ".join(corpus["messages"]),
                                  *[d["text"] + " " + " ".join(d["headings"]) for d in corpus["documents"]],
                                  *[v["text"] for v in corpus.get("result_views") or []],
                                  str((corpus.get("http_response") or {}).get("excerpt") or "")]))
    items, ungrounded = [], 0
    for c in raw.get("criteria_results") or []:
        result = c.get("result") if c.get("result") in ("met", "not_met", "cannot_tell") else "cannot_tell"
        quote = (c.get("quote") or "").strip()
        found = bool(quote) and _norm(quote)[:300] in haystack
        if result == "met" and not found:
            result, ungrounded = "cannot_tell", ungrounded + 1
        items.append({"criterion": str(c.get("criterion") or "")[:300], "result": result,
                      "quote": quote[:400] if found else None, "quote_verified": found,
                      **({"note": "quote not found in the output"} if quote and not found else {})})
    met = sum(1 for i in items if i["result"] == "met")
    not_met = sum(1 for i in items if i["result"] == "not_met")
    assessment = raw.get("assessment") if raw.get("assessment") in ("meets", "partially_meets", "does_not_meet", "cannot_tell") else "cannot_tell"
    if ungrounded and assessment == "meets":
        assessment = "partially_meets" if met else "cannot_tell"
    score = max(0, min(100, int(raw.get("score") or 0)))
    if items:  # the score may not claim more than the grounded criteria support
        score = min(score, round(100 * (met + 0.5 * (len(items) - met - not_met)) / len(items)))
    return {"oracle": "semantic", "assessment": assessment, "score": score, "reasoning": str(raw.get("reasoning") or "")[:1500],
            "criteria_results": items, "ungrounded_quotes": ungrounded}


# ── result ──────────────────────────────────────────────────────────────────

def assemble(b: Dict[str, Any], checks: List[Dict[str, Any]], judged: Optional[Dict[str, Any]],
             judge_error: Optional[str] = None) -> Dict[str, Any]:
    base = {k: b.get(k) for k in ("bundle_id", "test_id", "test_code", "criterion_code", "requirement_ref", "title",
                                  "variant", "kind", "scored")}
    if b["execution_status"] not in ("completed", "failed"):
        return {**base, "status": "not_validatable", "reason": b.get("error") or "not executed", "checks": [],
                "judge": None, "summary": f"Not validated: {b.get('error') or 'the test was not executed'}"}
    core_fail = [c for c in checks if c["weight"] == "core" and c["result"] == "fail"]
    sup_fail = [c for c in checks if c["weight"] == "supporting" and c["result"] == "fail"]
    parts = [f"{sum(1 for c in checks if c['result'] == 'pass')}/{len(checks)} deterministic checks passed"]
    if core_fail:
        parts.append("failed: " + "; ".join(c["name"].lower() for c in core_fail))
    if judged:
        parts.append(f"judge: {judged['assessment'].replace('_', ' ')} ({judged['score']})")
    elif judge_error:
        parts.append(f"judge unavailable ({judge_error})")
    return {**base, "status": "validated", "checks": checks, "judge": judged, "judge_error": judge_error,
            "core_failures": [c["id"] for c in core_fail], "supporting_failures": [c["id"] for c in sup_fail],
            "summary": "; ".join(parts)}
