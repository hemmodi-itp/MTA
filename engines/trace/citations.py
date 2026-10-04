"""
citations.py — a verifier's citation only counts if the repository proves it.

validate_citation(): the file exists in the checkout, the line range is inside it, the cited
symbol occurs in (or right around) those lines, and identifiers named in the claim appear there.
is_wired(): the cited code is reachable from a user-facing entry point (route, page, form,
agent, test) through the knowledge graph within 3 hops — the E3-vs-E2 distinction.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from engines.repo_intel.model import Graph

_IDENT = re.compile(r"`([^`]{2,80})`|\b([A-Za-z_][A-Za-z0-9_]*(?:_[A-Za-z0-9]+|[a-z][A-Z][A-Za-z0-9]*)+)\b")
_ENTRY_KINDS = ("route", "page", "form", "agent", "test")


class FileCache:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self._lines: Dict[str, Optional[List[str]]] = {}

    def lines(self, rel: str) -> Optional[List[str]]:
        rel = rel.strip().lstrip("./").replace("\\", "/")
        if rel not in self._lines:
            p = (self.root / rel).resolve()
            ok = p.is_file() and self.root in p.parents
            self._lines[rel] = p.read_text(encoding="utf-8", errors="replace").splitlines() if ok else None
        return self._lines[rel]


def validate_citation(c: Dict, files: FileCache, slack: int = 3, graph: Optional[Graph] = None) -> Tuple[bool, str]:
    rel = str(c.get("file") or "")
    lines = files.lines(rel)
    if lines is None:
        return False, f"file not in repository: {rel}"
    try:
        start, end = int(c.get("start_line")), int(c.get("end_line") or c.get("start_line"))
    except (TypeError, ValueError):
        return False, "missing line numbers"
    if start < 1 or end < start or start > len(lines):
        return False, f"lines {start}-{end} outside {rel} ({len(lines)} lines)"
    end = min(end, len(lines))
    window = "\n".join(lines[max(0, start - 1 - slack): min(len(lines), end + slack)])
    symbol = str(c.get("symbol") or "").strip()
    if symbol:
        leaf = re.split(r"[.#:]", symbol)[-1].strip("()")
        if leaf and leaf not in window and not _encloses(graph, rel, leaf, start, end):
            return False, f"symbol {leaf} not found at {rel}:{start}-{end}"
    idents = [a or b for a, b in _IDENT.findall(str(c.get("claim") or ""))]
    idents = [i for i in idents if len(i) >= 4 and " " not in i][:6]
    if idents and not any(i in window for i in idents):
        return False, f"none of {idents[:3]} appear at {rel}:{start}-{end}"
    return True, "ok"


def _encloses(graph: Optional[Graph], rel: str, name: str, start: int, end: int) -> bool:
    """The cited lines sit inside a definition of `name` in that file (a function body, a prompt constant)."""
    if graph is None:
        return False
    rel = rel.strip().lstrip("./")
    for n in graph.in_file(rel):
        if n.start_line and (n.name or "").split(".")[-1] == name:
            if n.start_line <= start and end <= (n.end_line or n.start_line) + 1:
                return True
            if n.kind == "component" and n.start_line <= start:  # components carry no end line
                return True
    return False


def nodes_at(graph: Graph, rel: str, start: int, end: int) -> List[str]:
    out = []
    for n in graph.in_file(rel):
        key = n.key
        if n.start_line and n.kind in ("symbol", "route", "form", "component", "prompt", "agent"):
            if n.start_line <= end and (n.end_line or n.start_line) >= start:
                out.append(key)
    return out or ([f"file:{rel}"] if f"file:{rel}" in graph.nodes else [])


def is_wired(graph: Graph, keys: List[str], hops: int = 3) -> Optional[str]:
    """Return the entry point that reaches any of `keys`, or None."""
    frontier, seen = list(keys), set(keys)
    for _ in range(hops + 1):
        for k in frontier:
            n = graph.nodes.get(k)
            if n and n.kind in _ENTRY_KINDS:
                return f"{n.kind} {n.name}"
        nxt = []
        for k in frontier:
            for kind, src in graph.inbound(k, ("exposes", "calls", "calls_api", "submits_to", "renders", "defines",
                                                "uses_prompt", "tests")):
                if src not in seen:
                    seen.add(src)
                    nxt.append(src)
        frontier = nxt
    return None
