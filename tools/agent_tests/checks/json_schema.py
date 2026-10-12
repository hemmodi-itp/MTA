"""
json_schema.py — does a reply satisfy a required JSON output format?

    ok, detail = check('{"answer": "x", "topic": "t", "source": null}', schema)

strict=True (default): the whole reply, trimmed, must be one JSON value — prose around it is a format violation.
strict=False: a single ```json fenced block or the first {...} object is accepted.
"""

import json
import re
from typing import Any, Dict, Optional, Tuple

from jsonschema import exceptions as js_exceptions
from jsonschema.validators import validator_for

_FENCE = re.compile(r"```(?:json)?\s*(.+?)\s*```", re.S | re.I)


def extract(text: str, strict: bool = True) -> Tuple[Optional[Any], Optional[str]]:
    """(parsed value, None) or (None, why it is not JSON)."""
    raw = (text or "").strip()
    candidates = [raw]
    if not strict:
        m = _FENCE.search(raw)
        if m:
            candidates.insert(0, m.group(1))
        start, end = raw.find("{"), raw.rfind("}")
        if 0 <= start < end:
            candidates.append(raw[start:end + 1])
    last_err = "empty reply"
    for c in candidates:
        try:
            return json.loads(c), None
        except json.JSONDecodeError as exc:
            last_err = f"not valid JSON ({exc.msg} at char {exc.pos})"
    return None, last_err


def check(text: str, schema: Dict[str, Any], strict: bool = True) -> Tuple[bool, str]:
    value, err = extract(text, strict)
    if err:
        return False, err
    cls = validator_for(schema)
    cls.check_schema(schema)
    errors = sorted(cls(schema).iter_errors(value), key=lambda e: list(e.absolute_path))
    if errors:
        e: js_exceptions.ValidationError = errors[0]
        where = "/".join(str(p) for p in e.absolute_path) or "(root)"
        return False, f"schema violation at {where}: {e.message}" + (f" (+{len(errors) - 1} more)" if len(errors) > 1 else "")
    return True, "valid JSON matching the schema"
