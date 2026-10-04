"""tools.py — tool surface for RequirementTraceabilityAgent (re-exported from engines/ and tools/agent_eval/), plus
the deterministic second half of traceability that brd_compliance runs after Pass/Fail:

    merged = apply_runtime_evidence(static_trace, requirements, test_cases, execution_results)
    # → {"criterion_verdicts": [...], "evidence_items": [...], "traced_requirements": [...]}

`static_trace` is what RequirementTraceabilityAgent returns (JSON-serialisable):

    {
      "version": "static-trace-1",
      "repo_full_name": str | None, "commit_sha": str | None,
      "llm_failures": int,
      "criteria": [{
          "code": "AC-01.1", "criterion_id": str | None, "requirement_code": "REQ-01",
          "static_a": {status, rationale, valid_citations, invalid_citations, wired, negative_search_ok,
                       absence_reason, confidence} | {"llm_failed": true, "llm_error": str} | None,
          "static_b": same shape | None,          # None when skipped or failed
          "samples": int,                          # verifier samples that produced a result (0-2)
          "sample_b": "ran" | "skipped: <rule>" | "failed: <error>" | "not run: <why>",
          "negative_search": {terms, candidates, top_files},
          "static_evidence": [evidence rows of the primary sample, without criterion_id],
          "llm_failed": bool, "llm_error": str | None,
      }, ...]
    }

Both the static agent (no runtime evidence) and apply_runtime_evidence go through `assemble()`, so static +
apply_runtime_evidence is exactly what a single combined pass would have produced. Pure, deterministic, no LLM,
never mutates its inputs.
"""

import copy
from typing import Dict, List, Optional

from engines.trace.absence import MIN_HITS_FOR_ABSENCE, absence_check, concrete_looked_for  # noqa: F401
from engines.trace.citations import FileCache, is_wired, nodes_at, validate_citation  # noqa: F401
from engines.trace.decide import LLM_UNAVAILABLE, decide, roll_up  # noqa: F401
from engines.trace.retrieve import CodeIndex, tokenize  # noqa: F401
from tools.agent_eval.llm_json import generate_json  # noqa: F401
from tools.agent_eval.untrusted import UNTRUSTED_RULE, fence_untrusted  # noqa: F401

STATIC_TRACE_VERSION = "static-trace-1"


def runtime_evidence(tests: List[dict], results: List[dict]) -> Dict[str, List[dict]]:
    """Executed tests become runtime evidence for the criterion they were generated for.

    Strength comes from the Pass/Fail Engine (E5 when deterministic checks decided, E4 when the judge did);
    results from the legacy live execution carry none and count as judged (E4).
    """
    by_id = {r.get("id"): r for r in results}
    out: Dict[str, List[dict]] = {}
    for t in tests:
        code, res = t.get("criterion_code"), by_id.get(t.get("id"))
        if not code or not res or res.get("status") not in ("passed", "failed") or res.get("transport_error"):
            continue
        out.setdefault(code, []).append({
            "strength": res.get("strength") or "E4", "outcome": "supports" if res["status"] == "passed" else "refutes",
            "test_case_id": t.get("id"), "validated": True,
            # runtime proof: screenshot / documents in the run's artifact folder (served by execution-files)
            "citation": {"kind": "runtime", **res["artifacts"]} if res.get("artifacts") else None,
            "summary": f"{t.get('code')} {res['status']} on the live app "
                       f"({'deterministic checks' if res.get('decided_by') == 'deterministic' else 'judge'} "
                       f"{res.get('judge_score')}): "
                       f"{str(res.get('judge_reasoning') or '')[:400]}"})
    return out


def assemble(static_trace: Dict, requirements: List[dict], runtime: Dict[str, List[dict]]) -> Dict[str, List[dict]]:
    """Decide every criterion from its static trace entry plus runtime evidence, roll requirements up."""
    entries = {e["code"]: e for e in (static_trace or {}).get("criteria") or []}
    criterion_verdicts: List[dict] = []
    evidence_items: List[dict] = []
    traced: List[dict] = []
    for req in requirements or []:
        req = copy.deepcopy(req)
        pairs = []
        for c in req.get("criteria") or []:
            e = entries.get(c["code"]) or {}
            rt = copy.deepcopy(runtime.get(c["code"], []))
            v = decide(c, req, copy.deepcopy(e.get("static_a")), copy.deepcopy(e.get("static_b")), rt)
            v["negative_search"] = copy.deepcopy(e.get("negative_search")
                                                 or {"terms": [], "candidates": 0, "top_files": []})
            v["samples"] = e.get("samples", 0)
            if e.get("sample_b"):
                v["sample_b"] = e["sample_b"]
            if v.get("static_verdict") == LLM_UNAVAILABLE:
                v["llm_error"] = e.get("llm_error")
            pairs.append((c, v))
            cid = c.get("id") or e.get("criterion_id")
            criterion_verdicts.append({**v, "code": c["code"], "criterion_id": cid, "requirement_code": req["code"]})
            evidence = copy.deepcopy(e.get("static_evidence") or []) + [{"method": "runtime", **x} for x in rt]
            evidence_items += [{**x, "criterion_id": cid} for x in evidence]
        rolled = roll_up(req, pairs)
        req.update({"verdict": rolled["verdict"], "score": rolled["score"], "status": rolled["legacy_status"],
                    "llm_unavailable": rolled.get("llm_unavailable", 0)})
        traced.append(req)
    return {"criterion_verdicts": criterion_verdicts, "evidence_items": evidence_items, "traced_requirements": traced}


def apply_runtime_evidence(static_trace: Dict, requirements: List[dict], test_cases: Optional[List[dict]],
                           execution_results: Optional[List[dict]]) -> Dict[str, List[dict]]:
    """Re-decide every criterion of a static trace with the runtime evidence from executed tests (runtime refutation
    beats everything, then runtime support, else the static verdict). Pure and deterministic; inputs are not mutated.

    Returns {"criterion_verdicts", "evidence_items", "traced_requirements"} — the same shapes the static agent
    returns, and exactly what a single pass with runtime evidence would have produced."""
    return assemble(static_trace, requirements, runtime_evidence(test_cases or [], execution_results or []))
