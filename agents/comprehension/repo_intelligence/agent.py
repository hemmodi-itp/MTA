"""
RepositoryIntelligenceAgent — indexes the fetched repo into a knowledge graph + code chunks.

Deterministic (no LLM): engines/repo_intel parses routes, handlers, pages, forms, frontend
API calls, LLM calls, prompts, agents, config, tests and dependencies in every fetched source
language, links them across files, and persists the snapshot in Postgres keyed by (repo, commit,
indexer version) so a re-run on the same commit is a cache hit. Without a commit SHA nothing is
cached. Traceability searches and walks this snapshot; repo_model["coverage"] says what was indexed
and what was not (it gates traceability's `not_implemented` verdicts).
"""

from pathlib import Path
from typing import Any, Dict, Optional

from agents.base_agent import BaseAgent
from agents.comprehension.repo_intelligence.tools import SnapshotStore, index_repository
from tools.shared import get_logger


class RepoIntelligenceAgent(BaseAgent):
    MODULE_NAME = "repo_intelligence"

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self.logger = get_logger("agent.repo_intelligence")

    def execute(self, request: dict, state: dict) -> Dict[str, Any]:
        emit = request.get("emit") or (lambda *a, **k: None)
        repo = request.get("repo_full_name") or "unknown/unknown"
        sha = request.get("commit_sha")
        store = request.get("snapshot_store")
        warnings = []
        if store is None:
            try:
                store = SnapshotStore()
            except Exception as exc:  # no database: index in memory only
                warnings.append(f"snapshot cache unavailable ({type(exc).__name__})")
                store = None

        if sha and store is not None:
            try:
                cached = store.find(repo, sha)
                if cached:
                    graph, chunks, model = store.load(cached)
                    emit(f"Repository index for {sha[:7]} already exists — reusing it ({len(graph.nodes)} nodes).", "success")
                    return self._result(cached, graph, chunks, model)
            except Exception as exc:
                warnings.append(f"snapshot cache lookup failed ({type(exc).__name__})")
                self.logger.warning(f"snapshot lookup failed: {exc}")

        idx = index_repository(Path(request["repo_dir"]), all_paths=request.get("repo_tree"))
        c, cov = idx.repo_model["counts"], idx.coverage
        emit(f"Indexed {cov.get('files_indexed', idx.file_count)} of {idx.file_count} files: {c.get('route', 0)} routes, "
             f"{c.get('page', 0)} pages, {c.get('form', 0)} forms, {c.get('agent', 0)} agents, {c.get('prompt', 0)} prompts, "
             f"{c.get('test', 0)} tests; {len(idx.graph.edges)} links, {len(idx.chunks)} code chunks.", "success")
        langs = ", ".join(f"{k} {v}" for k, v in list((cov.get("by_language") or {}).items())[:8])
        if langs:
            emit(f"Indexed by language: {langs}.")
        missing = cov.get("unfetched_source_count", 0) + cov.get("unindexed_source_count", 0)
        if missing:
            skipped = ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in (cov.get("skipped") or {}).items())
            emit(f"Coverage limitation: {missing} source file(s) are not in the index ({skipped}); "
                 "criteria that would live there cannot be judged not implemented.", "warning")

        snapshot_id = None
        if not sha:
            emit("No commit SHA was resolved, so this index is not cached.", "warning")
        elif store is not None:
            try:
                snapshot_id = store.save(repo, sha, idx)
            except Exception as exc:
                warnings.append(f"snapshot could not be saved ({type(exc).__name__})")
                self.logger.warning(f"snapshot save failed: {exc}")
        result = self._result(snapshot_id, idx.graph, idx.chunks, idx.repo_model)
        if warnings:
            emit("Repository index is in memory only: " + "; ".join(warnings) + ".", "warning")
            result.update(status="partial", error="; ".join(warnings))
        return result

    def _result(self, snapshot_id, graph, chunks, model) -> Dict[str, Any]:
        return {
            "module": self.MODULE_NAME,
            "status": "success",
            "snapshot_id": snapshot_id,
            "repo_graph": graph,      # in-memory, for this run's traceability (not serialised)
            "code_chunks": chunks,
            "repo_model": model,      # includes "coverage" (files indexed, by language, skipped by reason)
        }
