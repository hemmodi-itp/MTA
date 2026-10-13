"""
dataset.py — golden datasets in eval_sets/<agent>/ (Phase 9.2).

    eval_sets/<agent>/agent.yaml        the AgentSpec (its presence is the per-agent opt-in, design D3)
    eval_sets/<agent>/<dimension>.jsonl one AgentTestCase per line, sorted by id
    eval_sets/<agent>/manifest.json     dataset_version, generator/catalog versions, seed, counts, sha256 per file

Regeneration never destroys human work (design D9): reviewed and human-written cases are kept as they are; a
generated case whose content changed is replaced and goes back to unreviewed; unreviewed generated cases that are
no longer produced are dropped. dataset_version goes up by one whenever any file's content changes.
"""

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from pydantic import ValidationError

from tools.agent_tests.config import GENERATOR_VERSION, MIN_CASES
from tools.agent_tests.models import DIMENSIONS, AgentTestCase, canonical_json
from tools.agent_tests.spec import AgentSpec, load_spec

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATASET_ROOT = os.path.join(REPO_ROOT, "eval_sets")
MANIFEST = "manifest.json"
SPEC_FILE = "agent.yaml"


def agent_dir(agent: str, root: Optional[str] = None) -> str:
    if not agent or any(c in agent for c in "/\\") or agent.startswith("."):
        raise ValueError(f"invalid agent name {agent!r}")
    return os.path.join(root or DATASET_ROOT, agent)


def spec_for(directory: str) -> AgentSpec:
    return load_spec(os.path.join(directory, SPEC_FILE))


# ── reading / validating ────────────────────────────────────────────────────

@dataclass
class ValidationReport:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    counts: Dict[str, int] = field(default_factory=dict)
    unreviewed: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors


def load_cases(directory: str) -> Tuple[List[AgentTestCase], ValidationReport]:
    """Every case in the dataset (dimension order, file order) plus the problems found while reading."""
    rep = ValidationReport()
    cases: List[AgentTestCase] = []
    seen: Dict[str, str] = {}
    known = {f"{d}.jsonl" for d in DIMENSIONS}
    for name in sorted(os.listdir(directory)) if os.path.isdir(directory) else []:
        if name.endswith(".jsonl") and name not in known:
            rep.errors.append(f"{name}: not a known dimension file")
    for dim in DIMENSIONS:
        path = os.path.join(directory, f"{dim}.jsonl")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                if not line.strip():
                    continue
                where = f"{dim}.jsonl:{lineno}"
                try:
                    raw = json.loads(line)
                    case = AgentTestCase.model_validate(raw)
                except (json.JSONDecodeError, ValidationError) as exc:
                    rep.errors.append(f"{where}: {_first_error(exc)}")
                    continue
                if case.dimension != dim:
                    rep.errors.append(f"{where}: dimension {case.dimension!r} is in the wrong file")
                if case.id in seen:
                    rep.errors.append(f"{where}: duplicate id {case.id} (also in {seen[case.id]})")
                    continue
                seen[case.id] = where
                if case.content_hash and case.content_hash != case.compute_hash() and case.source != "human":
                    rep.warnings.append(f"{where}: {case.id} was edited by hand; set source: human to keep the edit "
                                        "through regeneration")
                cases.append(case)
    return cases, rep


def _first_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        e = exc.errors()[0]
        loc = ".".join(str(p) for p in e.get("loc", ()))
        return f"{loc + ': ' if loc else ''}{e.get('msg')}"
    return str(exc)


def validate(directory: str) -> ValidationReport:
    if not os.path.exists(os.path.join(directory, SPEC_FILE)):
        return ValidationReport(errors=[f"{directory}: no {SPEC_FILE} (the agent is not set up for Phase 9)"])
    try:
        spec = spec_for(directory)
    except (ValidationError, ValueError, OSError) as exc:
        return ValidationReport(errors=[f"{SPEC_FILE}: {_first_error(exc)}"])
    cases, rep = load_cases(directory)
    ids = {c.id for c in cases}
    for c in cases:
        if c.expected.same_as and c.expected.same_as not in ids:
            rep.errors.append(f"{c.id}: same_as points at missing case {c.expected.same_as}")
    for dim in DIMENSIONS:
        n = sum(1 for c in cases if c.dimension == dim)
        rep.counts[dim] = n
        cfg = spec.dimensions.get(dim)
        minimum = cfg.min_cases if cfg and cfg.min_cases is not None else MIN_CASES[dim]
        if spec.dimension_enabled(dim) and n < minimum:
            rep.warnings.append(f"{dim}: {n} case(s), below the minimum of {minimum}")
    rep.unreviewed = sum(1 for c in cases if not c.reviewed)
    manifest = read_manifest(directory)
    if manifest:
        for name, digest in (manifest.get("files") or {}).items():
            path = os.path.join(directory, name)
            if os.path.exists(path) and _sha256(path) != digest:
                rep.warnings.append(f"{name}: changed since the manifest was written (run generate or review)")
    return rep


# ── merging ─────────────────────────────────────────────────────────────────

def merge(existing: List[AgentTestCase], generated: List[AgentTestCase]) -> Tuple[List[AgentTestCase], Dict[str, list]]:
    """Generated cases merged into the stored ones by id (design D9). Returns (cases, changes by kind)."""
    changes: Dict[str, list] = {k: [] for k in ("added", "unchanged", "updated", "review_reset", "kept_reviewed",
                                                "kept_human", "dropped")}
    old = {c.id: c for c in existing}
    out: Dict[str, AgentTestCase] = {}
    for g in generated:
        prev = old.get(g.id)
        if prev is None:
            out[g.id] = g
            changes["added"].append(g.id)
        elif prev.source == "human":
            out[g.id] = prev
            changes["kept_human"].append(g.id)
        elif prev.compute_hash() == g.compute_hash():
            out[g.id] = prev  # keeps reviewed / reviewed_by / reviewed_at
            changes["unchanged"].append(g.id)
        else:
            out[g.id] = g
            changes["review_reset" if prev.reviewed else "updated"].append(g.id)
    produced = {g.id for g in generated}
    for c in existing:
        if c.id in produced:
            continue
        if c.source == "human":
            out[c.id] = c
            changes["kept_human"].append(c.id)
        elif c.reviewed:
            out[c.id] = c
            changes["kept_reviewed"].append(c.id)
        else:
            changes["dropped"].append(c.id)
    return list(out.values()), changes


# ── writing ─────────────────────────────────────────────────────────────────

def _sha256(path: str) -> str:
    """Over LF-normalised content, so a CRLF checkout (git autocrlf on Windows) keeps the same digest."""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()


def read_manifest(directory: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(directory, MANIFEST)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _render(cases: Iterable[AgentTestCase]) -> str:
    rows = sorted(cases, key=lambda c: c.id)
    return "".join(canonical_json(c.model_dump(exclude_none=True)) + "\n" for c in rows)


def write(directory: str, cases: List[AgentTestCase], agent: str, seed: Optional[int] = None,
          catalog_versions: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """Write one sorted jsonl file per dimension and the manifest. Byte-identical output for identical input."""
    os.makedirs(directory, exist_ok=True)
    prev = read_manifest(directory) or {}
    files: Dict[str, str] = {}
    counts: Dict[str, int] = {}
    for dim in DIMENSIONS:
        rows = [c for c in cases if c.dimension == dim]
        path = os.path.join(directory, f"{dim}.jsonl")
        if not rows:
            if os.path.exists(path):
                os.remove(path)
            continue
        body = _render(rows)
        if not os.path.exists(path) or open(path, encoding="utf-8").read() != body:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(body)
        files[f"{dim}.jsonl"] = _sha256(path)
        counts[dim] = len(rows)
    changed = files != (prev.get("files") or {})
    manifest = {
        "agent": agent,
        "dataset_version": int(prev.get("dataset_version") or 0) + (1 if changed or not prev else 0),
        "generator_version": GENERATOR_VERSION,
        "catalog_versions": catalog_versions if catalog_versions is not None else prev.get("catalog_versions", {}),
        "seed": seed if seed is not None else prev.get("seed"),
        "counts": counts,
        "total": sum(counts.values()),
        "unreviewed": sum(1 for c in cases if not c.reviewed),
        "files": files,
    }
    with open(os.path.join(directory, MANIFEST), "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    return manifest


def mark_reviewed(directory: str, by: str, on: str, ids: Optional[List[str]] = None,
                  dimension: Optional[str] = None, all_cases: bool = False) -> Tuple[List[str], List[str]]:
    """Set reviewed / reviewed_by / reviewed_at on the selected cases. Returns (marked ids, unknown ids)."""
    if not by.strip():
        raise ValueError("--by is required: who reviewed the cases")
    cases, rep = load_cases(directory)
    if rep.errors:
        raise ValueError("dataset has errors; run validate first: " + "; ".join(rep.errors[:3]))
    wanted = set(ids or [])
    known = {c.id for c in cases}
    marked: List[str] = []
    out: List[AgentTestCase] = []
    for c in cases:
        hit = all_cases or c.id in wanted or (dimension is not None and c.dimension == dimension)
        if hit and not c.reviewed:
            c = c.model_copy(update={"reviewed": True, "reviewed_by": by.strip(), "reviewed_at": on})
            marked.append(c.id)
        out.append(c)
    prev = read_manifest(directory) or {}
    write(directory, out, prev.get("agent") or os.path.basename(directory), prev.get("seed"),
          prev.get("catalog_versions"))
    return marked, sorted(wanted - known)
