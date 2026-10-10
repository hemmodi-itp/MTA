"""
extract.py — BRD text → quote-verified, classified, atomic requirements (Phase 1.1).

Pipeline (design §4.2):
  1. explicit.parse()      criteria the document declares with its own ids (deterministic, exact quotes)
  2. one LLM call          classify declared criteria, split compound ones, add undeclared ones
                           (output validated against LlmRequirementsResponse; one repair retry)
  3. merge                 declared items are authoritative for id/text/quote; the LLM can add, never drop
  4. quote verification    BrdIndex.quote_match(); an LLM-added item without a matching quote is rejected
  5. atomicity check       deterministic; a split is kept only if every child is grounded in its parent
  6. classification        risk tags, priority precedence, testability (classify.py)

Never raises into the caller for LLM problems: without a usable LLM answer the declared criteria are kept
with heuristic classification (status "degraded"); with neither, status is "failed" with the reason.
"""

import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from pydantic import ValidationError

from tools.requirements import atomicity, classify, explicit
from tools.requirements.brd_index import BrdIndex
from tools.requirements.ids import IdAllocator
from tools.requirements.models import (
    LLM_RESPONSE_JSON_SCHEMA,
    AcceptanceCriterion,
    LlmCriterion,
    LlmRequirement,
    LlmRequirementsResponse,
    Rejected,
    ReqWarning,
    Requirement,
)
from tools.requirements.prompts import REQUIREMENTS_EXTRACTION_PROMPT, VALIDATION_RETRY_SUFFIX

MAX_BRD_CHARS = 150_000
DOM_INFERRED_MAX_CONFIDENCE = 0.6
# Two statements are "the same criterion" when one restates ≥ this share of the other's content words.
SAME_CRITERION_SUPPORT = 0.8
TRANSIENT_RETRY_DELAY_S = 5
_WONT = re.compile(r"\b(?:priority|moscow)\s*[:=]?\s*(?:won['’]?t|will not)\b", re.IGNORECASE)
_REQ_ID = re.compile(r"^REQ-\d+$")
_AC_ID = re.compile(r"^AC-\d+\.\d+$")


@dataclass
class ExtractionResult:
    requirements: List[Requirement] = field(default_factory=list)
    rejected: List[Rejected] = field(default_factory=list)
    warnings: List[ReqWarning] = field(default_factory=list)
    status: str = "ok"
    limitations: List[str] = field(default_factory=list)


def _clean(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _same(a: str, b: str) -> bool:
    return BrdIndex(a).support(b) >= SAME_CRITERION_SUPPORT and BrdIndex(b).support(a) >= SAME_CRITERION_SUPPORT


# ── LLM call ─────────────────────────────────────────────────────────────────

def _declared_block(reqs: List[explicit.ExplicitRequirement]) -> str:
    lines = []
    for r in reqs:
        for c in r.criteria:
            lines.append(f"- {c.id} ({r.id} {r.title}): {c.statement}")
    return "\n".join(lines) or "(none)"


def call_llm(llm, text: str, declared: List[explicit.ExplicitRequirement], module_label: str) -> LlmRequirementsResponse:
    """One extraction call, schema-validated; one repair retry with the validation errors. Raises on failure."""
    from tools.agent_eval.llm_json import generate_json   # imported lazily: pulls in the connector stack

    prompt = REQUIREMENTS_EXTRACTION_PROMPT.substitute(
        brd_text=text, declared=_declared_block(declared), module_label=module_label or "(whole document)")
    try:
        raw = generate_json(llm, prompt, required_keys=["requirements"], schema=LLM_RESPONSE_JSON_SCHEMA)
    except ValueError:
        raise           # unparseable output: generate_json already retried once
    except Exception:   # a transient connector error (server / network) after the connector's own retries
        time.sleep(TRANSIENT_RETRY_DELAY_S)
        raw = generate_json(llm, prompt, required_keys=["requirements"], schema=LLM_RESPONSE_JSON_SCHEMA)
    try:
        return LlmRequirementsResponse.model_validate(raw)
    except ValidationError as exc:
        retry = prompt + VALIDATION_RETRY_SUFFIX.format(errors=str(exc)[:1500])
        raw = generate_json(llm, retry, required_keys=["requirements"], schema=LLM_RESPONSE_JSON_SCHEMA)
        return LlmRequirementsResponse.model_validate(raw)


# ── building criteria ────────────────────────────────────────────────────────

class _Builder:
    def __init__(self, text: str, source: str, allocator: IdAllocator, module_id: Optional[str],
                 reserved: Dict[str, str]):
        self.index = BrdIndex(text)
        self.text = text
        self.source = source
        self.allocator = allocator
        self.module_id = module_id
        self.reserved = reserved            # ids used by OTHER modules → their statement/title
        self.result = ExtractionResult()

    # ids
    def _doc_id_usable(self, doc_id: Optional[str], content: str, pattern: "re.Pattern[str]") -> bool:
        if not doc_id or not pattern.match(doc_id) or doc_id not in self.text:
            return False
        other = self.reserved.get(doc_id)
        return other is None or _same(other, content)

    def requirement_id(self, doc_id: Optional[str], title: str, description: str, taken: List[str]) -> str:
        if self._doc_id_usable(doc_id, title, _REQ_ID) and doc_id not in taken:
            return doc_id
        if doc_id and doc_id in self.reserved:
            self.warn(doc_id, "id_collision", f"{doc_id} is already used by another module; re-keyed")
        foreign = [r for r in self.reserved if _REQ_ID.match(r)]
        return self.allocator.requirement_id(title, description, taken_ids=taken + foreign)

    def criterion_id(self, doc_id: Optional[str], req_id: str, statement: str, taken: List[str]) -> str:
        if (self._doc_id_usable(doc_id, statement, _AC_ID) and doc_id not in taken
                and doc_id.split("-", 1)[1].split(".")[0] == req_id.split("-", 1)[1]):
            return doc_id
        if doc_id and doc_id in self.reserved:
            self.warn(doc_id, "id_collision", f"{doc_id} is already used by another module; re-keyed")
        prefix = "AC-" + req_id.split("-", 1)[1] + "."
        foreign = [r for r in self.reserved if r.startswith(prefix) and _AC_ID.match(r)]
        return self.allocator.criterion_id(req_id, statement, taken_ids=taken + foreign)

    def warn(self, ident: Optional[str], kind: str, detail: str = "") -> None:
        self.result.warnings.append(ReqWarning(id=ident, module_id=self.module_id, kind=kind, detail=detail))

    def reject(self, statement: str, reason: str) -> None:
        self.result.rejected.append(Rejected(module_id=self.module_id, statement=statement[:600], reason=reason))

    # classification
    def classify(self, statement: str, req_title: str, llm_c: Optional[LlmCriterion],
                 llm_req_priority: Optional[str]) -> Dict[str, Any]:
        text = f"{statement} {req_title}"
        tags = classify.risk_tags_for(text, llm_c.risk_tags if llm_c else None)
        testability, reason, t_src = classify.resolve_testability(
            llm_c.testability if llm_c else None, llm_c.testability_reason if llm_c else None, statement)
        priority, p_src = classify.resolve_priority(
            classify.stated_priority(statement), (llm_c.priority if llm_c else None) or llm_req_priority, tags)
        if _WONT.search(statement):
            testability, reason = "not_testable", "out of scope: the document marks it Won't"
        return {"testability": testability, "testability_reason": reason, "priority": priority,
                "priority_source": p_src, "risk_tags": tags,
                "classification_source": "llm" if (llm_c and t_src == "llm") else "heuristic"}

    def confidence(self, quote_match: str, classification_source: str) -> float:
        conf = {"exact": 1.0, "fuzzy": 0.9}.get(quote_match, 0.7)
        if classification_source == "heuristic":
            conf = min(conf, 0.7)
        if self.source == "dom_inferred":
            conf = min(conf, DOM_INFERRED_MAX_CONFIDENCE)
        return round(conf, 2)

    def duplicate_of_other_module(self, statement: str) -> Optional[str]:
        """Id of another module's criterion this one restates (shared BRD sections repeat in every module)."""
        for other_id, other in self.reserved.items():
            if other_id.startswith("AC-") and _same(statement, other):
                return other_id
        return None

    def build_criteria(self, ac_id: str, doc_id: Optional[str], statement: str, quote: str, req_title: str,
                       llm_c: Optional[LlmCriterion], llm_req_priority: Optional[str],
                       declared: bool) -> List[AcceptanceCriterion]:
        """The criterion, plus its atomic children when the LLM's split is valid. [] when rejected."""
        if not declared:
            dup = self.duplicate_of_other_module(statement)
            if dup:
                self.warn(dup, "duplicate_of_other_module", f"not re-added: {statement[:200]}")
                return []
        qm = "exact" if declared else self.index.quote_match(quote)
        if qm == "none" and not declared:
            qm = self.index.quote_match(statement)
            quote = statement if qm != "none" else quote
        if qm == "none":
            self.reject(statement, "quote_not_found")
            return []
        cls = self.classify(statement, req_title, llm_c, llm_req_priority)
        atomic, issues = atomicity.check(statement)
        base = dict(source=self.source, source_quote=quote[:600], quote_match=qm, quote_verified=True,
                    **cls)
        children = self._children(ac_id, statement, llm_c, base, req_title)
        parent = AcceptanceCriterion(
            id=ac_id, doc_id=doc_id, statement=statement, support=round(self.index.support(statement), 3),
            atomic=atomic and not children, atomicity_issues=issues if not children else (issues or ["split"]),
            children=[c.id for c in children], confidence=self.confidence(qm, cls["classification_source"]), **base)
        if not atomic and not children:
            self.warn(ac_id, "non_atomic_not_split", ", ".join(issues))
        return [parent] + children

    def _children(self, parent_id: str, statement: str, llm_c: Optional[LlmCriterion], base: Dict[str, Any],
                  req_title: str) -> List[AcceptanceCriterion]:
        parts = [_clean(s) for s in (llm_c.split if llm_c else []) if _clean(s)]
        parts = list(dict.fromkeys(parts))
        if len(parts) < 2:
            return []
        parent_index = BrdIndex(statement)
        if not all(parent_index.criterion_grounded(p) for p in parts):
            self.warn(parent_id, "split_rejected", "a split part is not grounded in the criterion's own words")
            return []
        out, taken = [], []
        for part in parts:
            cid = self.allocator.child_id(parent_id, part, taken_ids=taken)
            taken.append(cid)
            atomic, issues = atomicity.check(part)
            tags = classify.risk_tags_for(f"{part} {req_title}", base["risk_tags"])
            child = {**base, "risk_tags": tags}
            out.append(AcceptanceCriterion(
                id=cid, parent_id=parent_id, statement=part, support=round(self.index.support(part), 3),
                atomic=atomic, atomicity_issues=issues,
                confidence=self.confidence(base["quote_match"], base["classification_source"]), **child))
        return out


# ── public entry point ───────────────────────────────────────────────────────

def extract_requirements(text: str, llm=None, *, allocator: IdAllocator, module_id: Optional[str] = None,
                         module_label: str = "", source: str = "brd", patterns: Optional[Dict[str, str]] = None,
                         reserved: Optional[Dict[str, str]] = None, logger=None) -> ExtractionResult:
    """Requirements of one BRD (one module). `reserved` = ids other modules already use → their text."""
    reserved = dict(reserved or {})
    limitations: List[str] = []
    if len(text or "") > MAX_BRD_CHARS:
        limitations.append(f"The BRD is longer than {MAX_BRD_CHARS} characters; only the start was analysed.")
        text = text[:MAX_BRD_CHARS]

    declared = explicit.parse(text, patterns)
    llm_resp: Optional[LlmRequirementsResponse] = None
    if llm is not None:
        try:
            llm_resp = call_llm(llm, text, declared, module_label)
        except Exception as exc:   # LLM unavailable or unusable → degrade, never fail comprehension
            limitations.append(f"Requirement extraction LLM call failed ({type(exc).__name__}: "
                               f"{str(exc)[:200]}); declared criteria kept with heuristic classification.")
            if logger:
                logger.warning(f"[requirements] LLM extraction failed for {module_id or 'project'}: {exc}")
    else:
        limitations.append("No LLM available; declared criteria kept with heuristic classification.")

    b = _Builder(text, source, allocator, module_id, reserved)
    llm_reqs: List[LlmRequirement] = list(llm_resp.requirements) if llm_resp else []
    _merge(b, declared, llm_reqs)

    res = b.result
    res.limitations = limitations
    if not res.requirements:
        res.status = "failed"
        limitations.append("No requirements could be extracted from this document.")
    else:
        res.status = "ok" if llm_resp is not None else "degraded"
    return res


def _seen(b: "_Builder", statement: str, current: List[AcceptanceCriterion]) -> bool:
    """Already extracted for this module (in this requirement or an earlier one)?"""
    earlier = [c for r in b.result.requirements for c in r.acceptance_criteria]
    return any(_same(statement, c.statement) for c in current + earlier)


def _match_llm_req(er: explicit.ExplicitRequirement, llm_reqs: List[LlmRequirement], used: set) -> Optional[int]:
    for i, lr in enumerate(llm_reqs):
        if i not in used and _clean(lr.id).upper() == er.id.upper():
            return i
    for i, lr in enumerate(llm_reqs):
        if i not in used and lr.title and er.title and _same(lr.title, er.title):
            return i
    return None


def _all_llm_criteria(llm_reqs: List[LlmRequirement]) -> List[Tuple[int, int, LlmCriterion]]:
    return [(i, j, c) for i, lr in enumerate(llm_reqs) for j, c in enumerate(lr.acceptance_criteria)]


def _merge(b: _Builder, declared: List[explicit.ExplicitRequirement], llm_reqs: List[LlmRequirement]) -> None:
    used_reqs: set = set()
    used_crit: set = set()
    req_ids: List[str] = []
    all_llm_c = _all_llm_criteria(llm_reqs)

    def find_llm_criterion(ec: explicit.ExplicitCriterion) -> Optional[LlmCriterion]:
        for i, j, c in all_llm_c:
            if (i, j) not in used_crit and _clean(c.id).upper() == ec.id.upper():
                used_crit.add((i, j))
                return c
        for i, j, c in all_llm_c:
            if (i, j) not in used_crit and not _clean(c.id) and _same(c.statement, ec.statement):
                used_crit.add((i, j))
                return c
        return None

    # 1) declared requirements: authoritative ids, text and quotes
    for er in declared:
        li = _match_llm_req(er, llm_reqs, used_reqs)
        lr = llm_reqs[li] if li is not None else None
        if li is not None:
            used_reqs.add(li)
        title = er.title if not er.synthesised else (lr.title if lr else er.title)
        description = er.description or _clean(lr.description if lr else "")
        rid = b.requirement_id(er.id, title, description, req_ids)
        req_ids.append(rid)
        criteria: List[AcceptanceCriterion] = []
        for ec in er.criteria:
            lc = find_llm_criterion(ec)
            cid = b.criterion_id(ec.id, rid, ec.statement, [c.id for c in criteria])
            criteria += b.build_criteria(cid, ec.id, ec.statement, ec.statement, title, lc,
                                         lr.priority if lr else None, declared=True)
        # LLM additions inside the matched requirement
        if lr is not None:
            for j, lc in enumerate(lr.acceptance_criteria):
                if (li, j) in used_crit:
                    continue
                used_crit.add((li, j))
                if _seen(b, lc.statement, criteria):
                    continue    # a restatement of a criterion already extracted for this module
                cid = b.criterion_id(_clean(lc.id) or None, rid, lc.statement, [c.id for c in criteria])
                criteria += b.build_criteria(cid, None, _clean(lc.statement), _clean(lc.source_quote), title, lc,
                                             lr.priority, declared=False)
        quote = description or title
        b.result.requirements.append(Requirement(
            id=rid, doc_id=er.id, module_id=b.module_id, title=title, description=description,
            source=b.source, source_quote=quote[:600], quote_match=b.index.quote_match(quote) if quote else "none",
            acceptance_criteria=criteria))

    # 2) requirements only the LLM found
    for i, lr in enumerate(llm_reqs):
        if i in used_reqs:
            continue
        title, description = _clean(lr.title), _clean(lr.description)
        quote = _clean(lr.source_quote)
        qm = b.index.quote_match(quote)
        if qm == "none":
            qm = b.index.quote_match(description)
            quote = description if qm != "none" else quote
        if qm == "none":
            b.reject(title + (f": {description}" if description else ""), "quote_not_found")
            continue
        rid = b.requirement_id(_clean(lr.id) or None, title, description, req_ids)
        criteria = []
        for j, lc in enumerate(lr.acceptance_criteria):
            if (i, j) in used_crit:
                continue
            used_crit.add((i, j))
            if _seen(b, lc.statement, criteria):
                continue
            cid = b.criterion_id(_clean(lc.id) or None, rid, lc.statement, [c.id for c in criteria])
            criteria += b.build_criteria(cid, None, _clean(lc.statement), _clean(lc.source_quote), title, lc,
                                         lr.priority, declared=False)
        if not criteria and not _seen(b, quote, []):
            # A requirement with no criteria is checked against its own verified BRD text — never against the
            # LLM's summary of it, which is not document text.
            cid = b.criterion_id(None, rid, quote, [])
            criteria = b.build_criteria(cid, None, quote, quote, title, None, lr.priority, declared=False)
        if not criteria:
            if not any(w.kind == "duplicate_of_other_module" for w in b.result.warnings):
                b.reject(title, "no_verifiable_criteria")
            continue
        req_ids.append(rid)
        b.result.requirements.append(Requirement(
            id=rid, doc_id=rid if _clean(lr.id) == rid else None, module_id=b.module_id,
            title=title, description=description, source=b.source, source_quote=quote[:600], quote_match=qm,
            acceptance_criteria=criteria))
