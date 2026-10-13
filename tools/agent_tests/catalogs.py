"""
catalogs.py — the curated, versioned payload catalogs in tools/agent_tests/catalog/*.yaml (Phase 9.6).

Red-team payloads come only from these files; generators never write new attack text. Each catalog carries a
`version`, recorded in the dataset manifest and in each case's tags (catalog:<name>@<version>#<entry id>).
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List

import yaml

CATALOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "catalog")
NAMES = ("injection_direct", "injection_indirect", "leakage", "harmful", "out_of_scope", "robustness")


@dataclass(frozen=True)
class Catalog:
    name: str
    version: int
    entries: List[Dict[str, Any]] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)  # the whole file (for non-list catalogs like robustness)

    def tag(self, entry_id: str) -> str:
        return f"catalog:{self.name}@{self.version}#{entry_id}"


def load_catalogs(directory: str = CATALOG_DIR) -> Dict[str, Catalog]:
    out: Dict[str, Catalog] = {}
    for name in NAMES:
        with open(os.path.join(directory, f"{name}.yaml"), encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        version = data.get("version")
        if not isinstance(version, int):
            raise ValueError(f"catalog {name}.yaml has no integer `version`")
        entries = data.get("entries") or []
        ids = [e.get("id") for e in entries]
        if len(ids) != len(set(ids)) or any(not i for i in ids):
            raise ValueError(f"catalog {name}.yaml: entry ids must be present and unique")
        out[name] = Catalog(name, version, entries, data)
    return out


def versions(catalogs: Dict[str, Catalog]) -> Dict[str, int]:
    return {k: c.version for k, c in sorted(catalogs.items())}
