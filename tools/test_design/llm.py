"""
llm.py — the one schema-validated LLM call per module (Phase 3.3), plus the hint sanitiser.

    interpret_module(llm, inp, module_id, unlinked)  → DesignHints (validated; one repair retry) or raises
    sanitize(hints, inp, module_id, unlinked_ids)    → plain-dict hints with every reference checked:
        unknown / other-module / non-UI AC ids dropped, links only for listed cases, rules whose `then` is not an
        action dropped, extra cases without a valid AC dropped. The LLM can add; it can never remove.
"""

import time
from typing import Any, Dict, List

from pydantic import ValidationError

from tools.test_design.inputs import DesignInputs
from tools.test_design.models import DesignHints
from tools.test_design.prompts import TEST_DESIGN_PROMPT, VALIDATION_RETRY_SUFFIX

TRANSIENT_RETRY_DELAY_S = 5
MAX_UNLINKED_IN_PROMPT = 40


def _criteria_block(inp: DesignInputs, module_id: str) -> str:
    return "\n".join(f"- {a['id']}: {a['statement']}" for a in inp.testable_acs() if a["module_id"] == module_id)


def interpret_module(llm, inp: DesignInputs, module_id: str, unlinked: List[Dict[str, Any]]) -> DesignHints:
    from tools.agent_eval.llm_json import generate_json   # lazy: pulls in the connector stack

    unl = "\n".join(f"- {c['id']}: {c['title']}" for c in unlinked[:MAX_UNLINKED_IN_PROMPT]) or "(none)"
    name = next((m["name"] for m in inp.modules if m["id"] == module_id), module_id)
    prompt = TEST_DESIGN_PROMPT.substitute(module_label=f"{module_id} — {name}",
                                           criteria=_criteria_block(inp, module_id), unlinked=unl)
    try:
        raw = generate_json(llm, prompt, required_keys=["negative_paths"])
    except ValueError:
        raise
    except Exception:          # transient connector error after the connector's own retries
        time.sleep(TRANSIENT_RETRY_DELAY_S)
        raw = generate_json(llm, prompt, required_keys=["negative_paths"])
    try:
        return DesignHints.model_validate(raw)
    except ValidationError as exc:
        raw = generate_json(llm, prompt + VALIDATION_RETRY_SUFFIX.format(errors=str(exc)[:1500]),
                            required_keys=["negative_paths"])
        return DesignHints.model_validate(raw)


def sanitize(hints: DesignHints, inp: DesignInputs, module_id: str, unlinked_ids: List[str]) -> Dict[str, Any]:
    module_acs = {a["id"] for a in inp.testable_acs() if a["module_id"] == module_id}
    all_ui = {a["id"] for a in inp.testable_acs()}
    allowed_cases = set(unlinked_ids)
    out: Dict[str, Any] = {"decision_tables": [], "negative_paths": [], "ac_links": [], "extra_cases": []}
    for dt in hints.decision_tables:
        if dt.ac_id not in module_acs:
            continue
        conds = list(dict.fromkeys(dt.conditions))
        rules = [{"when": {k: v for k, v in r.when.items() if k in conds}, "then": r.then}
                 for r in dt.rules if r.then in dt.actions]
        rules = [r for r in rules if r["when"]]
        if len(conds) >= 2 and rules:
            out["decision_tables"].append({"ac_id": dt.ac_id, "conditions": conds, "actions": list(dt.actions),
                                           "rules": rules})
    for np_ in hints.negative_paths:
        if np_.ac_id in module_acs:
            out["negative_paths"].append({"ac_id": np_.ac_id, "has_negative_path": np_.has_negative_path})
    for link in hints.ac_links:
        ids = sorted(a for a in link.ac_ids if a in all_ui)
        if link.case_id in allowed_cases and ids:
            out["ac_links"].append({"case_id": link.case_id, "ac_ids": ids})
    for e in hints.extra_cases:
        ids = [a for a in e.ac_ids if a in module_acs]
        if ids:
            out["extra_cases"].append(dict(e.model_dump(), ac_ids=ids))
    return out


def merge_hints(parts: List[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"decision_tables": [], "negative_paths": [], "ac_links": [], "extra_cases": []}
    for p in parts:
        for k in out:
            out[k] += p.get(k) or []
    return out
