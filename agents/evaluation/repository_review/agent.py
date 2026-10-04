"""
RepositoryReviewAgent — findings about how the application is built (not whether it meets the BRD).

  1. deterministic rules (engines/review/rules.py), over every indexed language: secrets, committed env files,
     CORS wildcard, debug mode, state-changing routes without real authentication constructs, LLM calls without
     retry/timeout, missing tests (Python, JS/TS and other test nodes or test files) / health check / README,
     unpinned dependencies;
  2. one LLM review of design, architecture, workflow and security, fed the agents, prompts, LLM call sites and
     route handlers from the knowledge graph plus the app profile's `observed_risks` as hints to confirm. All of it
     is fenced as untrusted content. Each LLM finding's file and line are validated against the checkout; a
     finding that cannot be placed is kept with `verified: false` (severity capped at medium) and does not
     penalise the scorecard.
Findings are sorted by severity (verified first) before the LLM cap is applied. They feed the Quality Scorecard
and gates — never the compliance number.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agents.base_agent import BaseAgent
from agents.evaluation.repository_review.prompt import MAX_LLM_FINDINGS, REVIEW_PROMPT
from agents.evaluation.repository_review.tools import (
    FileCache,
    fence_untrusted,
    generate_json,
    rule_findings,
    scorecard,
    sort_findings,
)
from connectors.connector_registry import ConnectorRegistry
from tools.agent_eval.schemas import REVIEW_FINDINGS
from tools.shared import get_logger

CODE_BUDGET = 60_000
_FOCUS_KINDS = ("agent", "prompt", "model_call", "route", "form")


class RepositoryReviewAgent(BaseAgent):
    MODULE_NAME = "repository_review"

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self._registry = ConnectorRegistry(self.settings)
        self.logger = get_logger("agent.repository_review")

    def execute(self, request: dict, state: dict) -> Dict[str, Any]:
        emit = request.get("emit") or (lambda *a, **k: None)
        graph, chunks = request.get("repo_graph"), request.get("code_chunks") or []
        if graph is None:
            return {"module": self.MODULE_NAME, "status": "partial", "error": "no repository index",
                    "findings": [], "scorecard": None}
        all_paths = request.get("repo_tree") or sorted({c.file_path for c in chunks})
        findings = rule_findings(graph, chunks, all_paths)
        emit(f"Scanners: {len(findings)} finding(s) "
             f"({sum(f['severity'] in ('critical', 'high') for f in findings)} critical/high).")

        llm_findings, error = self._llm_review(request, graph, chunks, findings)
        findings = sort_findings(findings + llm_findings)
        card = scorecard(findings)
        unverified = sum(1 for f in llm_findings if f.get("verified") is False)
        emit(f"Design review: {len(llm_findings)} more finding(s)"
             + (f" ({unverified} could not be located in the code and are marked unverified)" if unverified else "")
             + ". Scorecard: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in card.items()),
             "warning" if any(f["severity"] == "critical" and f.get("verified", True) for f in findings) else "success")
        return {"module": self.MODULE_NAME, "status": "partial" if error else "success",
                **({"error": error} if error else {}), "findings": findings, "scorecard": card}

    def _llm_review(self, request, graph, chunks, scanner) -> Tuple[List[Dict], Optional[str]]:
        focus_files = {n.file_path for n in graph.nodes.values() if n.kind in _FOCUS_KINDS and n.file_path}
        picked, used = [], 0
        for c in sorted(chunks, key=lambda c: (c.file_path not in focus_files, c.file_path, c.start_line)):
            block = "\n".join(f"{c.start_line + i:>5}  {l}" for i, l in enumerate(c.content.splitlines()))
            block = f"===== {c.file_path}:{c.start_line} =====\n{block}\n"
            if used + len(block) > CODE_BUDGET:
                continue
            picked.append(block)
            used += len(block)
        model = request.get("repo_model") or {}
        summary = json.dumps({"routes": model.get("routes", [])[:30], "pages": model.get("pages", [])[:20],
                              "agents": [n.name for n in graph.of_kind("agent")][:20],
                              "prompts": [n.name for n in graph.of_kind("prompt")][:20], "models": model.get("models"),
                              "counts": model.get("counts")}, ensure_ascii=False)
        risks = [str(r)[:300] for r in ((request.get("agent_profile") or {}).get("observed_risks") or [])][:15]
        prompt = REVIEW_PROMPT.substitute(
            summary=fence_untrusted("repository", summary),
            code=fence_untrusted("repository", "\n".join(picked) or "(no code)"),
            scanner_findings=fence_untrusted("repository", "\n".join(f"- {f['rule_id']}: {f['title']}" for f in scanner)
                                             or "(none)"),
            observed_risks=fence_untrusted("app_profile", "\n".join(f"- {r}" for r in risks) or "(none)"))
        try:
            raw = generate_json(self._registry.get_llm(request.get("connector_mode")), prompt,
                                required_keys=["findings"], schema=REVIEW_FINDINGS)
        except Exception as exc:
            return [], f"LLM design review failed: {exc}"
        files = FileCache(Path(request["repo_dir"]))
        out = []
        for f in raw.get("findings") or []:
            if not isinstance(f, dict):
                continue
            lines = files.lines(str(f.get("file") or ""))
            try:
                line = int(f.get("start_line") or 0)
            except (TypeError, ValueError):
                line = 0
            located = lines is not None and 1 <= line <= len(lines)
            severity = f.get("severity", "low")
            if not located and severity in ("critical", "high"):
                severity = "medium"
            out.append({**f, "severity": severity, "source": "llm", "rule_id": f"llm/{f.get('dimension')}",
                        "confidence": 0.8 if located else 0.4, "verified": located,
                        "file": f.get("file") if located else None, "start_line": line if located else None,
                        "end_line": f.get("end_line") if located else None})
        return sort_findings(out)[:MAX_LLM_FINDINGS], None
