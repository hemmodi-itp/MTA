"""
testdata_filter.py — enforces `safety.allow_security_probes` on generated test data.

When security probes are not allowed (the default; always on prod/unspecified),
negative/boundary iterations whose field values carry an active attack payload
(XSS, SQLi, path traversal, ... — see payloads.py) are removed. A variant left
with no iterations is removed too. Positive datasets are never altered (a payload
there would be an LLM error worth seeing), but such a value is reported.

Every removal is returned so the caller can report it; nothing is dropped silently.
"""

import copy
from typing import Any, Dict, List, Tuple

from tools.safety.payloads import detect_payload


def _with(obj: Any, **changes: Any) -> Any:
    """Copy *obj* with *changes* (pydantic model_copy when available)."""
    if hasattr(obj, "model_copy"):
        return obj.model_copy(update=changes)
    clone = copy.copy(obj)
    for k, v in changes.items():
        setattr(clone, k, v)
    return clone


def _payload_in_fields(fields) -> Tuple[str, str]:
    for f in fields or []:
        value = getattr(f, "value", None) if not isinstance(f, dict) else f.get("value")
        hit = detect_payload(value)
        if hit:
            name = getattr(f, "field_name", None) if not isinstance(f, dict) else f.get("field_name")
            return hit, str(name)
    return "", ""


def drop_security_payloads(datasets: List[Any]) -> Tuple[List[Any], List[Dict[str, Any]]]:
    """
    *datasets* are ScenarioTestData models (tools/test_creation/testdata/models.py).
    Returns (datasets, dropped) — models are copied, never mutated in place.
    """
    out: List[Any] = []
    dropped: List[Dict[str, Any]] = []
    for ds in datasets:
        before = len(dropped)
        kept_variants = []
        for variant in ds.negative_variants or []:
            kept_iterations = []
            for idx, it in enumerate(getattr(variant, "iterations", None) or []):
                category, field = _payload_in_fields(it.fields)
                if category:
                    dropped.append({
                        "scenario_id": ds.scenario_id, "variant_id": variant.variant_id,
                        "iteration": idx, "field": field, "payload": category,
                        "reason": "security_probe_not_allowed",
                    })
                else:
                    kept_iterations.append(it)
            if len(kept_iterations) == len(getattr(variant, "iterations", None) or []):
                kept_variants.append(variant)
            elif kept_iterations:
                kept_variants.append(_with(variant, iterations=kept_iterations))
            else:
                dropped.append({
                    "scenario_id": ds.scenario_id, "variant_id": variant.variant_id,
                    "reason": "security_probe_not_allowed", "scope": "variant",
                })
        changed = len(dropped) > before
        category, field = _payload_in_fields(getattr(ds, "positive_dataset", None))
        if category:
            dropped.append({
                "scenario_id": ds.scenario_id, "field": field, "payload": category,
                "reason": "payload_in_positive_dataset_reported_only", "scope": "positive",
            })
        out.append(_with(ds, negative_variants=kept_variants) if changed else ds)
    return out, dropped
