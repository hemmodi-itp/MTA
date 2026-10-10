"""
payloads.py — deterministic detector for active security-probe payloads.

Used to enforce `safety.allow_security_probes`: when probes are not allowed
(the default, and always on prod/unspecified environments), test data that
carries an attack payload (XSS, SQL/NoSQL injection, path traversal, template
injection, command injection) is dropped and reported instead of being typed
into the application under test.
"""

import re
from typing import Any, Iterable, Optional

_PATTERNS = [
    ("xss", re.compile(r"<\s*/?\s*(script|iframe|svg|img|object|embed|body)\b", re.I)),
    ("xss", re.compile(r"javascript\s*:", re.I)),
    ("xss", re.compile(r"\bon(error|load|click|mouseover|focus|toggle)\s*=", re.I)),
    ("xss", re.compile(r"\balert\s*\(|\bprompt\s*\(|\bconfirm\s*\(", re.I)),
    ("sqli", re.compile(r"'\s*(or|and)\s*'?\d*'?\s*=\s*'?\d*", re.I)),
    ("sqli", re.compile(r"\bunion\s+(all\s+)?select\b", re.I)),
    ("sqli", re.compile(r";\s*(drop|delete|insert|update|truncate)\s+", re.I)),
    ("sqli", re.compile(r"'\s*--|'\s*#|\bor\s+1\s*=\s*1\b", re.I)),
    ("nosqli", re.compile(r"\{\s*['\"]?\$(ne|gt|lt|where|regex)['\"]?\s*:", re.I)),
    ("path_traversal", re.compile(r"(\.\./|\.\.\\){2,}|%2e%2e%2f", re.I)),
    ("template_injection", re.compile(r"\{\{\s*\d+\s*\*\s*\d+\s*\}\}|\$\{\s*\d+\s*\*\s*\d+\s*\}")),
    ("command_injection", re.compile(r"(;|\|\||&&|`)\s*(cat|ls|rm|curl|wget|id|whoami)\b", re.I)),
]


def detect_payload(value: Any) -> Optional[str]:
    """Return the payload category ('xss', 'sqli', ...) if *value* looks like one."""
    if not isinstance(value, str) or not value:
        return None
    for category, rx in _PATTERNS:
        if rx.search(value):
            return category
    return None


def first_payload(values: Iterable[Any]) -> Optional[str]:
    for v in values:
        hit = detect_payload(v)
        if hit:
            return hit
    return None
