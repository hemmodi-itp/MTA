"""
usage.py — process-wide LLM token-usage recorder (Phase 0.3, benchmark metric
"LLM tokens and cost per run"). Observe-only: it never changes a call.

Every connector calls `record(...)` after a completed call. Totals are kept in
memory (`snapshot()` / `reset()`); when MTA_LLM_USAGE_LOG is set, each call is
also appended as one JSON line to that file, so a parent process (the benchmark
runner) can total a `python main.py` subprocess's usage.

A response-cache hit is recorded with `cached=True` and zero tokens.
"""

import json
import os
import threading
import time
from typing import Any, Dict, Optional

_lock = threading.Lock()
_totals: Dict[str, Dict[str, int]] = {}

ENV_LOG = "MTA_LLM_USAGE_LOG"


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def record(provider: str, model: Optional[str], input_tokens: Any = 0, output_tokens: Any = 0,
           cached: bool = False, source: Optional[str] = None) -> None:
    entry = {
        "ts": round(time.time(), 3),
        "provider": provider,
        "model": model or "unknown",
        "input_tokens": _as_int(input_tokens),
        "output_tokens": _as_int(output_tokens),
        "cached": bool(cached),
    }
    if source:
        entry["source"] = source
    key = f"{entry['provider']}/{entry['model']}"
    with _lock:
        t = _totals.setdefault(key, {"calls": 0, "cache_hits": 0, "input_tokens": 0, "output_tokens": 0})
        t["calls"] += 1
        t["cache_hits"] += 1 if cached else 0
        t["input_tokens"] += entry["input_tokens"]
        t["output_tokens"] += entry["output_tokens"]
        path = os.environ.get(ENV_LOG)
        if path:
            try:
                os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
                with open(path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry) + "\n")
            except OSError:
                pass  # usage logging must never break an LLM call


def record_gemini(model: Optional[str], usage_metadata: Any, source: Optional[str] = None) -> None:
    """Gemini `usage_metadata`: thinking tokens are billed as output."""
    if usage_metadata is None:
        record("gemini", model, 0, 0, source=source or "no_usage_metadata")
        return
    get = (lambda k: usage_metadata.get(k)) if isinstance(usage_metadata, dict) else (
        lambda k: getattr(usage_metadata, k, None))
    record("gemini", model, get("prompt_token_count"),
           _as_int(get("candidates_token_count")) + _as_int(get("thoughts_token_count")), source=source)


def snapshot() -> Dict[str, Dict[str, int]]:
    with _lock:
        return {k: dict(v) for k, v in _totals.items()}


def reset() -> None:
    with _lock:
        _totals.clear()


def summarize_log(path: str) -> Dict[str, Dict[str, int]]:
    """Totals per provider/model from a MTA_LLM_USAGE_LOG JSONL file (missing -> {})."""
    totals: Dict[str, Dict[str, int]] = {}
    if not path or not os.path.exists(path):
        return totals
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            key = f"{e.get('provider')}/{e.get('model')}"
            t = totals.setdefault(key, {"calls": 0, "cache_hits": 0, "input_tokens": 0, "output_tokens": 0})
            t["calls"] += 1
            t["cache_hits"] += 1 if e.get("cached") else 0
            t["input_tokens"] += _as_int(e.get("input_tokens"))
            t["output_tokens"] += _as_int(e.get("output_tokens"))
    return totals
