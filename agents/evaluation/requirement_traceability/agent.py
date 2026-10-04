"""
RequirementTraceabilityAgent — one evidence-backed, code-only verdict per acceptance criterion.

Static only: it runs in parallel with the browser execution, so it never reads execution results. Runtime evidence
is merged later by brd_compliance through tools.apply_runtime_evidence(static_trace, …), which re-decides each
criterion from the `static_trace` this agent returns.

For every criterion:
  1. query expansion (batched: one LLM call per group of requirements, all their criteria at once);
  2. hybrid retrieval over the Repository Intelligence snapshot (BM25 + graph seeds + expansion);
  3. verifier sample A (temperature 0.2); a follow-up pass with the code A said it was missing; sample B
     (temperature 0.7, chunks shuffled) runs concurrently with that follow-up — or is skipped when A is decisive
     (see SKIP RULE below);
  4. deterministic citation validation against the checkout — uncited claims earn nothing;
  5. wiring proof through the graph (E3) vs. isolated code (E2);
  6. absence protocol: `not_implemented` only with a concrete negative search over an index that covers where the
     code would live (engines/trace/absence.py), else insufficient_evidence with the reason;
  7. a verifier that could not answer (LLM error) yields `llm_unavailable` (flag `llm_failed`), counted in
     `llm_failures`, never a silent insufficient_evidence; the step is then `partial`.
Criteria of all requirements run in one pool; one criterion's exception never fails the others.

SKIP RULE — sample B is not run when sample A, after deterministic validation, is decisive:
  (W) status implemented/partial, ≥1 validated citation, none rejected, cited code wired to an entry point, and
      the verifier reports confidence "high"; or
  (C) status implemented, ≥2 validated citations, none rejected, confidence not "low", nothing in need_more.
  B is a robustness check against a lucky or sloppy first answer; when the citations are verified line-by-line
  and (W) reachable from an entry point or (C) multiply corroborated, B can only lower agreement, not the verdict
  class, so its cost is not worth paying. Absence (`not_implemented`) and unsure verdicts always get sample B.
"""

import json
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agents.base_agent import BaseAgent
from agents.evaluation.requirement_traceability.prompt import (
    PREAMBLE,
    QUERY_EXPANSION_PROMPT,
    QUERY_TERMS_SCHEMA,
    VERIFIER_PROMPT,
    VERIFIER_SCHEMA,
)
from agents.evaluation.requirement_traceability.tools import (
    MIN_HITS_FOR_ABSENCE,  # noqa: F401  (re-exported for callers that tuned it)
    STATIC_TRACE_VERSION,
    CodeIndex,
    FileCache,
    absence_check,
    assemble,
    fence_untrusted,
    generate_json,
    is_wired,
    nodes_at,
    runtime_evidence,
    tokenize,
    validate_citation,
)
from connectors.connector_registry import ConnectorRegistry
from tools.shared import get_logger

WORKERS = 6
TOP_K = 12
MAX_CHUNK_LINES = 120
TEMPERATURE_A = 0.2
TEMPERATURE_B = 0.7
EXPANSION_BATCH_CRITERIA = 24

# Backward-compatible name (tests and older callers import it from here).
_runtime_evidence = runtime_evidence


class RequirementTraceabilityAgent(BaseAgent):
    MODULE_NAME = "requirement_traceability"

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self._registry = ConnectorRegistry(self.settings)
        self.logger = get_logger("agent.requirement_traceability")

    def execute(self, request: dict, state: dict) -> Dict[str, Any]:
        emit = request.get("emit") or (lambda *a, **k: None)
        requirements: List[dict] = request.get("requirements") or []
        graph, chunks = request.get("repo_graph"), request.get("code_chunks") or []
        if graph is None or not chunks:
            return {"module": self.MODULE_NAME, "status": "failed", "blocking": True,
                    "error": "No repository index available for traceability."}
        llm = request.get("llm") or self._registry.get_llm(request.get("connector_mode"))
        index = CodeIndex(graph, chunks)
        files = FileCache(Path(request["repo_dir"]))
        repo, sha = request.get("repo_full_name"), request.get("commit_sha")
        coverage = {"index": (request.get("repo_model") or {}).get("coverage") or {},
                    "repo": request.get("repo_coverage") or {}}
        vocab = _vocabulary(graph)

        n_criteria = sum(len(r.get("criteria") or []) for r in requirements)
        emit(f"Tracing {n_criteria} acceptance criteria across {len(requirements)} requirements "
             f"(retrieval over {len(index.chunks)} code chunks, up to 2 verifier samples each).")

        with ThreadPoolExecutor(max_workers=WORKERS) as pool, ThreadPoolExecutor(max_workers=WORKERS) as samples:
            terms, expansion_failed = self._expand_all(llm, requirements, vocab, pool)
            if expansion_failed:
                emit(f"Query expansion failed for {expansion_failed} criteria; their search uses the criterion "
                     "wording only.", "warning")
            jobs = [(req, c) for req in requirements for c in req.get("criteria") or []]
            futures = [pool.submit(self._trace_safe, llm, req, c, terms.get(c["code"], []), index, files, graph,
                                   repo, sha, coverage, samples) for req, c in jobs]
            entries = [f.result() for f in futures]

        llm_failures = sum(1 for e in entries if e.get("llm_failed"))
        static_trace = {"version": STATIC_TRACE_VERSION, "repo_full_name": repo, "commit_sha": sha,
                        "llm_failures": llm_failures, "criteria": entries}
        out = assemble(static_trace, requirements, {})

        for r in out["traced_requirements"]:
            verdict = r["verdict"]
            emit(f"{r['code']} {str(r.get('title') or '')[:60]} → {verdict}"
                 + (f" ({r['score']:.2f})" if r["score"] is not None else "")
                 + (f", {r['llm_unavailable']} criteria not evaluated (LLM unavailable)" if r.get("llm_unavailable") else ""),
                 "success" if verdict in ("verified", "implemented") else "warning"
                 if verdict in ("partial", "insufficient_evidence", "llm_unavailable") else "error")
        counts: Dict[str, int] = {}
        for v in out["criterion_verdicts"]:
            counts[v["verdict"]] = counts.get(v["verdict"], 0) + 1
        skipped_b = sum(1 for e in entries if str(e.get("sample_b") or "").startswith("skipped"))
        emit("Criteria: " + ", ".join(f"{k.replace('_', ' ')} {n}" for k, n in sorted(counts.items()))
             + (f" · second sample skipped for {skipped_b} decisive criteria" if skipped_b else ""), "success")

        result = {"module": self.MODULE_NAME, "status": "success", **out, "static_trace": static_trace,
                  "llm_failures": llm_failures}
        if llm_failures:
            errors = sorted({str(e.get("llm_error") or "")[:160] for e in entries if e.get("llm_failed")})
            msg = (f"{llm_failures} of {n_criteria} criteria could not be evaluated because the LLM verifier failed "
                   f"({'; '.join(errors[:3])}); they are marked llm_unavailable and excluded from the score.")
            emit(msg, "error")
            result.update(status="partial", error=msg)
        return result

    # ── 1. query expansion (batched) ─────────────────────────────────────────

    def _expand_all(self, llm, requirements: List[dict], vocab: str, pool) -> Tuple[Dict[str, List[str]], int]:
        batches: List[List[dict]] = []
        size = 0
        for req in requirements:
            n = len(req.get("criteria") or [])
            if not n:
                continue
            if batches and size + n <= EXPANSION_BATCH_CRITERIA:
                batches[-1].append(req)
                size += n
            else:
                batches.append([req])
                size = n
        got: Dict[str, List[str]] = {}
        failed = 0
        for batch, res in zip(batches, pool.map(lambda b: self._expand(llm, b, vocab), batches)):
            if res is None:
                failed += sum(len(r.get("criteria") or []) for r in batch)
            else:
                got.update(res)
        out: Dict[str, List[str]] = {}
        for req in requirements:
            base = tokenize(f"{req['title']} {req.get('description', '')}")
            for c in req.get("criteria") or []:
                out[c["code"]] = got.get(c["code"].upper(), []) + tokenize(c["statement"]) + base
        return out, failed

    def _expand(self, llm, batch: List[dict], vocab: str) -> Optional[Dict[str, List[str]]]:
        text = "\n\n".join(
            f"### {r['code']} {r['title']}: {r.get('description', '')}\n"
            + "\n".join(f"- {c['code']}: {c['statement']}" for c in r.get("criteria") or []) for r in batch)
        try:
            out = generate_json(llm, QUERY_EXPANSION_PROMPT.substitute(
                preamble=PREAMBLE, vocabulary=fence_untrusted("repository", vocab),
                requirements=fence_untrusted("brd", text)),
                required_keys=["criteria"], schema=QUERY_TERMS_SCHEMA, temperature=TEMPERATURE_A)
            return {str(x.get("code")).upper(): [str(t) for t in x.get("terms") or []][:15]
                    for x in out["criteria"] if isinstance(x, dict)}
        except Exception as exc:
            self.logger.warning(f"query expansion failed: {exc}")
            return None

    # ── 2-7. one criterion ───────────────────────────────────────────────────

    def _trace_safe(self, llm, req, c, terms, index, files, graph, repo, sha, coverage, samples) -> Dict:
        try:
            return self._trace(llm, req, c, terms, index, files, graph, repo, sha, coverage, samples)
        except Exception as exc:  # one criterion's failure never kills the step
            self.logger.warning(f"tracing {c.get('code')} failed: {exc}")
            entry = _entry(req, c)
            entry.update(llm_failed=True, llm_error=f"tracing failed: {type(exc).__name__}: {str(exc)[:200]}",
                         static_a={"llm_failed": True, "llm_error": f"tracing failed: {type(exc).__name__}"})
            return entry

    def _trace(self, llm, req, c, terms, index: CodeIndex, files: FileCache, graph, repo, sha, coverage, samples) -> Dict:
        entry = _entry(req, c)
        # Code only: README/docs are claims (E1), and in the verifier's context they crowd out the code
        hits = [h for h in index.search(terms, k=TOP_K + 8) if not _is_doc(h[0].file_path)][:TOP_K]
        entry["negative_search"] = {"terms": terms[:25], "candidates": len(hits),
                                    "top_files": sorted({h[0].file_path for h in hits})[:8]}
        if req.get("verifiability") == "non_technical":
            return entry
        if not hits:
            entry["static_a"] = {"status": "insufficient_evidence", "rationale": "Retrieval found no candidate code.",
                                 "valid_citations": 0, "wired": None, "negative_search_ok": False}
            entry["sample_b"] = "not run: no candidate code"
            return entry

        prompt = lambda hs: VERIFIER_PROMPT.substitute(  # noqa: E731
            preamble=PREAMBLE, req_code=req["code"], req_kind=req.get("kind", "functional"),
            verifiability=req.get("verifiability", "both"),
            req_text=fence_untrusted("brd", f"{req['title']}: {req.get('description', '')}"), crit_code=c["code"],
            criterion=fence_untrusted("brd", c["statement"]),
            paths=fence_untrusted("repository", "\n".join(index.paths_for(hs)
                                                          or ["(no route wiring found for these files)"])),
            code=fence_untrusted("repository", _render(hs)))

        def shuffled(hs):
            out = list(hs)
            random.Random(c["code"]).shuffle(out)
            return out

        raw_a, err_a = self._verify(llm, prompt(hits), TEMPERATURE_A)
        follow = (raw_a or {}).get("need_more") or _named_in(str((raw_a or {}).get("rationale") or ""))
        extra = []
        if raw_a and raw_a.get("status") in ("insufficient_evidence", "partial") and follow:
            known = {(h[0].file_path, h[0].start_line) for h in hits}
            extra = [h for h in index.lookup(follow) if (h[0].file_path, h[0].start_line) not in known]
        check = lambda raw, ev: self._check(raw, files, graph, len(hits), repo, sha, ev, terms, coverage)  # noqa: E731

        raw_b, err_b = None, None
        if extra:  # follow-up retrieval: the code A said was missing; B runs concurrently on the same context
            hits = extra + hits[:TOP_K - min(len(extra), 6)]
            fut_a = samples.submit(self._verify, llm, prompt(hits), TEMPERATURE_A)
            fut_b = samples.submit(self._verify, llm, prompt(shuffled(hits)), TEMPERATURE_B)
            (raw_a2, _), (raw_b, err_b) = fut_a.result(), fut_b.result()
            raw_a = raw_a2 or raw_a
            entry["sample_b"] = "ran" if raw_b else f"failed: {err_b}"
        else:
            skip = _skip_reason(raw_a, check(raw_a, [])) if raw_a else None
            if skip:
                entry["sample_b"] = f"skipped: {skip}"
            else:
                raw_b, err_b = self._verify(llm, prompt(shuffled(hits)), TEMPERATURE_B)
                entry["sample_b"] = "ran" if raw_b else f"failed: {err_b}"

        ev_a: List[dict] = []
        static_a = check(raw_a, ev_a) if raw_a else None
        static_b = check(raw_b, []) if raw_b else None
        if static_a is None and static_b is not None:  # A failed: B is the only sample, and the primary one
            ev_b: List[dict] = []
            static_a, static_b, ev_a = check(raw_b, ev_b), None, ev_b
            entry["sample_b"] = f"used as the only sample (sample A failed: {err_a})"
        if static_a is None:
            err = err_a or err_b or "no verifier answer"
            entry.update(llm_failed=True, llm_error=f"LLM verifier unavailable: {err}",
                         static_a={"llm_failed": True, "llm_error": f"LLM verifier unavailable: {err}"})
            return entry
        entry.update(static_a=static_a, static_b=static_b, static_evidence=ev_a,
                     samples=1 + (1 if static_b else 0))
        entry["negative_search"]["candidates"] = len(hits)
        return entry

    def _verify(self, llm, prompt: str, temperature: Optional[float]) -> Tuple[Optional[dict], Optional[str]]:
        try:
            raw = generate_json(llm, prompt, required_keys=["status"], schema=VERIFIER_SCHEMA, temperature=temperature)
            if not isinstance(raw, dict) or raw.get("status") not in ("implemented", "partial", "not_implemented",
                                                                       "insufficient_evidence"):
                return None, f"invalid verifier status {str((raw or {}).get('status'))[:40]!r}"
            return raw, None
        except Exception as exc:
            self.logger.warning(f"verifier call failed: {exc}")
            return None, f"{type(exc).__name__}: {str(exc)[:200]}"

    def _check(self, raw, files, graph, n_hits, repo, sha, evidence_out, terms, coverage) -> Optional[dict]:
        if not raw:
            return None
        valid, invalid, wired_by = [], 0, None
        for cit in raw.get("citations") or []:
            ok, why = validate_citation(cit, files, graph=graph)
            evidence_out.append({
                "method": "static", "strength": "E2" if ok else "E1",
                "outcome": "supports" if raw["status"] in ("implemented", "partial") else "neutral",
                "citation": {**cit, "url": _github_url(repo, sha, cit) if ok else None, "check": why},
                "summary": str(cit.get("claim") or "")[:1000], "validated": ok})
            if ok:
                valid.append(cit)
                if not wired_by:
                    keys = nodes_at(graph, str(cit["file"]).lstrip("./"), int(cit["start_line"]),
                                    int(cit.get("end_line") or cit["start_line"]))
                    wired_by = is_wired(graph, keys)
            else:
                invalid += 1
        if wired_by:
            for e in evidence_out:
                if e["validated"] and e["method"] == "static":
                    e["strength"], e["method"] = "E3", "structural"
                    e["summary"] = f"{e['summary']} (reachable from {wired_by})"
        absence_ok, absence_reason = (False, None)
        if raw["status"] == "not_implemented":
            absence_ok, absence_reason = absence_check(n_hits, raw.get("looked_for") or [], terms,
                                                       coverage.get("index"), coverage.get("repo"))
        return {"status": raw["status"], "rationale": raw.get("rationale"), "valid_citations": len(valid),
                "invalid_citations": invalid, "wired": wired_by, "negative_search_ok": absence_ok,
                "absence_reason": absence_reason, "confidence": raw.get("confidence"),
                "need_more": list(raw.get("need_more") or [])[:6]}


def _entry(req: dict, c: dict) -> Dict:
    return {"code": c["code"], "criterion_id": c.get("id"), "requirement_code": req["code"],
            "static_a": None, "static_b": None, "samples": 0, "sample_b": None,
            "negative_search": {"terms": [], "candidates": 0, "top_files": []}, "static_evidence": [],
            "llm_failed": False, "llm_error": None}


def _skip_reason(raw: dict, checked: Optional[dict]) -> Optional[str]:
    """The SKIP RULE (module docstring): why sample B is unnecessary, or None."""
    if not checked or checked["invalid_citations"]:
        return None
    status, conf = checked["status"], checked.get("confidence")
    if status in ("implemented", "partial") and checked["valid_citations"] >= 1 and checked["wired"] and conf == "high":
        return "validated citations wired to an entry point, high confidence"
    if status == "implemented" and checked["valid_citations"] >= 2 and conf != "low" and not checked.get("need_more"):
        return "clear verdict with every citation validated"
    return None


_DOC_SUFFIXES = (".md", ".mdx", ".rst", ".txt")


def _is_doc(path: str) -> bool:
    return path.lower().endswith(_DOC_SUFFIXES)


def _named_in(text: str) -> List[str]:
    """Identifiers a verifier's rationale says it could not see: `code spans`, dotted.names, snake_case, CamelCase."""
    import re
    names = re.findall(r"`([^`]{3,80})`", text)
    names += re.findall(r"\b[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]+\b", text)
    names += re.findall(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b", text)
    names += re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z0-9]+)+\b", text)
    return list(dict.fromkeys(n for n in names if "/" not in n or n.endswith((".py", ".ts", ".tsx"))))[:8]


def _render(hits) -> str:
    blocks = []
    for chunk, _, why in hits:
        lines = chunk.content.splitlines()[:MAX_CHUNK_LINES]
        numbered = "\n".join(f"{chunk.start_line + i:>5}  {l}" for i, l in enumerate(lines))
        blocks.append(f"===== {chunk.file_path}:{chunk.start_line}-{chunk.start_line + len(lines) - 1}"
                      f"{' (' + chunk.symbol + ')' if chunk.symbol else ''} [{why}] =====\n{numbered}")
    return "\n\n".join(blocks)


def _vocabulary(graph) -> str:
    routes = sorted({n.name for n in graph.of_kind("route")})[:40]
    pages = sorted({n.name for n in graph.of_kind("page")})[:20]
    agents = sorted({n.name for n in graph.of_kind("agent")})[:20]
    return json.dumps({"routes": routes, "pages": pages, "agents": agents}, ensure_ascii=False)


def _github_url(repo, sha, cit) -> Optional[str]:
    if not repo or not sha:
        return None
    return f"https://github.com/{repo}/blob/{sha}/{str(cit['file']).lstrip('./')}#L{cit['start_line']}-L{cit.get('end_line') or cit['start_line']}"
