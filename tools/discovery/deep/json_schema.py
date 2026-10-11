"""
json_schema.py — deterministic JSON-schema inference for the network inventory (task 2.5).

    infer(sample)              -> schema of one JSON value
    merge(schema_a, schema_b)  -> schema accepting both
    infer_many(samples)        -> merged schema (None for no samples)

Rules: types are JSON Schema type names; an object's `required` = keys present in every
sample; arrays merge their item schemas; integers widen to number; incompatible types
become a sorted `type` list; recursion stops at MAX_DEPTH. Values are never stored.
"""

from typing import Any, Dict, Iterable, List, Optional

MAX_DEPTH = 6


def _type_of(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, float):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    if isinstance(v, dict):
        return "object"
    return "string"


def infer(value: Any, depth: int = 0) -> Dict[str, Any]:
    t = _type_of(value)
    if depth >= MAX_DEPTH or t not in ("object", "array"):
        return {"type": t}
    if t == "object":
        props = {str(k): infer(v, depth + 1) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
        return {"type": "object", "properties": props, "required": sorted(props)}
    items: Optional[Dict[str, Any]] = None
    for v in value:
        s = infer(v, depth + 1)
        items = s if items is None else merge(items, s)
    return {"type": "array", "items": items or {}}


def _types(s: Dict[str, Any]) -> List[str]:
    t = s.get("type")
    return list(t) if isinstance(t, list) else ([t] if t else [])


def merge(a: Optional[Dict[str, Any]], b: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not a:
        return dict(b or {})
    if not b:
        return dict(a)
    ta, tb = set(_types(a)), set(_types(b))
    if {"integer", "number"} & ta and {"integer", "number"} & tb:
        ta = {("number" if t == "integer" else t) for t in ta}
        tb = {("number" if t == "integer" else t) for t in tb}
    if ta == tb == {"object"}:
        pa, pb = a.get("properties") or {}, b.get("properties") or {}
        props = {k: merge(pa.get(k), pb.get(k)) for k in sorted(set(pa) | set(pb))}
        required = sorted(set(a.get("required") or []) & set(b.get("required") or []))
        return {"type": "object", "properties": props, "required": required}
    if ta == tb == {"array"}:
        return {"type": "array", "items": merge(a.get("items"), b.get("items"))}
    if ta == tb and len(ta) == 1:
        return {"type": next(iter(ta))}
    types = sorted(ta | tb)
    return {"type": types[0] if len(types) == 1 else types}


def infer_many(samples: Iterable[Any]) -> Optional[Dict[str, Any]]:
    out: Optional[Dict[str, Any]] = None
    for s in samples:
        out = merge(out, infer(s)) if out is not None else infer(s)
    return out
