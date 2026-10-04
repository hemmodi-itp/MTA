"""
retrieve.py — find the code a criterion is most likely implemented in.

    index = CodeIndex(graph, chunks)          # once per run
    hits = index.search(terms, k=12)          # [(chunk, score, why)]

Signals, merged with reciprocal-rank fusion:
  * BM25 over identifier-split tokens of every chunk;
  * graph seeds: routes, pages, forms, agents, prompts, config whose names match the terms,
    mapped to the chunks that contain their handler / file;
  * graph expansion: chunks of symbols one or two `calls`/`exposes`/`calls_api` hops away
    from the best seeds, so a whole path (form → route → handler → helper) arrives together.
"""

import math
import re
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from engines.repo_intel.model import Chunk, Graph

_WORD = re.compile(r"[A-Za-z][a-z]+|[A-Z]+(?![a-z])|\d+")
_STOP = {"the", "and", "for", "with", "that", "this", "from", "into", "must", "should", "shall", "will", "are", "is",
         "be", "can", "user", "users", "system", "when", "each", "all", "any", "not", "its", "their", "have", "has",
         "self", "none", "true", "false", "return", "import", "def", "const", "let", "var", "function", "class", "async",
         "await", "new", "if", "else", "in", "of", "to", "a", "an", "or", "on", "by", "as", "at", "it"}
_SEED_KINDS = ("route", "page", "form", "agent", "prompt", "config", "component", "model_call", "table", "symbol")
WIRING_EDGES = ("exposes", "calls", "calls_api", "submits_to", "renders", "uses_prompt", "uses_model", "defines", "tests")


def tokenize(text: str) -> List[str]:
    """Split identifiers (camelCase, snake_case, kebab) and prose into lowercase stems."""
    out = []
    for w in _WORD.findall(text):
        w = w.lower()
        if len(w) < 2 or w in _STOP:
            continue
        out.append(w[:-1] if len(w) > 4 and w.endswith("s") else w)
    return out


class CodeIndex:
    def __init__(self, graph: Graph, chunks: Sequence[Chunk]):
        self.graph = graph
        self.chunks = [c for c in chunks if c.content.strip()]
        self.docs = [Counter(tokenize(f"{c.file_path} {c.symbol or ''} {c.content}")) for c in self.chunks]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg = (sum(self.lengths) / len(self.lengths)) if self.lengths else 1.0
        self.df: Counter = Counter()
        for d in self.docs:
            self.df.update(d.keys())
        self.by_file: Dict[str, List[int]] = defaultdict(list)
        for i, c in enumerate(self.chunks):
            self.by_file[c.file_path].append(i)
        # graph-seed candidates with their tokens, computed once (graph_seeds runs per criterion)
        self.seed_nodes: List[Tuple[str, str, frozenset]] = []
        for key, n in graph.nodes.items():
            if n.kind not in _SEED_KINDS:
                continue
            text = f"{n.name or ''} {key} {' '.join(str(v) for v in n.props.values() if isinstance(v, (str, list)))}"
            self.seed_nodes.append((key, n.kind, frozenset(tokenize(text))))
        self.by_leaf: Dict[str, List[str]] = defaultdict(list)       # symbol leaf name → node keys
        self.files_by_name: Dict[str, List[str]] = defaultdict(list)  # file basename → file node keys
        for key, n in graph.nodes.items():
            if n.kind == "file":
                self.files_by_name[(n.file_path or "").rsplit("/", 1)[-1].lower()].append(key)
            else:
                self.by_leaf[(n.name or "").split(".")[-1].lower()].append(key)

    # ── BM25 ────────────────────────────────────────────────────────────────
    def bm25(self, terms: Iterable[str], k: int = 30, k1: float = 1.4, b: float = 0.75) -> List[Tuple[int, float]]:
        q = [t for t in dict.fromkeys(tokenize(" ".join(terms)))]
        n = len(self.docs)
        scores = []
        for i, d in enumerate(self.docs):
            s = 0.0
            for t in q:
                tf = d.get(t)
                if not tf:
                    continue
                idf = math.log(1 + (n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                s += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * self.lengths[i] / self.avg))
            if s > 0:
                scores.append((i, s))
        return sorted(scores, key=lambda x: -x[1])[:k]

    # ── graph ───────────────────────────────────────────────────────────────
    def chunks_for_node(self, key: str) -> List[int]:
        n = self.graph.nodes.get(key)
        if not n or not n.file_path:
            return []
        idxs = self.by_file.get(n.file_path, [])
        if n.start_line:
            end = n.end_line or n.start_line
            inside = [i for i in idxs if self.chunks[i].start_line <= end and self.chunks[i].end_line >= n.start_line]
            if inside:
                return inside
        return idxs[:2]

    def graph_seeds(self, terms: Iterable[str], k: int = 12) -> List[Tuple[str, float]]:
        q = set(tokenize(" ".join(terms)))
        scored = []
        for key, kind, toks in self.seed_nodes:
            overlap = q & toks
            if overlap:
                weight = 1.5 if kind in ("route", "form", "page", "agent") else 1.0
                scored.append((key, weight * len(overlap)))
        return sorted(scored, key=lambda x: -x[1])[:k]

    def expand(self, key: str, hops: int = 2) -> List[str]:
        """Node keys reachable along wiring edges, both directions, up to `hops`."""
        seen, frontier = {key}, [key]
        for _ in range(hops):
            nxt = []
            for k in frontier:
                for _, d in self.graph.out(k, WIRING_EDGES):
                    if d not in seen:
                        seen.add(d)
                        nxt.append(d)
                for _, s in self.graph.inbound(k, ("exposes", "calls_api", "submits_to", "calls")):
                    if s not in seen:
                        seen.add(s)
                        nxt.append(s)
            frontier = nxt
        return list(seen)

    # ── fused search ────────────────────────────────────────────────────────
    def search(self, terms: Sequence[str], k: int = 12, rrf_k: int = 60) -> List[Tuple[Chunk, float, str]]:
        fused: Dict[int, float] = defaultdict(float)
        why: Dict[int, str] = {}
        for rank, (i, _) in enumerate(self.bm25(terms, 30)):
            fused[i] += 1 / (rrf_k + rank)
            why.setdefault(i, "text match")
        seeds = self.graph_seeds(terms)
        for rank, (key, _) in enumerate(seeds):
            for i in self.chunks_for_node(key):
                fused[i] += 1 / (rrf_k + rank)
                why[i] = f"graph: {self.graph.nodes[key].kind} {self.graph.nodes[key].name}"
        # expand from the top seeds so whole paths come together
        for key, _ in seeds[:4]:
            for nk in self.expand(key, hops=2):
                for i in self.chunks_for_node(nk)[:2]:
                    fused[i] += 0.5 / (rrf_k + 10)
                    why.setdefault(i, f"linked to {self.graph.nodes[key].name}")
        ranked = sorted(fused.items(), key=lambda x: -x[1])[:k]
        return [(self.chunks[i], s, why.get(i, "")) for i, s in ranked]

    def lookup(self, names: Sequence[str], k: int = 8) -> List[Tuple[Chunk, float, str]]:
        """Chunks defining the exact symbols / components / files the verifier asked for."""
        # Symbols first: a named function/component/prompt is what the verifier could not see.
        # File names only as a fallback — generic names (service.py, index.ts) repeat across folders
        # and would otherwise crowd out the exact definition that was asked for.
        symbols, files = {}, {}  # ordered: the verifier's order
        for n in names:
            n = (n or "").strip().strip("()`'\"")
            if len(n) < 3:
                continue
            leaf = re.split(r"[/#]", n)[-1]
            if re.search(r"\.(py|tsx?|jsx?|md|json|java|kt|go|rb|cs|rs|php|swift|dart|vue|svelte|c|h|cpp|hpp)$", leaf, re.I):
                files[leaf.lower()] = None
            else:
                symbols[leaf.split(".")[-1].lower()] = None
        found: List[int] = []

        def take(idxs: List[int], cap: int) -> None:
            for i in idxs[:cap]:
                if i not in found:
                    found.append(i)

        for name in symbols:
            for key in self.by_leaf.get(name, []):
                take(self.chunks_for_node(key), 3)
        if len(found) < k:
            for name in files:
                for key in self.files_by_name.get(name, []):
                    take(self.chunks_for_node(key), 1)
        return [(self.chunks[i], 1.0, "requested by verifier") for i in found[:k]]

    def paths_for(self, hits: Sequence[Tuple[Chunk, float, str]]) -> List[str]:
        """Human-readable wiring paths that touch the retrieved chunks (shown to the verifier)."""
        files = {c.file_path for c, _, _ in hits}
        lines = []
        for n in self.graph.of_kind("route"):
            key = n.key
            for _, h in self.graph.out(key, ["exposes"]):
                hn = self.graph.nodes.get(h)
                if hn and hn.file_path in files:
                    callers = [s for _, s in self.graph.inbound(key, ["calls_api", "submits_to"])]
                    via = f"{callers[0].split(':', 1)[1]} → " if callers else ""
                    lines.append(f"{via}{n.name} → {hn.name or hn.key} ({hn.file_path}:{hn.start_line})")
        return sorted(set(lines))[:20]
