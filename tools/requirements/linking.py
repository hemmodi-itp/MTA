"""
linking.py — attach acceptance-criterion ids to scenarios and to generated tests (Phase 1.1 / 1.3).

Scenarios:  the LLM's `ac_ids` (validated: known ids only, a split parent expands to its atomic children),
            else a deterministic similarity backfill against the module's leaf criteria
            (`ac_link_source`: "llm" | "similarity").
Tests:      the plan test's `ac_ids` restricted to its scenario's ACs ("direct"), else similarity between the
            test and its scenario's ACs ("similarity"), else the scenario's ACs ("inherited", design D2),
            else none — the test is reported as unlinked, never given a fabricated link.
"""

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from tools.requirements.brd_index import BrdIndex
from tools.requirements.models import AcceptanceCriterion, RequirementsDoc

SCENARIO_LINK_THRESHOLD = 0.5
TEST_LINK_THRESHOLD = 0.5
TEST_BEST_MATCH_MIN = 0.3
TEST_LINK_MARGIN = 0.15
REQ_HINT_BONUS = 0.2
MAX_SIMILARITY_LINKS = 5


def _text(*parts: Any) -> str:
    out = []
    for p in parts:
        if isinstance(p, (list, tuple)):
            out.extend(str(x) for x in p)
        elif p:
            out.append(str(p))
    return " ".join(out)


def scenario_text(sc: Dict[str, Any]) -> str:
    return _text(sc.get("title"), sc.get("business_objective"), sc.get("steps"), sc.get("expected_result"),
                 sc.get("preconditions"))


def _req_hints(sc: Dict[str, Any]) -> set:
    hints = set()
    for t in sc.get("traceability") or []:
        if isinstance(t, dict) and t.get("requirement_id"):
            hints.add(str(t["requirement_id"]).strip().upper())
    return hints


def criteria_index(doc: RequirementsDoc) -> Dict[str, AcceptanceCriterion]:
    return {ac.id: ac for ac in doc.criteria()}


def expand_to_leaves(ids: Iterable[str], index: Dict[str, AcceptanceCriterion]) -> Tuple[List[str], List[str]]:
    """(valid leaf ids in input order, dropped unknown ids). A split parent expands to its children."""
    leaves: List[str] = []
    dropped: List[str] = []
    for raw in ids or []:
        ac = index.get(str(raw).strip().upper())
        if ac is None:
            dropped.append(str(raw))
            continue
        for leaf in (ac.children or [ac.id]):
            if leaf not in leaves:
                leaves.append(leaf)
    return leaves, dropped


def similarity_scores(text: str, leaves: Sequence[AcceptanceCriterion], req_of: Dict[str, str],
                      hints: Optional[set] = None) -> List[Tuple[str, float]]:
    index = BrdIndex(text)
    scored = []
    for ac in leaves:
        score = index.support(ac.statement)
        rid = req_of.get(ac.id)
        if hints and rid and (rid.upper() in hints):
            score += REQ_HINT_BONUS
        scored.append((ac.id, round(score, 3)))
    return sorted(scored, key=lambda x: -x[1])


def _module_leaves(doc: RequirementsDoc, module_id: Optional[str]) -> List[AcceptanceCriterion]:
    leaves = doc.leaf_criteria(module_id) if module_id else []
    return leaves or doc.leaf_criteria()


def _req_ids(doc: RequirementsDoc) -> Dict[str, str]:
    """AC id → the requirement's id and doc id (either may appear in a scenario's traceability)."""
    out = {}
    for r in doc.requirements:
        for ac in r.acceptance_criteria:
            out[ac.id] = r.doc_id or r.id
    return out


def link_scenario(sc: Dict[str, Any], doc: RequirementsDoc, module_id: Optional[str] = None) -> Dict[str, Any]:
    """Return a copy of the scenario dict with `ac_ids` and `ac_link_source` set (or absent when unlinkable)."""
    out = dict(sc)
    index = criteria_index(doc)
    valid, _ = expand_to_leaves(sc.get("ac_ids") or [], index)
    if valid:
        out["ac_ids"] = valid
        out["ac_link_source"] = sc.get("ac_link_source") if sc.get("ac_link_source") in ("llm", "similarity") \
            else "llm"
        return out
    module_leaves = _module_leaves(doc, sc.get("module_id") or module_id)
    picked = _similar(sc, module_leaves, doc)
    if not picked and len(module_leaves) < len(doc.leaf_criteria()):
        # Shared BRD sections (an API or non-functional chapter copied into every module's document) produce
        # scenarios about another module's criteria — look project-wide before giving up.
        picked = _similar(sc, doc.leaf_criteria(), doc)
    out.pop("ac_ids", None)
    out.pop("ac_link_source", None)
    if picked:
        out["ac_ids"] = picked
        out["ac_link_source"] = "similarity"
    return out


def _similar(sc: Dict[str, Any], leaves: Sequence[AcceptanceCriterion], doc: RequirementsDoc) -> List[str]:
    scored = similarity_scores(scenario_text(sc), leaves, _req_ids(doc), _req_hints(sc))
    return [i for i, s in scored if s >= SCENARIO_LINK_THRESHOLD][:MAX_SIMILARITY_LINKS]


def link_scenarios(scenarios: List[Dict[str, Any]], doc: Optional[RequirementsDoc],
                   module_id: Optional[str] = None) -> List[Dict[str, Any]]:
    if doc is None or not doc.requirements:
        return scenarios
    return [link_scenario(sc, doc, module_id) for sc in scenarios]


_STEP_TEXT_KEYS = ("message", "value", "text", "expected", "url", "locator_key")


def test_text(test: Dict[str, Any]) -> str:
    parts = [test.get("name"), test.get("type")]
    for step in test.get("steps") or []:
        if isinstance(step, dict):
            parts += [step.get(k) for k in _STEP_TEXT_KEYS if isinstance(step.get(k), str)]
    return re.sub(r"[_-]+", " ", _text(*parts))


def link_test(test: Dict[str, Any], scenario_ac_ids: Sequence[str],
              index: Dict[str, AcceptanceCriterion]) -> Tuple[List[str], str]:
    """(ac_ids, link) for one plan test. link ∈ direct | similarity | inherited | "" (unlinked)."""
    allowed = list(scenario_ac_ids or [])
    proposed, _ = expand_to_leaves(test.get("ac_ids") or [], index)
    direct = [a for a in proposed if a in allowed]
    if direct:
        return direct, "direct"
    leaves = [index[a] for a in allowed if a in index]
    if leaves:
        scored = similarity_scores(test_text(test), leaves, {}, None)
        best = scored[0][1] if scored else 0.0
        # Sibling criteria share most words ("50 accepted" / "51 rejected"): keep only those close to the best.
        picked = [i for i, s in scored if s >= TEST_LINK_THRESHOLD and s >= best - TEST_LINK_MARGIN]
        if not picked and scored and scored[0][1] >= TEST_BEST_MATCH_MIN and \
                (len(scored) == 1 or scored[0][1] > scored[1][1]):
            picked = [scored[0][0]]
        if picked:
            return picked[:MAX_SIMILARITY_LINKS], "similarity"
    if allowed:
        return allowed, "inherited"
    return [], ""
