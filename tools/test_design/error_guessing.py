"""
error_guessing.py — applies the error-guessing catalog (catalog/error_guessing.yaml, plan §5 D/E/I) per field type.

Core entries belong to the `thorough` profile; every entry on every field (including twin forms) is `exhaustive`.
Entries marked `requires: security_probes` are generated only when the project allows security probes.
"""

import functools
import os
from typing import Any, Dict, List, Optional

import yaml

from tools.test_design.cases import (
    fill_text, form_preconditions, form_target, new_case, other_fields_filled, rejection_oracles, submit_label,
)
from tools.test_design.inputs import DesignInputs, Field, Form, valid_value_for

CATALOG_PATH = os.path.join(os.path.dirname(__file__), "catalog", "error_guessing.yaml")
_TYPE_ALIASES = {"tel": "text", "url": "text", "range": "number"}


@functools.lru_cache(maxsize=1)
def load_catalog(path: str = CATALOG_PATH) -> List[Dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    entries = data.get("entries") or []
    ids = [e["id"] for e in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("error_guessing.yaml: duplicate entry ids")
    return entries


def _value(entry: Dict[str, Any], fld: Optional[Field], seed: str) -> Any:
    v = entry.get("value")
    if v is None or fld is None:
        return v
    if isinstance(v, str) and v.startswith("{long:"):
        return fill_text(int(v[6:-1]), seed)
    if v == "{default}":
        return fld.default_value or ""
    if fld.type == "file":
        names = {"renamed_exe": {"file_name": "renamed.png", "size_bytes": 2048, "content": "MZ executable header"},
                 "zero_byte": {"file_name": "empty.csv", "size_bytes": 0},
                 "unicode_name": {"file_name": "résumé 漢字 #1.csv", "size_bytes": 512},
                 "double_ext": {"file_name": "report.csv.exe", "size_bytes": 512}}
        return names.get(v, v)
    if isinstance(v, str) and "{valid}" in v:
        return v.replace("{valid}", str(valid_value_for(fld) or "Valid"))
    return v


def _oracles(expect: str, form: Form, fld: Optional[Field], value: Any) -> List[Dict[str, Any]]:
    if expect == "rejected" and fld is not None:
        return rejection_oracles(form, fld, ["wrong_type", "too_long", "wrong_accept", "out_of_range"], [])
    table = {
        "accepted": [{"type": "submission_accepted", "source": "catalog"}],
        "consistent": [{"type": "no_server_error", "source": "catalog"},
                       {"type": "consistent_outcome", "detail": "accepted as entered or rejected with a message",
                        "source": "catalog"}],
        "no_server_error": [{"type": "no_server_error", "source": "catalog"}],
        "rendered_as_text": [{"type": "rendered_as_text", "contains": value, "source": "catalog"}],
        "not_executed": [{"type": "no_script_execution", "probe": "window.__mta_xss", "source": "catalog"}],
        "single_record": [{"type": "single_record_created", "source": "catalog"}],
        "error_clears": [{"type": "error_clears", "source": "catalog"}],
    }
    return table.get(expect, table["consistent"])


def generate(inp: DesignInputs) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    catalog = load_catalog()
    for form in inp.forms:
        if not form.fields:
            continue
        for entry in catalog:
            if entry.get("requires") == "security_probes" and not inp.allow_security_probes:
                continue
            applies = entry.get("applies_to") or []
            if "form" in applies:
                if form.method != "post" or (form.submit or {}).get("destructive"):
                    continue
                level = "thorough" if entry.get("core") and not form.twin_of else "exhaustive"
                out.append(new_case(
                    key=f"eg|{entry['id']}|{form.form_id}", title=f"{form.dom_id or 'form'}: {entry['title']}",
                    technique="error_guessing", test_type="negative", level=level, target=form_target(form),
                    preconditions=form_preconditions(form),
                    inputs=other_fields_filled(form, ""),
                    steps_outline=["fill every field with a valid value", f"{entry['title']} ({submit_label(form)})"],
                    oracles=_oracles(entry["expect"], form, None, None), source="catalog", confidence=0.85,
                    module_id=form.module_id, tags=[entry["id"]], likelihood=0.55,
                ))
                continue
            for fld in form.fields:
                ftype = _TYPE_ALIASES.get(fld.type, fld.type)
                if ftype not in applies:
                    continue
                level = "thorough" if entry.get("core") and not form.twin_of else "exhaustive"
                value = _value(entry, fld, f"{entry['id']}{form.form_id}{fld.name}")
                inputs = {fld.name: {"value": value, "value_rule": f"catalog: {entry['id']}"}}
                inputs.update(other_fields_filled(form, fld.name))
                out.append(new_case(
                    key=f"eg|{entry['id']}|{form.form_id}|{fld.name}",
                    title=f"{fld.label or fld.name}: {entry['title']}", technique="error_guessing",
                    test_type="negative" if entry["expect"] in ("rejected", "not_executed") else "boundary",
                    level=level, target=form_target(form, fld), 
                    preconditions=form_preconditions(form), inputs=inputs,
                    steps_outline=["fill all other fields with valid values",
                                   f"set {fld.label or fld.name} to the catalog value", f"submit ({submit_label(form)})"],
                    oracles=_oracles(entry["expect"], form, fld, value),
                    source="catalog", confidence=0.85, module_id=form.module_id,
                    tags=[entry["id"]] + (["security"] if entry.get("requires") else []),
                    likelihood=0.6 if entry.get("core") else 0.4,
                ))
    return out
