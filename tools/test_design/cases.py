"""
cases.py — the one constructor every generator uses, plus the deterministic id, filler text and step-time estimate.

A generator returns plain dicts built by new_case(); design.py validates them into models.TestCase after risk and
selection. The id is a hash of the content `key` (never a counter), so the same input always yields the same ids
and an unchanged case keeps its id when other cases come and go.
"""

import hashlib
import json
from typing import Any, Dict, Iterable, List, Optional

from tools.test_design.inputs import Field, Form


def case_id(key: str) -> str:
    return "TC-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]


def est_seconds(steps: Iterable[str], technique: str = "") -> int:
    """Rough wall-clock estimate per test (module setup + navigation + one step each) used by the runtime budget."""
    n = len(list(steps))
    base = 4 if technique in ("role_matrix", "state_transition") else 5
    return int(base + 1.5 * n + 0.5)


def fill_text(length: int, seed: str = "") -> str:
    """Deterministic text of exactly `length` characters, distinct per seed (avoids duplicate-record collisions)."""
    if length <= 0:
        return ""
    head = ("T" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:5]) if seed else "T"
    s = (head + "x" * length)[:length]
    return s


def new_case(*, key: str, title: str, technique: str, test_type: str, level: str, target: Dict[str, Any],
             ac_ids: Optional[List[str]] = None, roles: Optional[List[str]] = None,
             preconditions: Optional[List[str]] = None, inputs: Optional[Dict[str, Dict[str, Any]]] = None,
             steps_outline: Optional[List[str]] = None, oracles: Optional[List[Dict[str, Any]]] = None,
             cleanup: Optional[List[str]] = None, source: str = "brd", confidence: float = 1.0,
             module_id: Optional[str] = None, tags: Optional[List[str]] = None,
             likelihood: float = 0.5) -> Dict[str, Any]:
    steps = list(steps_outline or [])
    return {
        "id": case_id(key), "key": key, "ac_ids": sorted(set(ac_ids or [])),
        "ac_link": "generator" if ac_ids else None, "scenario_id": None, "module_id": module_id,
        "title": title[:160], "technique": technique, "test_type": test_type, "level": level,
        "priority": "P3", "risk_score": 0.0, "roles": list(roles or []), "preconditions": list(preconditions or []),
        "inputs": dict(inputs or {}), "steps_outline": steps, "oracles": list(oracles or []),
        "cleanup": list(cleanup or []), "target": {k: v for k, v in target.items() if v is not None},
        "source": source, "confidence": round(float(confidence), 2), "est_seconds": est_seconds(steps, technique),
        "tags": sorted(set(tags or [])), "_likelihood": round(float(likelihood), 3),
    }


def form_target(form: Form, fld: Optional[Field] = None) -> Dict[str, Any]:
    return {"kind": "form", "form_id": form.form_id, "url_template": form.url_template,
            "sample_url": form.sample_url, "field": fld.name if fld else None}


def form_preconditions(form: Form) -> List[str]:
    """Where the case starts. The signed-in role comes from the spec's module setup (assign.py checks that the
    module's role can reach the page), not from the role the crawler happened to discover the form with."""
    return [f"on {form.url_template}" + (f" ({form.sample_url})" if form.sample_url and "{" in form.url_template else "")]


def submit_label(form: Form) -> str:
    return (form.submit or {}).get("text") or "submit"


def probe_for(form: Form, field_name: Optional[str], kinds: Iterable[str]) -> Optional[Dict[str, Any]]:
    kinds = list(kinds)
    for p in form.probes:
        if p.get("probe") in kinds and (field_name is None or p.get("field") in (field_name, None)):
            return p
    return None


def rejection_oracles(form: Form, fld: Field, message_kinds: Iterable[str], probe_kinds: Iterable[str],
                      native_evidence: bool = True) -> List[Dict[str, Any]]:
    """Oracles for an input the app must reject: the field is invalid, the expected message (BRD > observed),
    and — when a probe showed it — that native validation stops the request / the URL does not change.

    native_evidence=False for inputs the browser's own validation does not catch (e.g. whitespace only passes
    `required`): no native message, no probe evidence, and "rejected" instead of "field invalid".

    "field invalid" also needs the probe of this kind to have SEEN it — the field marked aria-invalid, or a native
    validation message for it. An app that validates in its own script (`novalidate`, errors in an alert) never
    marks the field, and a rule the DOM does not state (a price below 0 in a text input, a length with no
    maxlength) never makes it :invalid: asserting it there fails on a correct app."""
    probe = probe_for(form, fld.name, probe_kinds) if native_evidence else None
    native = (probe or {}).get("native") or {}
    # a native message alone is not enough: on a `novalidate` form the browser does not block, the page posts and
    # re-renders, and the field is no longer invalid — it must have BLOCKED the submit (or the app set aria-invalid)
    seen_invalid = probe is not None and (
        fld.name in (probe.get("aria_invalid") or [])
        or (bool(native.get("blocked")) and bool((native.get("messages") or {}).get(fld.name))))
    first = {"type": "field_invalid", "field": fld.name} if seen_invalid else \
        {"type": "submission_rejected", "field": fld.name}
    oracles: List[Dict[str, Any]] = [first]
    for mk in message_kinds:
        msg = fld.messages.get(mk)
        if msg and (native_evidence or msg.get("origin") != "native"):
            oracles.append({"type": "error_text", "contains": msg["text"], "source": msg["source"]})
            break
    if not native_evidence:
        return oracles
    if probe:
        native = probe.get("native") or {}
        # nothing was sent: the browser blocked it, or the page's own validation did (an empty network log)
        if native.get("blocked") or probe.get("network") == []:
            oracles.append({"type": "no_request", "method": form.method.upper(), "url": form.action, "source": "observed"})
        if probe.get("navigated") is False:
            oracles.append({"type": "url_unchanged", "source": "observed"})
    return oracles


def acceptance_oracles(fld: Optional[Field], message_kinds: Iterable[str] = (), source: str = "dom") -> List[Dict[str, Any]]:
    """`source` = where the expectation that the value is valid comes from (the constraint's source)."""
    oracles: List[Dict[str, Any]] = [{"type": "submission_accepted", "source": source}]
    if fld is not None:
        for mk in message_kinds:
            msg = fld.messages.get(mk)
            if msg:
                oracles.append({"type": "no_error_text", "contains": msg["text"], "source": msg["source"]})
                break
    return oracles


def stable_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def other_fields_filled(form: Form, except_field: str) -> Dict[str, Dict[str, Any]]:
    from tools.test_design.inputs import valid_value_for
    out = {}
    for f in form.fields:
        if f.name == except_field:
            continue
        v = valid_value_for(f)
        if v is not None:
            out[f.name] = {"value": v, "value_rule": "valid", "role": "filler"}
    return out
