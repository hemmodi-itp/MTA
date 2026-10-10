"""
migrations.py — pure v1 -> v2 upgrades (no I/O).

`detect_version(name, data)` decides what is on disk; `to_v2(name, data)` returns a
new v2 document (the input is never mutated). v1 bodies are preserved verbatim
except for one canonicalisation: the old Python-fallback test_data shape
(`positive_dataset: {description, data: {field: value}}`,
`negative_variants[].data`) is rewritten to the canonical field/iteration shape
every reader expects (docs/audit/current_state.md §3).
"""

import copy
from typing import Any, Dict, List

from contracts.artifacts.models import SCHEMA_VERSION
from contracts.artifacts.registry import spec_for


class ArtifactVersionError(ValueError):
    """The document claims a schema_version this MTA does not understand."""


def detect_version(name: str, data: Any) -> int:
    spec = spec_for(name)
    if spec.kind == "plain":
        return 1
    if isinstance(data, dict) and "schema_version" in data:
        try:
            version = int(data["schema_version"])
        except (TypeError, ValueError):
            raise ArtifactVersionError(f"{name}: unreadable schema_version {data['schema_version']!r}")
        if version > SCHEMA_VERSION:
            raise ArtifactVersionError(
                f"{name}: schema_version {version} is newer than this MTA supports ({SCHEMA_VERSION})"
            )
        if version == SCHEMA_VERSION:
            return version
    return 1


def _fields_from_mapping(data: Any) -> List[Dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    return [{"field_name": k, "field_type": "text", "value": "" if v is None else str(v)} for k, v in data.items()]


def _canonical_dataset(record: Any) -> Any:
    """Rewrite the fallback_core shape into the canonical one; leave others as is."""
    if not isinstance(record, dict):
        return record
    out = dict(record)
    pos = out.get("positive_dataset")
    if isinstance(pos, dict):
        out["positive_dataset"] = _fields_from_mapping(pos.get("data", {}))
        if pos.get("description") and "positive_description" not in out:
            out["positive_description"] = pos["description"]
    variants = []
    for v in out.get("negative_variants") or []:
        if isinstance(v, dict) and "iterations" not in v and isinstance(v.get("data"), dict):
            fields = _fields_from_mapping(v["data"])
            v = {k: val for k, val in v.items() if k != "data"}
            v["iterations"] = [{"fields": fields, "expected_error": None}]
        variants.append(v)
    if "negative_variants" in out:
        out["negative_variants"] = variants
    return out


def to_v2(name: str, data: Any) -> Dict[str, Any]:
    spec = spec_for(name)
    if spec.kind == "plain":
        raise ValueError(f"{name} has no versioned envelope")
    if detect_version(name, data) == SCHEMA_VERSION:
        return copy.deepcopy(data)

    body = copy.deepcopy(data)
    envelope = {"schema_version": SCHEMA_VERSION, "artifact": name}
    if spec.kind == "dict":
        if not isinstance(body, dict):
            raise ValueError(f"{name}: v1 document must be a JSON object, got {type(body).__name__}")
        body.pop("schema_version", None)
        body.pop("artifact", None)
        return {**envelope, **body}
    if spec.kind == "list":
        if isinstance(body, dict) and spec.payload_key in body:
            body = body[spec.payload_key]
        if not isinstance(body, list):
            raise ValueError(f"{name}: v1 document must be a JSON array, got {type(body).__name__}")
        if name == "test_data":
            body = [_canonical_dataset(r) for r in body]
        return {**envelope, spec.payload_key: body}
    if spec.kind == "map":
        if not isinstance(body, dict):
            raise ValueError(f"{name}: v1 document must be a JSON object, got {type(body).__name__}")
        body.pop("schema_version", None)
        return {**envelope, spec.payload_key: body}
    raise AssertionError(spec.kind)


def payload_of(name: str, v2: Dict[str, Any]) -> Any:
    """The legacy-shaped body readers use: the list / id-map for enveloped artifacts,
    the (v2) dict itself for dict artifacts."""
    spec = spec_for(name)
    if spec.kind in ("list", "map"):
        return v2.get(spec.payload_key, [] if spec.kind == "list" else {})
    return v2


def to_v1(name: str, data: Any) -> Any:
    """Downgrade (for `migrate --to 1`): strip the envelope, restore the v1 body."""
    spec = spec_for(name)
    if spec.kind == "plain" or detect_version(name, data) == 1:
        return copy.deepcopy(data)
    if spec.kind == "dict":
        return {k: v for k, v in copy.deepcopy(data).items() if k not in ("schema_version", "artifact")}
    return copy.deepcopy(data.get(spec.payload_key, [] if spec.kind == "list" else {}))
