"""
constraints.py — boundaries and expected messages stated in text (BRD acceptance criteria, observed messages).

Pure functions, no I/O. The precedence when several sources state the same constraint is applied by the caller
(inputs.py): DOM constraint > BRD AC > observed validation > default (flagged).

    parse_constraints("Name must be 1–50 characters")       → {"length": {"min": 1, "max": 50}}
    parse_constraints("a whole number from 1 to 99")         → {"range": {"min": 1, "max": 99, "integer": True}}
    parse_constraints("files over 1 MB are rejected")        → {"size": {"max": 1048576}}
    quoted_messages('… rejected with "Name is required".')   → ["Name is required"]
"""

import re
from typing import Any, Dict, List, Optional

_NUM = r"(-?\d+(?:\.\d+)?)"
_DASH = r"\s*(?:-|–|—|to|and)\s*"
_UNIT_BYTES = {"b": 1, "byte": 1, "bytes": 1, "kb": 1024, "mb": 1024 ** 2, "gb": 1024 ** 3}
_WORD_NUM = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
             "eight": 8, "nine": 9, "ten": 10}

_LEN_RANGE = re.compile(rf"(?:between\s+)?{_NUM}{_DASH}{_NUM}\s*(?:characters|chars|letters)", re.I)
_LEN_MAX = re.compile(rf"(?:at most|up to|maximum(?: of)?|max(?:imum)?\.?|no more than|not exceed(?:ing)?)\s+{_NUM}\s*(?:characters|chars|letters)", re.I)
_LEN_MIN = re.compile(rf"(?:at least|minimum(?: of)?|min(?:imum)?\.?|no fewer than)\s+{_NUM}\s*(?:characters|chars|letters)", re.I)
_LEN_EXACT = re.compile(rf"exactly\s+{_NUM}\s*(?:characters|chars|letters)", re.I)
_LEN_OVER = re.compile(rf"{_NUM}\s+or more\s+(?:characters|chars|letters)\s+(?:is|are)\s+rejected", re.I)
_RANGE = re.compile(rf"(?:from|between)\s+{_NUM}{_DASH}{_NUM}(?!\s*(?:characters|chars|letters|MB|KB|GB|bytes))", re.I)
_MIN_WORD = re.compile(r"\b(zero|one|\d+)\s+or more\b(?!\s+(?:characters|chars|letters))", re.I)
_MIN_NUM = re.compile(rf"(?:at least|greater than or equal to|>=)\s+{_NUM}(?!\s*(?:characters|chars|letters|MB|KB|GB|bytes|%))", re.I)
_MAX_NUM = re.compile(rf"(?:at most|less than or equal to|<=|no more than)\s+{_NUM}(?!\s*(?:characters|chars|letters|decimals?|MB|KB|GB|bytes|%))", re.I)
_DECIMALS = re.compile(r"(?:at most|up to|max(?:imum)?(?: of)?)\s+(\d+|one|two|three)\s+decimals?", re.I)
_SIZE_MAX = re.compile(rf"{_NUM}\s*(B|KB|MB|GB|bytes?)\s+or (?:smaller|less)|(?:at most|up to|max(?:imum)?(?: of)?|no larger than|not exceed(?:ing)?)\s+{_NUM}\s*(B|KB|MB|GB|bytes?)|(?:over|larger than|bigger than|exceeding)\s+{_NUM}\s*(B|KB|MB|GB|bytes?)", re.I)
_WHOLE = re.compile(r"\b(?:whole number|integer)\b", re.I)
_NON_NEG = re.compile(r"\b(?:zero or more|non-?negative|must not be negative)\b", re.I)
_POSITIVE = re.compile(r"\bpositive (?:number|amount|value|integer)\b|\bgreater than zero\b", re.I)
_REQUIRED = re.compile(r"\b(?:is|are) required\b|\bmandatory\b|\bmust not be (?:empty|blank)\b|\bcannot be (?:empty|blank)\b", re.I)
_OPTIONAL = re.compile(r"\b(?:is|are) optional\b", re.I)
_ONE_OF = re.compile(r"\bmust be one of\s+(.+?)(?:\s*\(|[;.]|$)", re.I)
_FILE_TYPES = re.compile(r"\b(?:only\s+)?((?:[A-Z]{2,5})(?:\s*(?:,|or|and)\s*[A-Z]{2,5})*)\s+files?\b")
_QUOTED = re.compile(r"\"([^\"]{3,160})\"|“([^”]{3,160})”")
_DATE = r"(\d{4}-\d{2}-\d{2})"
_DATE_RANGE = re.compile(rf"between\s+{_DATE}\s+and\s+{_DATE}|from\s+{_DATE}\s+to\s+{_DATE}", re.I)
_DATE_MIN = re.compile(rf"(?:on or after|not before|from)\s+{_DATE}", re.I)
_DATE_MAX = re.compile(rf"(?:on or before|not after|until|up to)\s+{_DATE}", re.I)


def _num(s: str) -> Any:
    s = s.strip().lower()
    if s in _WORD_NUM:
        return _WORD_NUM[s]
    v = float(s)
    return int(v) if v.is_integer() else v


def _bytes(value: str, unit: str) -> int:
    return int(float(value) * _UNIT_BYTES[unit.lower().rstrip("s") if unit.lower() not in _UNIT_BYTES else unit.lower()])


def parse_constraints(text: str) -> Dict[str, Dict[str, Any]]:
    """Constraints stated in one sentence/clause. Keys: length, range, size, decimals, required, options,
    accept, date. Values are plain dicts (the caller adds `source`)."""
    out: Dict[str, Dict[str, Any]] = {}
    if not text:
        return out
    raw = text.replace(" ", " ").replace(" ", " ")
    t = re.sub(_DATE, " DATE ", raw)          # "2024-01-01" must not read as the numeric range 2024–1

    length: Dict[str, Any] = {}
    m = _LEN_RANGE.search(t)
    if m:
        length = {"min": _num(m.group(1)), "max": _num(m.group(2))}
    for rx, key in ((_LEN_MAX, "max"), (_LEN_MIN, "min")):
        m = rx.search(t)
        if m and key not in length:
            length[key] = _num(m.group(1))
    m = _LEN_OVER.search(t)
    if m and "max" not in length:
        length["max"] = _num(m.group(1)) - 1
    m = _LEN_EXACT.search(t)
    if m:
        length["boundary"] = _num(m.group(1))
    if length:
        out["length"] = length

    rng: Dict[str, Any] = {}
    m = _RANGE.search(t)
    if m and "length" not in out:
        rng = {"min": _num(m.group(1)), "max": _num(m.group(2))}
    if _NON_NEG.search(t):
        rng.setdefault("min", 0)
    elif _POSITIVE.search(t):
        rng.setdefault("min", 0)
        rng["min_exclusive"] = True
    if "min" not in rng:
        m = _MIN_WORD.search(t) or _MIN_NUM.search(t)
        if m and not _LEN_OVER.search(t):
            rng["min"] = _num(m.group(1))
    if "max" not in rng:
        m = _MAX_NUM.search(t)
        if m and "length" not in out:
            rng["max"] = _num(m.group(1))
    if rng and _WHOLE.search(t):
        rng["integer"] = True
    if rng:
        out["range"] = rng

    m = _DECIMALS.search(t)
    if m:
        out["decimals"] = {"max": _num(m.group(1))}

    m = _SIZE_MAX.search(t)
    if m:
        g = m.groups()
        if g[0]:
            out["size"] = {"max": _bytes(g[0], g[1])}
        elif g[2]:
            out["size"] = {"max": _bytes(g[2], g[3])}
        else:
            out["size"] = {"max": _bytes(g[4], g[5])}

    if _REQUIRED.search(t):
        out["required"] = {"value": True}
    elif _OPTIONAL.search(t):
        out["required"] = {"value": False}

    m = _ONE_OF.search(t)
    if m:
        opts = [o.strip(" `'\"") for o in re.split(r",\s*|\s+or\s+|\s+and\s+", m.group(1)) if o.strip(" `'\"")]
        if len(opts) >= 2:
            out["options"] = {"values": opts}

    m = _FILE_TYPES.search(t)
    if m and re.search(r"\bfiles?\b", t, re.I):
        exts = [e.lower() for e in re.findall(r"[A-Z]{2,5}", m.group(1)) if e not in ("MB", "KB", "GB", "OR", "AND")]
        if exts:
            out["accept"] = {"values": ["." + e for e in exts]}

    dates: Dict[str, Any] = {}
    m = _DATE_RANGE.search(raw)
    if m:
        g = [x for x in m.groups() if x]
        dates = {"min": g[0], "max": g[1]}
    else:
        m1, m2 = _DATE_MIN.search(raw), _DATE_MAX.search(raw)
        if m1:
            dates["min"] = m1.group(1)
        if m2:
            dates["max"] = m2.group(1)
    if dates:
        out["date"] = dates
    return out


def quoted_messages(text: str) -> List[str]:
    """Literal UI messages quoted in a statement (straight or curly double quotes), in order, de-duplicated."""
    seen: List[str] = []
    for m in _QUOTED.finditer(text or ""):
        msg = (m.group(1) or m.group(2) or "").strip()
        if msg and msg not in seen and not re.fullmatch(r"[\w./-]+", msg):   # skip bare tokens like "mouse"
            seen.append(msg)
    return seen


def message_kind(message: str) -> Optional[str]:
    """Classify an error message by the constraint it reports (matches form_model observed_messages keys)."""
    t = (message or "").lower()
    if not t:
        return None
    if "required" in t or "please choose" in t or "please fill" in t or "please select" in t:
        return "required_missing"
    if re.search(r"at most \d+ (?:characters|chars)|too long|maximum length", t):
        return "too_long"
    if re.search(r"at least \d+ (?:characters|chars)|too short", t):
        return "too_short"
    if "between" in t or "zero or more" in t or "greater" in t or "less than" in t or "range" in t:
        return "out_of_range"
    if "decimal" in t or "number" in t or "numeric" in t:
        return "wrong_type"
    if "files are allowed" in t or "file type" in t or "only" in t and "file" in t:
        return "wrong_accept"
    if re.search(r"\d+\s*(?:mb|kb|gb)\b", t) or "smaller" in t or "too large" in t:
        return "too_large"
    return None


def split_clauses(statement: str) -> List[str]:
    """Clauses of a statement, split on ';' and sentence ends (never inside quotes)."""
    parts: List[str] = []
    buf, in_q = [], False
    for ch in statement or "":
        if ch in "\"“”":
            in_q = not in_q if ch == "\"" else (ch == "“")
        if not in_q and ch == ";":
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
        if not in_q and ch == "." and len(buf) > 1:
            parts.append("".join(buf))
            buf = []
    if buf:
        parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip(" .")]
