"""
blast.py — Phase 6.5 blast radius: a locator_map.json fix changes every spec that uses the key, so every one of
those specs is re-run, not only the one that failed.

A plan-rendered spec references a key as `action.<verb>("key", ...)` (or `dragAndDrop("a", "key")`); a spec that
calls a flow (flows.generated.ts) uses every key that flow uses.
"""

from __future__ import annotations

import os
import re
from typing import Dict, Iterable, List, Set

_ACTION_KEYS = re.compile(r"action\.\w+\(\s*['\"]([\w.-]+)['\"](?:\s*,\s*['\"]([\w.-]+)['\"])?")
_FLOW_DEF = re.compile(r"export async function (\w+)\(")
_FLOW_CALL = re.compile(r"flows\.(\w+)\(")


def keys_in(text: str) -> Set[str]:
    out: Set[str] = set()
    for a, b in _ACTION_KEYS.findall(text or ""):
        out.add(a)
        if b:
            out.add(b)
    return out


def flow_keys(flows_ts: str) -> Dict[str, Set[str]]:
    """{flow name: keys it uses} from flows.generated.ts."""
    out: Dict[str, Set[str]] = {}
    parts = _FLOW_DEF.split(flows_ts or "")
    for name, body in zip(parts[1::2], parts[2::2]):
        out[name] = keys_in(body)
    return out


def specs_using_keys(scripts_dir: str, keys: Iterable[str], flows_ts_path: str = "") -> List[str]:
    """Spec paths (relative to scripts_dir, "/" separators) that use any of `keys`, sorted."""
    wanted = set(keys)
    if not wanted or not os.path.isdir(scripts_dir):
        return []
    flows: Dict[str, Set[str]] = {}
    if flows_ts_path and os.path.isfile(flows_ts_path):
        with open(flows_ts_path, encoding="utf-8") as fh:
            flows = flow_keys(fh.read())
    hits = []
    for root, _dirs, files in os.walk(scripts_dir):
        for f in files:
            if not f.endswith(".spec.ts"):
                continue
            path = os.path.join(root, f)
            try:
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
            except OSError:
                continue
            used = keys_in(text)
            for flow in _FLOW_CALL.findall(text):
                used |= flows.get(flow, set())
            if used & wanted:
                hits.append(os.path.relpath(path, scripts_dir).replace(os.sep, "/"))
    return sorted(hits)
