"""
ep.py — equivalence partitioning (Phase 3.2).

Valid and invalid classes per field type (plan §5.D). One test per invalid class; the valid classes of every field
are combined into ONE positive test per form. Classes already exercised by BVA with the same value are removed by
design.py's signature de-duplication, so EP and BVA never double-count the same input.
"""

from typing import Any, Dict, List, Optional, Tuple

from tools.test_design.cases import (
    acceptance_oracles, fill_text, form_preconditions, form_target, new_case, other_fields_filled, probe_for,
    rejection_oracles, submit_label,
)
from tools.test_design.inputs import DesignInputs, Field, Form, constraint_source, valid_value_for

# (class name, value, message kinds, probe kinds, constraint kind for AC attribution)
InvalidClass = Tuple[str, Any, List[str], List[str], str]


def invalid_classes(fld: Field) -> List[InvalidClass]:
    """Invalid equivalence classes for one field, in a fixed order."""
    c = fld.constraints
    out: List[InvalidClass] = []
    required = bool((c.get("required") or {}).get("value", fld.required))
    if required:
        if fld.type in ("select",) or fld.options:
            out.append(("nothing selected", "", ["required_missing"], ["required_missing", "empty"], "required"))
        elif fld.type == "file":
            out.append(("no file chosen", None, ["required_missing"], ["required_missing", "empty"], "required"))
        else:
            out.append(("empty", "", ["required_missing"], ["required_missing", "empty"], "required"))
            out.append(("whitespace only", "   ", ["required_missing"], ["required_missing", "empty"], "required"))
    rng = c.get("range") or {}
    numeric = fld.type == "number" or bool(rng) or "decimals" in c
    if numeric:
        out.append(("non-numeric text", "abc", ["wrong_type", "out_of_range"], ["wrong_type", "non_integer"], "range"))
        if rng.get("integer"):
            out.append(("decimal in an integer field", "1.5", ["out_of_range", "wrong_type"], ["non_integer"], "range"))
        if rng.get("min") is not None and float(rng["min"]) >= 0:
            out.append(("negative number", "-5", ["out_of_range", "below_min"], ["below_min"], "range"))
        dec = (c.get("decimals") or {}).get("max")
        if dec is not None and not rng.get("integer"):
            out.append((f"more than {dec} decimals", "1." + "1" * (int(dec) + 1), ["wrong_type", "out_of_range"],
                        ["wrong_type"], "decimals"))
    length = c.get("length") or {}
    if length.get("max") is not None and fld.type not in ("select", "file"):
        n = int(length["max"]) * 2
        out.append((f"far too long ({n} chars)", fill_text(n, f"ep{fld.form_id}{fld.name}"), ["too_long"],
                    ["too_long"], "length"))
    opts = (c.get("options") or {}).get("values")
    if opts and fld.type not in ("select",):
        out.append(("value outside the allowed set", "Other", ["required_missing"], [], "options"))
    accept = (c.get("accept") or {}).get("values")
    if fld.type == "file" and accept:
        bad = next((e for e in (".exe", ".txt", ".pdf") if e not in accept), ".bin")
        out.append((f"disallowed type ({bad})", {"file_name": f"invalid{bad}", "size_bytes": 1024},
                    ["wrong_accept"], ["wrong_accept"], "accept"))
        out.append(("empty (0-byte) file", {"file_name": f"empty{accept[0]}", "size_bytes": 0}, ["too_large", "wrong_accept"],
                    [], "size"))
    if fld.type == "email":
        out.append(("missing @", "qa.example.com", ["wrong_type"], ["wrong_type"], "pattern"))
    else:
        bad = _not_matching((c.get("pattern") or {}).get("value"))
        if bad is not None:                 # a format rule (BRD, DOM pattern attribute, or the app's code — Phase 8)
            out.append((f"wrong format ({bad})", bad, ["wrong_type"], ["wrong_type"], "pattern"))
    return out


def _not_matching(pattern) -> Optional[str]:
    """A short value the format rule rejects (None when the pattern is unusable or matches all candidates)."""
    import re as _re
    if not isinstance(pattern, str) or not pattern or pattern == "email":
        return None
    try:
        rx = _re.compile(pattern)
    except _re.error:
        return None
    for cand in ("abc", "12.345", "1,5", "!@#", "x1"):
        if not rx.fullmatch(cand):
            return cand
    return None


def valid_classes(fld: Field) -> List[Tuple[str, Any]]:
    """Valid classes beyond the default filler (each option of a select; each accepted file type)."""
    out: List[Tuple[str, Any]] = []
    if fld.type == "select" or fld.options:
        allowed = (fld.constraints.get("options") or {}).get("values")
        for o in fld.options:
            if o.get("value") in (None, "") or o.get("disabled"):
                continue
            if allowed and o.get("text") not in allowed and o.get("value") not in allowed:
                continue
            out.append((f"option {o.get('text') or o.get('value')}", o.get("text") or o.get("value")))
    elif fld.type == "file":
        for ext in (fld.constraints.get("accept") or {}).get("values") or []:
            out.append((f"type {ext}", {"file_name": f"valid{ext}", "size_bytes": 1024}))
    return out


def _level(fld: Field, form: Form, standard_ok: bool) -> str:
    base = "standard" if standard_ok and fld.priority in ("P0", "P1") else "thorough"
    if form.twin_of:
        base = "thorough" if base == "standard" else "exhaustive"
    return base


def valid_known(form: Form, f: Field) -> Optional[bool]:
    """True: a valid value can be derived (options, a numeric/length/date/type rule). None: the field is optional
    and the form accepts it empty (leave it empty). False: unknowable (credentials, codes, free text the app
    checks against data) — a "valid" guess would make a positive test that fails on a correct app."""
    c = f.constraints
    if f.type == "password":
        return False
    length = c.get("length") or {}
    if f.type == "select" or f.options or any(k in c for k in ("range", "accept", "date", "pattern")) or             (length and length.get("source") != "default"):
        return True
    if (c.get("required") or {}).get("value", f.required):
        return False
    empty = probe_for(form, None, ["empty"])
    return None if not (empty and empty.get("accepted") is False) else False


def generate(inp: DesignInputs) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for form in inp.forms:
        if not form.fields:
            continue
        known = {f.name: valid_known(form, f) for f in form.fields}
        positives_ok = all(k is not False for k in known.values()) and any(known.values())
        # one combined positive test per form — only when every field's valid value is genuinely known
        valid_inputs = {}
        for f in form.fields:
            v = valid_value_for(f) if known[f.name] else ""
            if v is not None:
                valid_inputs[f.name] = {"value": v, "value_rule": "valid class" if known[f.name] else "left empty",
                                        "constraint_source": "dom" if f.constraints else "default"}
        if positives_ok:
            out.append(new_case(
                key=f"ep|{form.form_id}|valid", title=f"{form.dom_id or 'form'} on {form.url_template}: all fields valid is accepted",
                technique="ep", test_type="positive",
                level="standard" if any(f.priority in ("P0", "P1") for f in form.fields) and not form.twin_of else "thorough",
                target=form_target(form), ac_ids=[],          # linked later by text (linking.py) or the LLM
                preconditions=form_preconditions(form), inputs=valid_inputs,
                steps_outline=["fill every field with a valid value", f"submit ({submit_label(form)})"],
                oracles=acceptance_oracles(None), source="dom", module_id=form.module_id, likelihood=0.4,
            ))
        for fld in form.fields:
            for name, value, mk, pk, kind in invalid_classes(fld):
                ac_ids = list(fld.kind_acs.get(kind) or fld.kind_acs.get("required") or fld.ac_ids) \
                    if kind != "required" else list(fld.kind_acs.get("required") or fld.ac_ids)
                inputs = {fld.name: {"value": value, "value_rule": f"EP invalid: {name}",
                                     "constraint_source": constraint_source(fld, kind, "value" if kind == "required" else "max")}}
                inputs.update(other_fields_filled(form, fld.name))
                out.append(new_case(
                    key=f"ep|{form.form_id}|{fld.name}|invalid|{name}",
                    title=f"{fld.label or fld.name}: {name} is rejected", technique="ep", test_type="negative",
                    level=_level(fld, form, kind in ("required", "accept", "range", "decimals")),
                    target=form_target(form, fld), ac_ids=ac_ids, 
                    preconditions=form_preconditions(form), inputs=inputs,
                    steps_outline=["fill all other fields with valid values", f"set {fld.label or fld.name} to {name}",
                                   f"submit ({submit_label(form)})"],
                    oracles=rejection_oracles(form, fld, mk, pk, native_evidence=name != "whitespace only"),
                    source=_src(fld, kind), module_id=form.module_id,
                    tags=[kind], likelihood=0.75,
                ))
            for name, value in (valid_classes(fld) if positives_ok else []):
                inputs = {fld.name: {"value": value, "value_rule": f"EP valid: {name}"}}
                inputs.update(other_fields_filled(form, fld.name))
                out.append(new_case(
                    key=f"ep|{form.form_id}|{fld.name}|valid|{name}",
                    title=f"{fld.label or fld.name}: {name} is accepted", technique="ep", test_type="positive",
                    level="thorough" if not form.twin_of else "exhaustive", target=form_target(form, fld),
                    ac_ids=list(fld.kind_acs.get("options") or fld.kind_acs.get("accept") or fld.ac_ids),
                    preconditions=form_preconditions(form), inputs=inputs,
                    steps_outline=["fill all other fields with valid values", f"set {fld.label or fld.name} to {name}",
                                   f"submit ({submit_label(form)})"],
                    oracles=acceptance_oracles(fld, source=_src(fld, "options")), source=_src(fld, "options"),
                    module_id=form.module_id,
                    likelihood=0.3,
                ))
    return out


def _src(fld: Field, kind: str) -> str:
    c = fld.constraints.get(kind) or {}
    return c.get("source") or "dom"
