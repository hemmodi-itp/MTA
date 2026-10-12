"""
bva.py — boundary value analysis, 3-value (Phase 3.2).

For every length, numeric, date, count and file-size constraint: min-1, min, min+1, nominal, max-1, max, max+1.
Constraint sources in precedence order: DOM > BRD AC > observed validation > default (flagged, thorough only).

Pure point functions (tested with exact values) + generate(inputs) which turns them into test cases.
"""

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional, Tuple

from tools.test_design.cases import (
    acceptance_oracles, fill_text, form_preconditions, form_target, new_case, other_fields_filled, rejection_oracles,
    submit_label,
)
from tools.test_design.inputs import DesignInputs, Field, Form, constraint_source

Point = Tuple[str, Any, bool]          # (label, value, valid)
DEFAULT_TEXT_MAX = 255                  # flagged default when a text field states no maximum


def _dedupe(points: List[Point]) -> List[Point]:
    out: List[Point] = []
    seen = set()
    for label, value, valid in points:
        if value in seen:
            continue
        seen.add(value)
        out.append((label, value, valid))
    return out


def numeric_points(lo: Optional[Decimal], hi: Optional[Decimal], step: Decimal,
                   lo_exclusive: bool = False) -> List[Point]:
    """3-value BVA over a numeric range with the given step. A missing bound contributes no points."""
    if lo is None and hi is None:
        return []
    pts: List[Point] = []
    if lo is not None:
        if lo_exclusive:
            pts += [("min", lo, False), ("min+1", lo + step, True)]
        else:
            pts += [("min-1", lo - step, False), ("min", lo, True), ("min+1", lo + step, True)]
    if lo is not None and hi is not None:
        mid = ((lo + hi) / 2 / step).to_integral_value(rounding=ROUND_HALF_UP) * step
        pts.append(("nominal", mid, True))
    elif lo is not None:
        pts.append(("nominal", lo + step * 10, True))
    else:
        pts.append(("nominal", hi - step * 10 if hi - step * 10 > 0 else hi / 2, True))
    if hi is not None:
        pts += [("max-1", hi - step, True), ("max", hi, True), ("max+1", hi + step, False)]
    if lo is not None and hi is not None and lo > hi:
        return []
    # an interior point that falls outside [lo, hi] (tiny ranges) is not a valid boundary
    fixed = []
    for label, v, valid in pts:
        if valid and ((lo is not None and (v < lo or (lo_exclusive and v == lo))) or (hi is not None and v > hi)):
            continue
        fixed.append((label, v, valid))
    return _dedupe(fixed)


def length_points(lo: Optional[int], hi: Optional[int]) -> List[Point]:
    """Lengths are non-negative integers: min-1 below 0 is dropped."""
    pts = numeric_points(Decimal(lo) if lo is not None else None, Decimal(hi) if hi is not None else None, Decimal(1))
    return [(l, int(v), ok) for l, v, ok in pts if v >= 0]


def date_points(lo: Optional[dt.date], hi: Optional[dt.date]) -> List[Point]:
    """Day-granular BVA. timedelta arithmetic gets month ends and leap years right (2024-02-28 + 1 = 02-29)."""
    one = dt.timedelta(days=1)
    pts: List[Point] = []
    if lo is not None:
        pts += [("min-1", lo - one, False), ("min", lo, True), ("min+1", lo + one, True)]
    if lo is not None and hi is not None:
        if lo > hi:
            return []
        pts.append(("nominal", lo + (hi - lo) // 2, True))
    if hi is not None:
        pts += [("max-1", hi - one, True), ("max", hi, True), ("max+1", hi + one, False)]
    return _dedupe([(l, v, ok) for l, v, ok in pts if not ok or ((lo is None or v >= lo) and (hi is None or v <= hi))])


def size_points(lo: Optional[int], hi: Optional[int]) -> List[Point]:
    pts = length_points(lo, hi)
    return [p for p in pts if p[0] != "nominal" or lo is not None]


def _step_for(rng: Dict[str, Any], decimals: Optional[int]) -> Decimal:
    if rng.get("step") not in (None, ""):
        return Decimal(str(rng["step"]))
    if rng.get("integer"):
        return Decimal(1)
    if decimals:
        return Decimal(1).scaleb(-int(decimals))
    return Decimal(1)


def fmt_number(v: Decimal, step: Decimal) -> str:
    exp = -step.as_tuple().exponent if step.as_tuple().exponent < 0 else 0
    return f"{v:.{exp}f}"


# ── case generation ────────────────────────────────────────────────────────────

def _level(fld: Field, form: Form, default_source: bool) -> str:
    base = "standard" if fld.priority in ("P0", "P1") else "thorough"
    if default_source:
        base = "thorough" if base == "standard" else "exhaustive"
    if form.twin_of:
        base = {"standard": "thorough", "thorough": "exhaustive"}.get(base, base)
    return base


def _case(form: Form, fld: Field, kind: str, label: str, value: Any, valid: bool, rule: str, source: str,
          msg_kinds: List[str], probe_kinds: List[str], level: str, inputs_extra: Dict[str, Any],
          confidence: float) -> Dict[str, Any]:
    ac_ids = list(fld.kind_acs.get(kind) or fld.ac_ids)
    shown = f"{len(value)} chars" if kind == "length" else (value if not isinstance(value, dict) else
                                                            f"{value.get('size_bytes')} bytes")
    verdict = "is accepted" if valid else "is rejected"
    title = f"{fld.label or fld.name} {kind} {label} ({shown}) {verdict}"
    inputs = {fld.name: dict({"value": value, "value_rule": rule, "constraint_source": source}, **inputs_extra)}
    inputs.update(other_fields_filled(form, fld.name))
    steps = ["fill all other fields with valid values", f"set {fld.label or fld.name} to {rule}",
             f"submit ({submit_label(form)})"]
    oracles = acceptance_oracles(fld, msg_kinds, source) if valid else rejection_oracles(form, fld, msg_kinds, probe_kinds)
    return new_case(
        key=f"bva|{form.form_id}|{fld.name}|{kind}|{label}", title=title, technique="bva",
        test_type=("boundary" if label != "nominal" else "positive") if valid else "negative",
        level=level, target=form_target(form, fld), ac_ids=ac_ids, 
        preconditions=form_preconditions(form), inputs=inputs, steps_outline=steps, oracles=oracles,
        source=source, confidence=confidence, module_id=form.module_id, tags=[kind],
        likelihood=0.8 if not valid else 0.6,
    )


def generate(inp: DesignInputs) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for form in inp.forms:
        for fld in form.fields:
            c = fld.constraints
            # length
            if fld.type in ("text", "textarea", "search", "password", "email", "tel", "url"):
                length = c.get("length") or {}
                lo, hi = length.get("min"), length.get("max")
                if lo is None and fld.required and hi is not None:
                    lo = 1
                default = hi is None
                if default and (lo is not None or "range" not in c) and fld.type not in ("search",) and "decimals" not in c:
                    hi = DEFAULT_TEXT_MAX
                if hi is not None or lo is not None:
                    src_hi = "default" if default else constraint_source(fld, "length", "max")
                    for label, n, valid in length_points(lo, hi):
                        # a defaulted max only contributes max / max+1; a real min keeps its own points
                        if default and label in ("nominal", "max-1"):
                            continue
                        if label.startswith("min") and length.get("min") is None and default:
                            continue          # min implied by `required` only: the EP "empty" class covers it
                        src = src_hi if label.startswith("max") else (
                            constraint_source(fld, "length", "min") if length.get("min") is not None else
                            ("dom" if fld.required else "default"))
                        conf = 0.4 if src == "default" else 0.95
                        mk = ["too_long"] if label.startswith("max") else (["required_missing"] if n == 0 else ["too_short"])
                        pk = ["too_long"] if label.startswith("max") else ["required_missing", "empty"]
                        out.append(_case(form, fld, "length", label, fill_text(n, f"{form.form_id}{fld.name}{label}"),
                                         valid, f"len={label} ({n})", src, mk, pk,
                                         _level(fld, form, src == "default"), {"length": n}, conf))
            # numeric range (number inputs, or text inputs with a stated numeric rule)
            rng = c.get("range")
            if rng and (rng.get("min") is not None or rng.get("max") is not None):
                decimals = (c.get("decimals") or {}).get("max")
                step = _step_for(rng, decimals)
                lo = Decimal(str(rng["min"])) if rng.get("min") is not None else None
                hi = Decimal(str(rng["max"])) if rng.get("max") is not None else None
                for label, v, valid in numeric_points(lo, hi, step, bool(rng.get("min_exclusive"))):
                    bound = "min" if label.startswith("min") else ("max" if label.startswith("max") else "min")
                    src = constraint_source(fld, "range", bound)
                    mk = ["out_of_range", "below_min" if label.startswith("min") else "above_max"]
                    pk = ["below_min"] if label.startswith("min") else ["above_max"]
                    out.append(_case(form, fld, "range", label, fmt_number(v, step), valid,
                                     f"{label} ({fmt_number(v, step)})", src, mk, pk,
                                     _level(fld, form, False), {"step": fmt_number(step, step)}, 0.95))
            # dates
            dates = c.get("date")
            if dates and (dates.get("min") or dates.get("max")):
                lo = _date(dates.get("min"))
                hi = _date(dates.get("max"))
                for label, v, valid in date_points(lo, hi):
                    src = constraint_source(fld, "date", "min" if label.startswith("min") else "max")
                    out.append(_case(form, fld, "date", label, v.isoformat(), valid, f"{label} ({v.isoformat()})",
                                     src, ["out_of_range"], ["below_min", "above_max"], _level(fld, form, False),
                                     {}, 0.95))
            # file size
            size = c.get("size")
            if fld.type == "file" and size and size.get("max") is not None:
                ext = ((c.get("accept") or {}).get("values") or [".csv"])[0]
                for label, n, valid in size_points(size.get("min"), int(size["max"])):
                    if label == "nominal":
                        continue
                    src = constraint_source(fld, "size", "max")
                    out.append(_case(form, fld, "size", label, {"file_name": f"bva_{label.replace('+', 'p').replace('-', 'm')}{ext}",
                                                                 "size_bytes": n}, valid, f"file of {label} bytes ({n})",
                                     src, ["too_large"], ["too_large"], _level(fld, form, False),
                                     {"needs_fixture": True}, 0.9))
    return out


def _date(s: Optional[str]) -> Optional[dt.date]:
    if not s:
        return None
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None
