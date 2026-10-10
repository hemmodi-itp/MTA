"""
explicit.py — deterministic parser for requirements and acceptance criteria a document declares with its own ids.

    ### REQ-03 Product management            → requirement REQ-03, title "Product management"
    Signed-in users can add, edit …           → its description (until the first criterion)
    - AC-03.2: Name must be 1–50 characters…  → criterion AC-03.2 (wrapped continuation lines are joined)

Document ids are canonical when present (design R2): testers recognise them and benchmark ground truth uses them.
Each statement is the document's own text, so its source_quote is exact by construction. Patterns can be
overridden per project (`requirements.doc_id_patterns`), as regexes with named groups `id` and `text`.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

DEFAULT_REQUIREMENT_PATTERN = r"^\s{0,3}(?:#{1,6}\s*|\*\*)?(?P<id>REQ-\d+)\b\**\s*[:.\-–—]?\s*(?P<text>.*)$"
DEFAULT_CRITERION_PATTERN = (
    r"^\s*(?:[-*+]|\d+[.)])?\s*\**(?P<id>AC-\d+(?:\.\d+){1,2})\**\s*[:.\-–—]\s*(?P<text>.+)$"
)
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s")
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")


@dataclass
class ExplicitCriterion:
    id: str
    statement: str
    line_no: int


@dataclass
class ExplicitRequirement:
    id: str
    title: str
    description: str = ""
    line_no: int = 0
    synthesised: bool = False      # criteria appeared with no declared requirement heading
    criteria: List[ExplicitCriterion] = field(default_factory=list)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def parse(text: str, patterns: Optional[Dict[str, str]] = None) -> List[ExplicitRequirement]:
    """Requirements in document order, each with its declared criteria. Never raises on odd input."""
    patterns = patterns or {}
    req_re = re.compile(patterns.get("requirement") or DEFAULT_REQUIREMENT_PATTERN)
    ac_re = re.compile(patterns.get("criterion") or DEFAULT_CRITERION_PATTERN)

    reqs: List[ExplicitRequirement] = []
    current: Optional[ExplicitRequirement] = None
    open_ac: Optional[ExplicitCriterion] = None
    desc_lines: List[str] = []

    def close_description() -> None:
        if current is not None and desc_lines and not current.description:
            current.description = _clean(" ".join(desc_lines))
        desc_lines.clear()

    for n, line in enumerate((text or "").splitlines(), start=1):
        m_ac = ac_re.match(line)
        if m_ac:
            ac_id = m_ac.group("id")
            if current is None or not _belongs(ac_id, current.id):
                req_id = "REQ-" + ac_id.split("-", 1)[1].split(".")[0]
                existing = next((r for r in reqs if r.id == req_id), None)
                if existing is None:
                    close_description()
                    existing = ExplicitRequirement(id=req_id, title=f"Requirement {req_id}", line_no=n,
                                                   synthesised=True)
                    reqs.append(existing)
                current = existing
            close_description()
            open_ac = ExplicitCriterion(id=ac_id, statement=_clean(m_ac.group("text")), line_no=n)
            current.criteria.append(open_ac)
            continue

        m_req = req_re.match(line)
        if m_req:
            close_description()
            open_ac = None
            title = _clean(m_req.group("text")).strip("*").strip() or m_req.group("id")
            current = ExplicitRequirement(id=m_req.group("id"), title=title, line_no=n)
            reqs.append(current)
            continue

        stripped = line.strip()
        if not stripped or _HEADING.match(line):
            open_ac = None
            if _HEADING.match(line):
                close_description()
                current = None if current is not None and current.criteria else current
            continue
        if open_ac is not None and not _BULLET.match(line):
            open_ac.statement = _clean(f"{open_ac.statement} {stripped}")   # wrapped bullet continuation
            continue
        open_ac = None
        if current is not None and not current.criteria:
            desc_lines.append(stripped)

    close_description()
    return _dedupe(reqs)


def _belongs(ac_id: str, req_id: str) -> bool:
    return ac_id.split("-", 1)[1].split(".")[0] == req_id.split("-", 1)[1]


def _dedupe(reqs: List[ExplicitRequirement]) -> List[ExplicitRequirement]:
    """A document that repeats a criterion id (e.g. in a summary table) keeps its first definition."""
    seen = set()
    for r in reqs:
        kept = []
        for c in r.criteria:
            if c.id not in seen and c.statement:
                seen.add(c.id)
                kept.append(c)
        r.criteria = kept
    return [r for r in reqs if r.criteria or not r.synthesised]
