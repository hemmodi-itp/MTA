"""model.py — in-memory graph types produced by the parsers and persisted by store.py."""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


@dataclass
class Node:
    kind: str
    key: str
    file_path: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    name: Optional[str] = None
    props: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    file_path: str
    start_line: int
    end_line: int
    content: str
    symbol: Optional[str] = None


@dataclass
class Graph:
    """Nodes by key plus a set of (src, kind, dst) edges.

    `out`, `inbound`, `of_kind` and `in_file` are served from indexes, so traceability's graph walks are O(degree)
    rather than O(|E|). The indexes are rebuilt lazily whenever `edges` / `nodes` changed size since they were built,
    so code that mutates `graph.edges` or `graph.nodes` directly (older callers, tests) stays correct.
    """
    nodes: Dict[str, Node] = field(default_factory=dict)
    edges: set = field(default_factory=set)  # {(src_key, kind, dst_key)}

    def __post_init__(self) -> None:
        self._out: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        self._in: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        self._edges_indexed = 0
        self._kind_index: Dict[str, List[Node]] = {}
        self._file_index: Dict[str, List[Node]] = {}
        self._nodes_indexed = -1

    # ── mutation ──
    def add(self, node: Node) -> Node:
        existing = self.nodes.get(node.key)
        if existing is None:
            self.nodes[node.key] = node
            return node
        existing.props.update({k: v for k, v in node.props.items() if k not in existing.props})
        return existing

    def link(self, src: str, kind: str, dst: str) -> None:
        if src == dst or (src, kind, dst) in self.edges:
            return
        in_sync = self._edges_indexed == len(self.edges)
        self.edges.add((src, kind, dst))
        if in_sync:  # keep the adjacency index current without a rebuild
            self._out[src].append((kind, dst))
            self._in[dst].append((kind, src))
            self._edges_indexed += 1

    # ── indexes ──
    def _adjacency(self) -> None:
        if self._edges_indexed == len(self.edges):
            return
        self._out, self._in = defaultdict(list), defaultdict(list)
        for s, k, d in self.edges:
            self._out[s].append((k, d))
            self._in[d].append((k, s))
        self._edges_indexed = len(self.edges)

    def _node_indexes(self) -> None:
        if self._nodes_indexed == len(self.nodes):
            return
        kinds: Dict[str, List[Node]] = {}
        files: Dict[str, List[Node]] = {}
        for n in self.nodes.values():
            kinds.setdefault(n.kind, []).append(n)
            if n.file_path:
                files.setdefault(n.file_path, []).append(n)
        self._kind_index, self._file_index, self._nodes_indexed = kinds, files, len(self.nodes)

    # ── queries ──
    def of_kind(self, kind: str) -> List[Node]:
        self._node_indexes()
        return list(self._kind_index.get(kind, ()))

    def in_file(self, path: str) -> List[Node]:
        """Every node located in `path` (symbols, routes, forms, …)."""
        self._node_indexes()
        return list(self._file_index.get(path, ()))

    def out(self, key: str, kinds: Optional[Iterable[str]] = None) -> List[Tuple[str, str]]:
        self._adjacency()
        ks: Optional[Set[str]] = set(kinds) if kinds else None
        return [(k, d) for k, d in self._out.get(key, ()) if ks is None or k in ks]

    def inbound(self, key: str, kinds: Optional[Iterable[str]] = None) -> List[Tuple[str, str]]:
        self._adjacency()
        ks: Optional[Set[str]] = set(kinds) if kinds else None
        return [(k, s) for k, s in self._in.get(key, ()) if ks is None or k in ks]


def symbol_key(path: str, qualname: str) -> str:
    return f"symbol:{path}#{qualname}"


def normalize_route_path(path: str) -> str:
    """'/api/items/{id}' and '/api/items/:id' and '/api/items/${id}' → '/api/items/*'."""
    p = path.strip().split("?")[0].split("#")[0]
    p = p.replace("${", "{")
    parts = []
    for seg in p.split("/"):
        if not seg:
            continue
        if seg.startswith((":", "{", "[", "<")) or "{" in seg:
            parts.append("*")
        else:
            parts.append(seg.lower())
    return "/" + "/".join(parts)
