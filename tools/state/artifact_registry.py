"""
artifact_registry — persists per-module ID counters and content signatures for
every test artifact (business scenarios, DOM intents, test data, specs).

Problem this solves: several agents (comprehension, discovery, test data,
script generation) used to assign artifact IDs as a bare sequential counter
that restarted at 1 on every run/module. Re-running discovery for a project
with an existing module, or adding a new module with the same starting
numbering, caused genuinely new content to be assigned an ID that collided
with unrelated, previously-generated content (e.g. a new module's BS-001
colliding with an older module's BS-001). Downstream "already covered" checks
then matched on that colliding ID and skipped generation for real new content.

Fix: IDs are namespaced by module (`{module_id}_{artifact_type}_{n:03d}`,
e.g. "M03_BS_007") and only assigned once per distinct *content* signature —
a sha256 of the normalized text that defines the artifact (title + steps for
a scenario, action + element name for a DOM intent, etc). Re-processing
identical content always resolves to the same ID; genuinely new content
always gets a new, non-colliding ID. The mapping is persisted to
artifact_registry.json in the project directory so numbering survives across
runs/processes.
"""

import hashlib
import json
import os
import re
import threading
from typing import Dict, Tuple

_REGISTRY_FILENAME = "artifact_registry.json"
_LOCK = threading.Lock()


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def content_signature(*parts: str) -> str:
    """sha256 hex digest of the normalized, joined content parts."""
    normalized = "||".join(_normalize(p) for p in parts)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class ArtifactRegistry:
    """
    Tracks, per project, the next available ID number for each
    (module_id, artifact_type) pair, and the content signature each
    already-assigned ID corresponds to.
    """

    def __init__(self, project_dir: str):
        self.project_dir = project_dir
        self.path = os.path.join(project_dir, _REGISTRY_FILENAME)
        self._data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as fh:
                    data = json.load(fh) or {}
                data.setdefault("counters", {})
                data.setdefault("content_index", {})
                return data
            except Exception:
                pass
        return {"counters": {}, "content_index": {}}

    def save(self) -> None:
        with _LOCK:
            os.makedirs(self.project_dir, exist_ok=True)
            tmp_path = self.path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.path)

    def get_or_create_id(
        self,
        module_id: str,
        artifact_type: str,
        *content_parts: str,
    ) -> Tuple[str, bool, str]:
        """
        Resolve the artifact ID for this module + content.

        Returns:
            (artifact_id, is_new, content_hash)

        Re-calling with the same (module_id, artifact_type, content_parts)
        always returns the same artifact_id — the counter is only advanced
        for genuinely new content.
        """
        module_id = module_id or "GEN"
        content_hash = content_signature(*content_parts)
        index_key = f"{module_id}:{artifact_type}:{content_hash}"

        existing = self._data["content_index"].get(index_key)
        if existing:
            return existing, False, content_hash

        counters: Dict[str, Dict[str, int]] = self._data["counters"]
        module_counters = counters.setdefault(module_id, {})
        next_n = module_counters.get(artifact_type, 0) + 1
        module_counters[artifact_type] = next_n

        artifact_id = f"{module_id}_{artifact_type}_{next_n:03d}"
        self._data["content_index"][index_key] = artifact_id
        return artifact_id, True, content_hash
