"""
rejection.py — the app's own validation rejecting the input of a test.

    INPUT_REJECTED.search(message)  "Please fill …", "X is required", "add at least one point … before generating"
    named_fields(message)           the fields such a message names, e.g. "…: Constraints, Dependencies." →
                                    ["Constraints", "Dependencies"]; [] when it names none

For a POSITIVE test the rejection means MTA's test data was incomplete, not that the app is wrong: the Playwright
Executor completes the named fields and submits once more, and the Pass/Fail Engine reports a rejection that
remains as inconclusive.
"""

import re
from typing import List

INPUT_REJECTED = re.compile(r"^\W{0,3}please (add|fill|enter|provide|complete|select)\b|\b(this field|field|value) is required\b|"
                            r"\bare required\b|\brequired fields?\b|\bcannot be (empty|blank)\b|\bmust not be empty\b|"
                            r"\bmissing (required )?fields?\b|\bat least one\b.{0,60}\bbefore\b|^\W{0,3}[\w '-]{1,40} (is|are) required\W*$", re.I)
_SINGLE = re.compile(r"^\W{0,3}([\w][\w &/'-]{0,60}?) (is|are) required\W*$", re.I)
MAX_NAMED = 8


def named_fields(message: str) -> List[str]:
    """Field names listed after the message's last colon ("…: A, B and C."), or the subject of "X is required"."""
    m = (message or "").strip()
    single = _SINGLE.match(m)
    if single:
        return [single.group(1).strip()]
    if ":" not in m:
        return []
    tail = m.rsplit(":", 1)[1].strip().rstrip(".!")
    names = [n.strip(" \"'“”") for n in re.split(r",|;|\band\b", tail)]
    names = [n for n in names if 0 < len(n) <= 60]
    return names[:MAX_NAMED] if len(tail) <= 400 else []
