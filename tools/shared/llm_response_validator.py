"""
llm_response_validator.py — shared utility for validating LLM JSON responses.

Usage:
    from tools.shared.llm_response_validator import validate_llm_json

    parsed = validate_llm_json(raw_text, required_keys=["intents"])
    # raises ValueError with a clear message if validation fails
"""

import json
import re
from typing import Any, List, Optional

# One fence around the WHOLE reply: ```json\n … \n```  (language tag optional)
_OUTER_FENCE = re.compile(r"^```[A-Za-z0-9_-]*[ \t]*\r?\n?(.*?)\r?\n?[ \t]*```$", re.S)


def strip_outer_fence(raw: str) -> str:
    """Remove ONE markdown fence wrapping the whole reply (```json … ```), nothing else.

    Fences inside the payload (e.g. a Markdown code block inside a JSON string value such as
    brd_markdown) are content and must survive untouched.
    """
    text = (raw or "").strip()
    m = _OUTER_FENCE.match(text)
    return m.group(1).strip() if m else text


def parse_llm_json(raw: str) -> Any:
    """
    Strip a markdown fence around the whole payload, if present, and parse JSON.
    Raises ValueError on parse failure.
    """
    cleaned = strip_outer_fence(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"LLM returned invalid JSON: {exc}\n"
            f"--- first 500 chars ---\n{(raw or '')[:500]}"
        ) from exc


def validate_llm_json(
    raw: str,
    required_keys: Optional[List[str]] = None,
    expected_type: type = dict,
) -> Any:
    """
    Parse LLM output as JSON and validate its structure.

    Args:
        raw:           Raw text returned by the LLM.
        required_keys: If provided, each key must exist in the parsed dict.
        expected_type: Expected top-level type (dict or list). Default: dict.

    Returns the parsed object.
    Raises ValueError with a descriptive message on any failure.
    """
    parsed = parse_llm_json(raw)

    if not isinstance(parsed, expected_type):
        raise ValueError(
            f"LLM JSON has wrong top-level type: expected {expected_type.__name__}, "
            f"got {type(parsed).__name__}"
        )

    if required_keys and isinstance(parsed, dict):
        missing = [k for k in required_keys if k not in parsed]
        if missing:
            raise ValueError(
                f"LLM JSON is missing required keys: {missing}\n"
                f"Got keys: {list(parsed.keys())}"
            )

    return parsed


def validate_list_field(parsed: dict, field: str, min_length: int = 0) -> list:
    """
    Assert that parsed[field] is a list with at least min_length items.
    Returns the list. Raises ValueError otherwise.
    """
    value = parsed.get(field)
    if not isinstance(value, list):
        raise ValueError(f"Expected '{field}' to be a list, got {type(value).__name__}")
    if len(value) < min_length:
        raise ValueError(
            f"Expected '{field}' to have at least {min_length} item(s), got {len(value)}"
        )
    return value
