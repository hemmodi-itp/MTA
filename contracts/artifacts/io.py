"""
io.py — the one way MTA code reads and writes pipeline artifacts.

    load_payload(name, path, default)   -> body in the shape callers already use
                                           (list for test_data, id-map for
                                           scenario_element_map / test_plans, dict
                                           otherwise); accepts v1 or v2 on disk.
    save_artifact(name, path, payload)  -> writes the v2 envelope atomically.
    validate_document(name, data)       -> ValidationReport (never raises).
    validate_file(name, path)           -> ValidationReport for a file on disk.

Readers never fail because of a lenient-schema mismatch — enforcement is the
orchestrator's job at step boundaries (contracts.enforce: warn | block).
"""

import json
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any, List, Optional

from pydantic import ValidationError

from contracts.artifacts.migrations import ArtifactVersionError, detect_version, payload_of, to_v2
from contracts.artifacts.models import SCHEMA_VERSION
from contracts.artifacts.registry import spec_for

_MISSING = object()


class ArtifactContractError(ValueError):
    """An artifact failed its contract (used by callers that choose to raise)."""


@dataclass
class ValidationReport:
    artifact: str
    path: Optional[str] = None
    ok: bool = True
    version_found: Optional[int] = None
    migrated: bool = False
    errors: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"artifact": self.artifact, "path": self.path, "ok": self.ok,
                "version_found": self.version_found, "migrated": self.migrated, "errors": self.errors}


def read_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def upgrade(name: str, data: Any) -> Any:
    """v1 or v2 document -> v2 document (plain artifacts are returned unchanged)."""
    if spec_for(name).kind == "plain":
        return data
    return to_v2(name, data)


def load_payload(name: str, path: str, default: Any = _MISSING) -> Any:
    """
    Read *path* and return its body in the legacy shape (see module docstring).
    Missing file -> *default* (or FileNotFoundError when no default is given).
    Malformed JSON / an unsupported schema_version propagate as exceptions.
    """
    if not os.path.exists(path):
        if default is _MISSING:
            raise FileNotFoundError(path)
        return default
    data = read_json(path)
    if spec_for(name).kind == "plain":
        return data
    return payload_of(name, to_v2(name, data))


def wrap(name: str, payload: Any) -> Any:
    """Legacy-shaped body (or an existing v2 document) -> v2 document."""
    spec = spec_for(name)
    if spec.kind == "plain":
        return payload
    if spec.kind in ("list", "map"):
        if isinstance(payload, dict) and payload.get("schema_version") == SCHEMA_VERSION:
            return payload
        return {"schema_version": SCHEMA_VERSION, "artifact": name, spec.payload_key: payload}
    return to_v2(name, payload)


def atomic_write_json(path: str, data: Any) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def save_artifact(name: str, path: str, payload: Any) -> str:
    """Write *payload* (legacy shape or v2) as a v2 document, atomically."""
    atomic_write_json(path, wrap(name, payload))
    return path


def stamp(name: str, document: dict) -> dict:
    """For dict artifacts built in place: return *document* with the v2 envelope keys first."""
    return wrap(name, document)


def validate_document(name: str, data: Any, path: Optional[str] = None) -> ValidationReport:
    spec = spec_for(name)
    report = ValidationReport(artifact=name, path=path)
    try:
        if spec.kind == "plain":
            report.version_found = 1
            if name == "locator_map":
                if not isinstance(data, dict):
                    raise ValueError("locator_map must be a JSON object keyed by locator key")
                for key, entry in data.items():
                    spec.model.model_validate(entry)
            else:
                spec.model.model_validate(data)
            return report
        report.version_found = detect_version(name, data)
        report.migrated = report.version_found != SCHEMA_VERSION
        spec.model.model_validate(to_v2(name, data))
    except ValidationError as exc:
        report.ok = False
        report.errors = [
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()[:20]
        ]
    except (ArtifactVersionError, ValueError, TypeError) as exc:
        report.ok = False
        report.errors = [str(exc)]
    return report


def validate_file(name: str, path: str) -> ValidationReport:
    try:
        data = read_json(path)
    except FileNotFoundError:
        return ValidationReport(artifact=name, path=path, ok=False, errors=["file not found"])
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return ValidationReport(artifact=name, path=path, ok=False, errors=[f"invalid JSON: {exc}"])
    return validate_document(name, data, path)


def load_records(path: str) -> list:
    """test_data.json -> list of per-scenario records (v1 list, v2 envelope, or the
    legacy {scenario_id: record} map some early writers produced). Missing -> []."""
    if not os.path.exists(path):
        return []
    data = read_json(path)
    if isinstance(data, dict) and "schema_version" not in data and "datasets" not in data:
        return [dict(r, scenario_id=r.get("scenario_id") or sid)
                for sid, r in data.items() if isinstance(r, dict)]
    return payload_of("test_data", to_v2("test_data", data))
