"""
crud.py — CRUD lifecycle (Phase 3.2), from the page templates app_map found:

    <base>          list            <base>/new      create form
    <base>/{id}     detail (+ delete form)          <base>/{id}/edit   update form

One lifecycle test per resource with a create form and a list or detail page:
create → list → detail → reload persists → update → delete → gone, then the deleted item's direct URL. [thorough]
"""

import re
from typing import Any, Dict, List

from tools.test_design.cases import fill_text, new_case
from tools.test_design.inputs import DesignInputs, valid_value_for

# Lifecycle wording; "add" is left out on purpose (adding to a cart is not creating the resource) and so are
# duplicate-submission rules (a different test: error_guessing form.double_click).
_LIFECYCLE = re.compile(r"\b(creat\w*|delet\w*|edit\w*|updat\w*|disappear\w*|not found|reload\w*|persist\w*|"
                        r"permanent\w*)\b", re.I)
_NOT_LIFECYCLE = re.compile(r"\b(twice|duplicate\w*|same name)\b", re.I)


def generate(inp: DesignInputs) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    templates = set(inp.states)
    for base in sorted(templates):
        create = next((f for f in inp.forms if f.url_template == f"{base}/new" and f.method == "post"), None)
        if create is None:
            continue
        detail = f"{base}/{{id}}" if f"{base}/{{id}}" in templates else None
        if base not in templates and detail is None:
            continue
        edit = next((f for f in inp.forms if f.url_template == f"{base}/{{id}}/edit"), None)
        delete = next((f for f in inp.forms if detail and f.url_template == detail and
                       (f.submit or {}).get("destructive")), None)
        noun = base.strip("/").split("/")[-1].rstrip("s") or "item"
        values = {f.name: valid_value_for(f) for f in create.fields}
        name_field = next((f for f in create.fields if f.type in ("text",) and "name" in f.name.lower()), None)
        if name_field is not None:
            values[name_field.name] = "CRUD " + fill_text(12, f"crud{base}")
        steps = [f"create a {noun} on {base}/new with unique values", f"find it in the list on {base}"]
        if detail:
            steps += ["open its detail page; every field shows the value entered", "reload; it is still there"]
        if edit:
            steps += [f"edit it on {base}/{{id}}/edit and save", "the list and the detail page show the new values"]
        if delete:
            steps += [f"delete it ({(delete.submit or {}).get('text') or 'Delete'})", f"it is gone from {base}",
                      "opening its old detail URL shows 'not found' (also after a reload)"]
        noun_rx = re.compile(rf"\b{re.escape(noun)}s?\b", re.I)
        ac_ids = [a["id"] for a in inp.testable_acs()
                  if noun_rx.search(a["statement"]) and _LIFECYCLE.search(a["statement"])
                  and not _NOT_LIFECYCLE.search(a["statement"])]
        out.append(new_case(
            key=f"crud|{base}", title=f"{noun.capitalize()} lifecycle: create, read, reload, update, delete, gone",
            technique="crud", test_type="positive", level="thorough",
            target={"kind": "resource", "url_template": base, "sample_url": create.sample_url},
            ac_ids=ac_ids, roles=[create.role] if create.role else [], preconditions=[f"signed in as {create.role}"]
            if create.role else [],
            inputs={k: {"value": v, "value_rule": "valid, unique"} for k, v in values.items() if v is not None},
            steps_outline=steps,
            oracles=[{"type": "persisted", "source": "catalog"}, {"type": "deleted_not_found", "source": "catalog"}],
            cleanup=[f"delete the {noun} if a step failed before deletion"],
            source="app_map+catalog", module_id=create.module_id, tags=["crud"], likelihood=0.7,
        ))
    return out
