"""
service.py — Phase 6.1 / 6.2: the triage steps that need more than the report — a health check and one re-run
for `environment`, a --repeat-each=3 re-run that separates `flaky` from a real failure, and an LLM verdict for what
is still `unknown` (the LLM must quote the evidence it relies on, or its answer is discarded).

Everything that touches the outside world is injected (rerun / health / llm), so this module is pure and testable:

    rerun(tests: [(spec_file, title)], repeat_each: int) -> {(spec_file, title): {"statuses": [...],
                                                                               "error": str, "annotations": [...]}}
    health() -> (ok: bool, detail: str)
    llm(item) -> {"verdict": str, "quotes": [str], "reason": str}
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

from tools.triage.triage import (DATA, ENVIRONMENT, FLAKY, LOCATOR, PRODUCT_DEFECT, UNKNOWN, classify, count)

Key = Tuple[str, str]
RerunFn = Callable[[List[Key], int], Dict[Key, Dict[str, Any]]]
HealthFn = Callable[[], Tuple[bool, str]]
LlmFn = Callable[[Dict[str, Any]], Dict[str, Any]]

REPEAT = 3
LLM_VERDICTS = (PRODUCT_DEFECT, LOCATOR, DATA, ENVIRONMENT)
_PASS = ("passed", "expected")


def _key(item: dict) -> Key:
    return (item["spec_file"], item["test_name"])


def refine(triage: Dict[str, Any], *, rerun: Optional[RerunFn] = None, health: Optional[HealthFn] = None,
           llm: Optional[LlmFn] = None, flaky_rerun: bool = True) -> Dict[str, Any]:
    """Mutates and returns `triage` (counts recomputed). Each step is skipped when its function is None."""
    items = triage.get("tests") or []

    # 1. environment: health check, then one re-run; a second failure is classified again on its own error.
    env = [it for it in items if it["verdict"] == ENVIRONMENT]
    if env and health is not None:
        ok, detail = health()
        if not ok:
            for it in env:
                it["evidence"].append(f"health check failed: {detail}")
        elif rerun is not None:
            again = rerun([_key(it) for it in env], 1)
            for it in env:
                r = again.get(_key(it))
                if r is None:
                    it["evidence"].append("health check ok; re-run produced no result")
                elif r["statuses"] and all(s in _PASS for s in r["statuses"]):
                    it["evidence"].append("health check ok; passed on one re-run — transient environment failure")
                    it["recovered"] = True
                else:
                    v = classify("failed", r.get("error", ""), r.get("annotations"))
                    if v["verdict"] != ENVIRONMENT:
                        it["verdict"] = v["verdict"]
                        it["evidence"] = [f"health check ok; re-run failed differently: {e}" for e in v["evidence"]]
                        it["error"] = (r.get("error") or "")[:500]
                    else:
                        it["evidence"].append("health check ok; still failing on re-run")

    # 2. flaky: re-run every remaining failure --repeat-each=3; any pass means it is not a consistent failure.
    if flaky_rerun and rerun is not None:
        cands = [it for it in items if it["verdict"] in (PRODUCT_DEFECT, LOCATOR, DATA, UNKNOWN)]
        if cands:
            again = rerun([_key(it) for it in cands], REPEAT)
            for it in cands:
                r = again.get(_key(it))
                if not r or not r["statuses"]:
                    continue
                passed = sum(1 for s in r["statuses"] if s in _PASS)
                if passed:
                    it["evidence"].insert(0, f"passed {passed}/{len(r['statuses'])} on a --repeat-each={REPEAT} "
                                             f"re-run (was {it['verdict']})")
                    it["verdict"] = FLAKY
                else:
                    it["evidence"].append(f"failed {len(r['statuses'])}/{len(r['statuses'])} on a "
                                          f"--repeat-each={REPEAT} re-run — consistent")

    # 3. what is still unknown: ask the LLM, keep the answer only when it quotes real evidence.
    if llm is not None:
        for it in [i for i in items if i["verdict"] == UNKNOWN]:
            try:
                ans = llm(it) or {}
            except Exception as exc:          # never fatal: the item stays unknown
                it["evidence"].append(f"LLM triage unavailable: {type(exc).__name__}")
                continue
            ok, why = validate_llm_answer(ans, it)
            if ok:
                it["verdict"] = ans["verdict"]
                it["evidence"].append(f"LLM verdict (cites: {ans['quotes'][:3]}): {str(ans.get('reason', ''))[:200]}")
                it["llm"] = True
            else:
                it["evidence"].append(f"LLM answer rejected: {why}")

    triage["counts"] = count(items)
    return triage


def validate_llm_answer(ans: Dict[str, Any], item: Dict[str, Any]) -> Tuple[bool, str]:
    if ans.get("verdict") not in LLM_VERDICTS:
        return False, f"verdict {ans.get('verdict')!r} not one of {list(LLM_VERDICTS)}"
    quotes = [q for q in ans.get("quotes") or [] if isinstance(q, str) and q.strip()]
    if not quotes:
        return False, "no evidence quoted"
    haystack = " ".join([item.get("error") or ""] + [str(e) for e in item.get("evidence") or []])
    missing = [q for q in quotes if q.strip() not in haystack]
    if missing:
        return False, f"quoted text not in the evidence: {missing[:2]}"
    return True, ""


def make_llm(registry, prompt: str, mode: Optional[str] = None) -> LlmFn:
    """An LlmFn over a ConnectorRegistry LLM (one call per unknown failure). `prompt` has {test} and {error}."""
    def _call(item: Dict[str, Any]) -> Dict[str, Any]:
        raw = registry.get_llm(mode).generate(prompt.format(test=item.get("test_name", ""),
                                                           error=(item.get("error") or "")[:2000]))
        m = re.search(r"\{.*\}", raw or "", re.S)
        return json.loads(m.group(0)) if m else {}
    return _call


def http_health(url: str, timeout: float = 10.0) -> HealthFn:
    """Reachable = any HTTP answer below 500 from the project's own base URL (its configured target)."""
    def _check() -> Tuple[bool, str]:
        if not url:
            return False, "no base URL configured"
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:      # noqa: S310 — the project's own app
                return resp.status < 500, f"{url} -> {resp.status}"
        except urllib.error.HTTPError as exc:
            return exc.code < 500, f"{url} -> {exc.code}"
        except Exception as exc:
            return False, f"{url} unreachable: {type(exc).__name__}: {str(exc)[:120]}"
    return _check


def statuses_from_report(report: Dict[str, Any]) -> Dict[Key, Dict[str, Any]]:
    """{(spec_file, title): {"statuses", "error", "annotations"}} from a Playwright JSON report (one entry per
    project and per --repeat-each run)."""
    from tools.triage.triage import _iter_suites, _spec_key
    out: Dict[Key, Dict[str, Any]] = {}
    for suite in _iter_suites(report.get("suites", [])):
        for spec in suite.get("specs", []):
            key = (_spec_key(spec.get("file", "")), spec.get("title", ""))
            slot = out.setdefault(key, {"statuses": [], "error": "", "annotations": []})
            for t in spec.get("tests", []):
                slot["statuses"].append(t.get("status", ""))
                for r in t.get("results", []):
                    slot["annotations"] += r.get("annotations") or []
                    e = r.get("error") or {}
                    if not slot["error"] and (e.get("message") or e.get("value")):
                        slot["error"] = e.get("message") or e.get("value")
    return out


def grep_for_titles(titles: List[str]) -> str:
    """A --grep pattern matching exactly these test titles."""
    return "|".join(re.escape(t) for t in dict.fromkeys(titles))


def make_rerun(project_name: str, settings: Optional[dict] = None) -> RerunFn:
    """A RerunFn over UIExecutionAgent: only the given specs (keys relative to test_scripts/), only the given
    titles (--grep), N times each."""
    import os

    def _rerun(tests: List[Key], repeat_each: int) -> Dict[Key, Dict[str, Any]]:
        from agents.test_execution.ui_execution.agent import UIExecutionAgent
        if not tests:
            return {}
        specs = sorted({sf for sf, _ in tests})
        request = {"project_name": project_name, "spec_files": specs, "headless": True,
                   "grep": grep_for_titles([t for _, t in tests])}
        if repeat_each > 1:
            request["repeat_each"] = repeat_each
        out = UIExecutionAgent(settings=settings or {}).execute(request, {})
        path = out.get("report_json")
        if not path or not os.path.isfile(path):
            return {}
        with open(path, encoding="utf-8") as fh:
            report = json.load(fh)
        wanted = set(tests)
        return {k: v for k, v in statuses_from_report(report).items() if k in wanted}
    return _rerun
