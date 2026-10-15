"""
inputs.py — everything the test-design generators read, loaded once and normalised (no generator does I/O).

    DesignInputs.load(project_dir)   reads project.yaml, requirements.json, business_scenarios.json, form_model.json,
                                     app_map.json, permission_matrix.json, test_data.json and the previous
                                     test_cases.json (change fingerprint); a missing Phase 2 artifact only disables
                                     the generators that need it (recorded in `limitations`).

Field constraints are merged with the plan's precedence: DOM constraint > BRD AC > observed validation >
default (flagged). Every merged constraint keeps its `source`.
"""

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import yaml

from tools.test_design.constraints import message_kind, parse_constraints, quoted_messages, split_clauses

PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
_GENERIC_NAMES = {"q", "id", "next", "csrf", "token", "_csrf"}


def best_priority(priorities) -> str:
    ps = [p for p in priorities if p in PRIORITY_RANK]
    return min(ps, key=PRIORITY_RANK.get) if ps else "P3"


def url_path(url: str) -> str:
    p = urlparse(url or "")
    return (p.path or "/").rstrip("/") or "/"


def norm_template(t: str) -> str:
    """'/products?page' → '/products' (query-variant states are the same page for test design)."""
    return (t or "/").split("?", 1)[0].rstrip("/") or "/"


@dataclass
class Field:
    form_id: str
    name: str
    label: str
    type: str
    locator: Optional[Dict[str, Any]]
    required: bool
    constraints: Dict[str, Dict[str, Any]]          # kind -> {..., "source": dom|brd|observed|default}
    messages: Dict[str, Dict[str, str]]             # kind -> {"text", "source"}
    options: List[Dict[str, Any]]
    default_value: Optional[str]
    ac_ids: List[str] = field(default_factory=list)
    priority: str = "P3"
    kind_acs: Dict[str, List[str]] = field(default_factory=dict)   # constraint kind -> ACs that state it
    citations: Dict[str, str] = field(default_factory=dict)        # Phase 8.2: constraint kind -> "file:line"


@dataclass
class Form:
    form_id: str
    url_template: str
    sample_url: str
    dom_id: str
    method: str
    action: str
    submit: Dict[str, Any]
    role: Optional[str]
    fields: List[Field]
    probes: List[Dict[str, Any]]
    module_id: Optional[str] = None
    twin_of: Optional[str] = None                   # same dom_id + field names as an earlier form (e.g. new/edit)
    ac_ids: List[str] = field(default_factory=list)


@dataclass
class State:
    url_template: str
    sample_url: str
    roles: List[str]
    access: Dict[str, str]
    structural_hash: str
    elements: List[Dict[str, Any]]
    module_id: Optional[str] = None


@dataclass
class Transition:
    from_t: str
    to_t: str
    via: str                                        # element accessible name (link/button text)
    role: Optional[str]
    roles: List[str]
    action: str


@dataclass
class DesignInputs:
    project: str
    modules: List[Dict[str, Any]]                   # {id, name, url, path, role}
    acs: List[Dict[str, Any]]                       # leaf ACs: id, statement, priority, risk_tags, testability, module_id, req_id
    scenarios: List[Dict[str, Any]]
    forms: List[Form]
    states: Dict[str, State]
    transitions: List[Transition]
    permission: Dict[str, Any]
    datasets: Dict[str, Dict[str, Any]]             # scenario_id -> test_data record
    role_logins: Dict[str, Dict[str, str]]          # role -> {username, password} (from auth.roles setup fills)
    allow_security_probes: bool
    previous_hashes: Dict[str, str]
    present: Dict[str, str]
    limitations: List[str]
    # Phase 8 white-box: form_id -> fields the server combines with stored state before checking (a cart line's
    # quantity is added to what the cart holds) — an "accepted at the limit" case then depends on earlier tests
    stateful: Dict[str, List[str]] = field(default_factory=dict)

    # ── loading ──────────────────────────────────────────────────────────────

    @classmethod
    def load(cls, project_dir: str, project: Optional[str] = None) -> "DesignInputs":
        def read(*rel) -> Optional[Any]:
            for base in ("test_comprehension", "comprehension"):
                path = os.path.join(project_dir, base, *rel)
                if os.path.exists(path):
                    with open(path, encoding="utf-8") as fh:
                        return json.load(fh)
            return None

        def read_fixed(*rel) -> Optional[Any]:
            path = os.path.join(project_dir, *rel)
            if not os.path.exists(path):
                return None
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)

        raw_yaml: dict = {}
        ypath = os.path.join(project_dir, "project.yaml")
        if os.path.exists(ypath):
            with open(ypath, encoding="utf-8") as fh:
                raw_yaml = yaml.safe_load(fh) or {}
        return cls.from_artifacts(
            project=project or os.path.basename(os.path.normpath(project_dir)),
            manifest=raw_yaml,
            requirements=read("requirements.json"),
            scenarios=read("business_scenarios.json"),
            form_model=read("form_model.json"),
            app_map=read("app_map.json"),
            permission_matrix=read("permission_matrix.json"),
            test_data=read_fixed("test_creation", "test_data", "test_data.json"),
            previous=read_fixed("test_creation", "test_cases.json"),
            code_rules=read("code_rules.json"),
        )

    @classmethod
    def from_artifacts(cls, project: str, manifest: dict, requirements: Optional[dict], scenarios: Optional[dict],
                       form_model: Optional[dict] = None, app_map: Optional[dict] = None,
                       permission_matrix: Optional[dict] = None, test_data: Any = None,
                       previous: Optional[dict] = None, code_rules: Optional[dict] = None) -> "DesignInputs":
        present = {
            "requirements": "present" if requirements else "missing",
            "business_scenarios": "present" if scenarios else "missing",
            "form_model": "present" if form_model else "missing",
            "app_map": "present" if app_map else "missing",
            "permission_matrix": "present" if permission_matrix else "missing",
        }
        limitations = [f"{k} missing: generators that need it produced nothing" for k, v in present.items()
                       if v == "missing" and k not in ("requirements", "business_scenarios")]
        role_logins = _role_logins(manifest)
        modules = _modules(manifest, role_logins)
        acs = _leaf_acs(requirements or {})
        scen = sorted((scenarios or {}).get("scenarios") or [], key=lambda s: str(s.get("scenario_id")))
        states = _states(app_map or {}, modules)
        forms = _forms(form_model or {}, modules)
        transitions = _transitions(app_map or {}, states)
        datasets = _datasets(test_data)
        safety = manifest.get("safety") if isinstance(manifest.get("safety"), dict) else {}
        env = str(manifest.get("environment") or "").lower()
        allow_sec = bool(safety.get("allow_security_probes")) and env not in ("prod", "production")
        prev_hashes = dict((previous or {}).get("page_hashes") or {})
        inp = cls(project=project, modules=modules, acs=acs, scenarios=scen, forms=forms, states=states,
                  transitions=transitions, permission=permission_matrix or {}, datasets=datasets,
                  role_logins=role_logins, allow_security_probes=allow_sec, previous_hashes=prev_hashes,
                  present=present, limitations=limitations)
        inp._link_fields_to_acs()
        inp._apply_code_rules(code_rules)
        inp._resolve_form_modules()
        return inp

    def _apply_code_rules(self, code_rules: Optional[dict]) -> None:
        """Phase 8.2: a white-box rule of the route a form posts to becomes a `code` constraint of the field (it never
        overrides what the DOM, the BRD or an observed message says), with its file:line citation."""
        if not code_rules:
            return
        import re as _re
        from tools.whitebox.python_rules import template_path
        for form in self.forms:
            action = _re.sub(r"/\d+(?=/|$)", "/{id}", (form.action or "").split("?")[0]) or form.url_template
            key = f"{(form.method or 'get').upper()} {template_path(action)}"
            for route in code_rules.get("routes") or []:
                if f"{route.get('method')} {route.get('path_template')}" == key and route.get("stateful_fields"):
                    self.stateful[form.form_id] = sorted(set(self.stateful.get(form.form_id, []))
                                                         | set(route["stateful_fields"]))
            for rule in code_rules.get("rules") or []:
                if key not in (rule.get("routes") or []):
                    continue
                for fld in form.fields:
                    if fld.name != rule.get("field") or rule.get("kind") not in (
                            "length", "range", "pattern", "options", "required"):
                        continue
                    value = {k: v for k, v in (rule.get("value") or {}).items() if k not in ("source", "sources")}
                    _merge_constraint(fld, rule["kind"], value, "code")
                    fld.citations.setdefault(rule["kind"], rule.get("citation") or "")
                    if rule["kind"] == "required":
                        fld.required = True

    # ── derived lookups ──────────────────────────────────────────────────────

    def ac(self, ac_id: str) -> Optional[Dict[str, Any]]:
        return self._ac_index().get(ac_id)

    def _ac_index(self) -> Dict[str, Dict[str, Any]]:
        if not hasattr(self, "_aci"):
            self._aci = {a["id"]: a for a in self.acs}
        return self._aci

    def testable_acs(self) -> List[Dict[str, Any]]:
        return [a for a in self.acs if a["testability"] == "ui"]

    def module_for_path(self, template: str) -> Optional[str]:
        t = norm_template(template)
        for m in self.modules:
            if m["path"] == t:
                return m["id"]
        return None

    def module_role(self, module_id: Optional[str]) -> Optional[str]:
        for m in self.modules:
            if m["id"] == module_id:
                return m.get("role")
        return None

    def page_hashes(self) -> Dict[str, str]:
        return {t: s.structural_hash for t, s in sorted(self.states.items()) if s.structural_hash}

    def changed_pages(self) -> set:
        if not self.previous_hashes:
            return set()
        return {t for t, h in self.page_hashes().items() if self.previous_hashes.get(t) not in (None, h)}

    def valid_value(self, field: Field) -> Any:
        """A value inside every known constraint of the field (the 'all other fields valid' filler)."""
        return valid_value_for(field)

    # ── AC ↔ field linking (deterministic) ────────────────────────────────────

    def _link_fields_to_acs(self) -> None:
        """Link leaf ACs to the form fields they talk about and merge BRD constraints/messages into the fields.

        A field is linked when its label (or a specific name) appears in the AC text AND either the AC's module
        owns the form's page, or the clause naming the field states a constraint or a message. Twin forms
        (same dom_id and fields, e.g. /products/new and /products/{id}/edit) inherit the first form's links."""
        by_sig: Dict[Tuple, Form] = {}
        for form in self.forms:
            sig = (form.dom_id, tuple(f.name for f in form.fields))
            if form.fields and sig in by_sig:
                form.twin_of = by_sig[sig].form_id
            else:
                by_sig.setdefault(sig, form)
        primaries = [f for f in self.forms if not f.twin_of]
        for ac in self.acs:
            if ac["testability"] != "ui":
                continue
            candidates = []
            for form in primaries:
                page_module = self.module_for_path(form.url_template)
                owns = page_module is not None and page_module == ac["module_id"]
                for fld in form.fields:
                    clauses = [c for c in split_clauses(ac["statement"]) if _mentions(c, fld)]
                    if not clauses:
                        continue
                    cons: Dict[str, Dict[str, Any]] = {}
                    msgs: List[str] = []
                    for c in clauses:
                        for k, v in parse_constraints(c).items():
                            if _fits(fld, k):
                                cons.setdefault(k, v)
                        msgs += quoted_messages(c)
                    if not owns and not cons:
                        continue
                    candidates.append((owns, form, fld, cons, msgs))
            # Prefer the forms on the AC's own module page; others only when no owned form matches.
            if any(c[0] for c in candidates):
                candidates = [c for c in candidates if c[0]]
            for _owns, form, fld, cons, msgs in candidates:
                if ac["id"] not in fld.ac_ids:
                    fld.ac_ids.append(ac["id"])
                if ac["id"] not in form.ac_ids:
                    form.ac_ids.append(ac["id"])
                kinds = set()
                for kind, val in cons.items():
                    _merge_constraint(fld, kind, dict(val, ac_id=ac["id"]), "brd")
                    kinds.add(kind)
                for m in msgs:
                    mk = message_kind(m)
                    if mk and _fits_message(fld, mk):
                        kinds.add(_MESSAGE_CONSTRAINT.get(mk, "required"))
                        if mk not in fld.messages or fld.messages[mk]["source"] != "brd":
                            fld.messages[mk] = {"text": m, "source": "brd", "ac_id": ac["id"]}
                for kind in kinds:
                    fld.kind_acs.setdefault(kind, [])
                    if ac["id"] not in fld.kind_acs[kind]:
                        fld.kind_acs[kind].append(ac["id"])
        twins = {f.form_id: f for f in primaries}
        for form in self.forms:
            if form.twin_of:
                src = twins[form.twin_of]
                form.ac_ids = list(src.ac_ids)
                for fld, sfld in zip(form.fields, src.fields):
                    fld.ac_ids = list(sfld.ac_ids)
                    fld.kind_acs = {k: list(v) for k, v in sfld.kind_acs.items()}
                    for kind, val in sfld.constraints.items():
                        if val.get("source") == "brd":
                            _merge_constraint(fld, kind, dict(val), "brd")
                    for mk, mv in sfld.messages.items():
                        if mv["source"] == "brd":
                            fld.messages[mk] = dict(mv)
        for form in self.forms:
            for fld in form.fields:
                fld.ac_ids.sort()
                for v in fld.kind_acs.values():
                    v.sort()
                fld.priority = best_priority(self.ac(a)["priority"] for a in fld.ac_ids if self.ac(a))
            form.ac_ids.sort()

    def _resolve_form_modules(self) -> None:
        """Exact module URL match > module owning most linked ACs > module of the page the form is reached from >
        longest module-path prefix."""
        preds: Dict[str, List[str]] = {}
        for t in self.transitions:
            preds.setdefault(t.to_t, []).append(t.from_t)
        for form in self.forms:
            mid = self.module_for_path(form.url_template)
            if mid is None and form.ac_ids:
                counts: Dict[str, int] = {}
                for a in form.ac_ids:
                    counts[self.ac(a)["module_id"]] = counts.get(self.ac(a)["module_id"], 0) + 1
                mid = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
            if mid is None:
                for p in sorted(set(preds.get(norm_template(form.url_template), []))):
                    mid = self.module_for_path(p)
                    if mid:
                        break
            if mid is None:
                mid = _prefix_module(form.url_template, self.modules)
            form.module_id = mid
        for t, st in self.states.items():
            st.module_id = self.module_for_path(t) or _prefix_module(t, self.modules)


# ── helpers ───────────────────────────────────────────────────────────────────

def _mentions(text: str, fld: Field) -> bool:
    t = text.lower()
    label = re.sub(r"\(.*?\)", "", fld.label or "").strip().lower()
    label = label.splitlines()[0].strip() if label else ""
    cands = [label] if label and len(label) >= 3 else []
    if fld.name and fld.name.lower() not in _GENERIC_NAMES and len(fld.name) >= 3:
        cands.append(fld.name.lower().replace("_", " "))
    if fld.type == "file":
        cands.append("file")
    return any(re.search(rf"\b{re.escape(c)}s?\b", t) for c in cands)


_TEXTISH = {"text", "textarea", "search", "password", "email", "tel", "url"}
_FITS = {
    "length": lambda f: f.type in _TEXTISH,
    "range": lambda f: f.type in _TEXTISH | {"number", "range"},
    "decimals": lambda f: f.type in _TEXTISH | {"number"},
    "size": lambda f: f.type == "file",
    "accept": lambda f: f.type == "file",
    "options": lambda f: f.type in ("select", "radio") or bool(f.options),
    "date": lambda f: f.type in ("date", "datetime-local", "month") or f.type in _TEXTISH,
    "required": lambda f: True,
}
_MESSAGE_CONSTRAINT = {"too_long": "length", "too_short": "length", "out_of_range": "range", "wrong_type": "range",
                       "wrong_accept": "accept", "too_large": "size"}


def _fits(fld: Field, kind: str) -> bool:
    """A stated constraint applies to a field only if the field's type can carry it (no 'MB' on a name box)."""
    return _FITS.get(kind, lambda f: False)(fld)


def _fits_message(fld: Field, kind: str) -> bool:
    return _fits(fld, _MESSAGE_CONSTRAINT.get(kind, "required"))


# Phase 8.2: `code` = a rule read from the app's source (white box) — below what the BRD and the running app say
_PRECEDENCE = {"dom": 0, "brd": 1, "observed": 2, "code": 3, "default": 4}


def _merge_constraint(fld: Field, kind: str, value: Dict[str, Any], source: str) -> None:
    """Merge one constraint key by key: a bound from a higher-precedence source is never overwritten."""
    cur = fld.constraints.get(kind)
    value = dict(value)
    value["source"] = source
    if cur is None:
        fld.constraints[kind] = value
        return
    merged = dict(cur)
    sources = dict(cur.get("sources") or {k: cur.get("source") for k in cur if k not in ("source", "sources", "ac_id")})
    for k, v in value.items():
        if k in ("source", "sources", "ac_id"):
            continue
        if k not in merged or _PRECEDENCE[source] < _PRECEDENCE.get(sources.get(k) or cur.get("source"), 9):
            merged[k] = v
            sources[k] = source
    if value.get("ac_id") and not merged.get("ac_id"):
        merged["ac_id"] = value["ac_id"]
    merged["sources"] = sources
    merged["source"] = min(sources.values(), key=lambda s: _PRECEDENCE.get(s, 9)) if sources else source
    fld.constraints[kind] = merged


def constraint_source(fld: Field, kind: str, bound: str) -> str:
    c = fld.constraints.get(kind) or {}
    return (c.get("sources") or {}).get(bound) or c.get("source") or "default"


def _dom_constraints(c: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    num = lambda v: (int(float(v)) if float(v).is_integer() else float(v)) if v not in (None, "") else None  # noqa: E731
    try:
        if c.get("maxlength") not in (None, "") or c.get("minlength") not in (None, ""):
            out["length"] = {k: num(c.get(f"{k}length")) for k in ("min", "max") if c.get(f"{k}length") not in (None, "")}
        if c.get("min") not in (None, "") or c.get("max") not in (None, ""):
            rng = {k: num(c.get(k)) for k in ("min", "max") if c.get(k) not in (None, "")}
            step = c.get("step")
            if c.get("type") == "number" and (step in (None, "", "1") or str(step) == "1"):
                rng["integer"] = True
            if step not in (None, "", "any"):
                rng["step"] = num(step)
            if c.get("type") in ("date", "datetime-local", "month"):
                out["date"] = {k: c.get(k) for k in ("min", "max") if c.get(k)}
            else:
                out["range"] = rng
        if c.get("accept"):
            out["accept"] = {"values": [a.strip().lower() for a in str(c["accept"]).split(",") if a.strip()]}
        if c.get("pattern"):
            out["pattern"] = {"value": c["pattern"]}
    except (TypeError, ValueError):
        pass
    return out


def _field(form_id: str, raw: Dict[str, Any]) -> Field:
    c = raw.get("constraints") or {}
    ftype = (c.get("type") or raw.get("type") or "text").lower()
    fld = Field(
        form_id=form_id, name=raw.get("name") or "", label=(raw.get("label") or raw.get("name") or "").strip(),
        type=ftype, locator=raw.get("locator"), required=bool(c.get("effective_required") or c.get("required")),
        constraints={}, messages={}, options=[o for o in (c.get("options") or []) if isinstance(o, dict)],
        default_value=c.get("default_value"),
    )
    for kind, val in _dom_constraints(c).items():
        _merge_constraint(fld, kind, val, "dom")
    if fld.required:
        _merge_constraint(fld, "required", {"value": True}, "dom")
    for kind, msg in sorted((raw.get("observed_messages") or {}).items()):
        text = (msg or {}).get("text")
        if not text:
            continue
        fld.messages.setdefault(kind, {"text": text, "source": "observed", "origin": (msg or {}).get("source")})
        for ck, cv in parse_constraints(text).items():
            if ck in ("length", "range", "size", "decimals"):
                _merge_constraint(fld, ck, cv, "observed")
    return fld


def _forms(form_model: dict, modules: List[Dict[str, Any]]) -> List[Form]:
    seen: Dict[Tuple, Form] = {}
    out: List[Form] = []
    for raw in sorted(form_model.get("forms") or [], key=lambda f: (norm_template(f.get("url_template", "")),
                                                                     len(f.get("url_template", "")),
                                                                     f.get("dom_id") or "", f.get("form_id", ""))):
        tmpl = norm_template(raw.get("url_template") or url_path(raw.get("url", "")))
        key = (tmpl, raw.get("dom_id"), tuple(f.get("name") for f in raw.get("fields") or []))
        if key in seen:                       # '/products?page' variant of '/products'
            continue
        form = Form(
            form_id=raw["form_id"], url_template=tmpl, sample_url=raw.get("url") or "",
            dom_id=raw.get("dom_id") or "", method=(raw.get("method") or "get").lower(),
            action=raw.get("action") or "", submit=raw.get("submit") or {}, role=raw.get("role"),
            fields=[_field(raw["form_id"], f) for f in raw.get("fields") or []],
            probes=list(raw.get("probes") or []),
        )
        seen[key] = form
        out.append(form)
    return out


def _states(app_map: dict, modules: List[Dict[str, Any]]) -> Dict[str, State]:
    out: Dict[str, State] = {}
    for s in sorted(app_map.get("states") or [], key=lambda s: (s.get("url_template", ""), s.get("state_id", ""))):
        t = norm_template(s.get("url_template") or url_path(s.get("url", "")))
        roles = list(s.get("roles") or [])
        st = out.get(t)
        if st is None:
            st = out[t] = State(url_template=t, sample_url=s.get("url") or "", roles=[], access={},
                                structural_hash=s.get("structural_hash") or "", elements=[])
        for r in roles:
            if r not in st.roles:
                st.roles.append(r)
            st.access.setdefault(r, s.get("access") or "reachable")
        if not st.elements and s.get("access") == "reachable":
            st.elements = list(s.get("elements") or [])
            st.sample_url = s.get("url") or st.sample_url
            st.structural_hash = s.get("structural_hash") or st.structural_hash
    for st in out.values():
        st.roles.sort()
    return out


def _transitions(app_map: dict, states: Dict[str, State]) -> List[Transition]:
    by_id = {s.get("state_id"): norm_template(s.get("url_template") or url_path(s.get("url", "")))
             for s in app_map.get("states") or []}
    seen: Dict[Tuple, Transition] = {}
    for t in app_map.get("transitions") or []:
        if t.get("unresolved_reason") or not t.get("to_state"):
            continue
        a, b = by_id.get(t.get("from_state")), by_id.get(t.get("to_state"))
        if not a or not b or a == b:
            continue
        el = t.get("element") or {}
        via = (el.get("name") or el.get("href") or "").strip()
        key = (a, b, via)
        roles = sorted(t.get("roles") or [])
        if key in seen:
            seen[key].roles = sorted(set(seen[key].roles) | set(roles))
            continue
        seen[key] = Transition(from_t=a, to_t=b, via=via, role=roles[0] if roles else None, roles=roles,
                               action=t.get("action") or "navigate")
    return [seen[k] for k in sorted(seen)]


def _leaf_acs(requirements: dict) -> List[Dict[str, Any]]:
    out = []
    for req in requirements.get("requirements") or []:
        for ac in req.get("acceptance_criteria") or []:
            if ac.get("children"):
                continue
            out.append({
                "id": ac["id"], "statement": ac.get("statement") or "", "priority": ac.get("priority") or "P3",
                "risk_tags": sorted(ac.get("risk_tags") or []), "testability": ac.get("testability") or "ui",
                "module_id": req.get("module_id"), "req_id": req.get("id"),
            })
    return sorted(out, key=lambda a: _ac_sort_key(a["id"]))


def _ac_sort_key(ac_id: str):
    return [int(p) if p.isdigit() else p for p in re.split(r"[.\-]", ac_id)]


def _role_logins(manifest: dict) -> Dict[str, Dict[str, str]]:
    roles = ((manifest.get("auth") or {}).get("roles") or {}) if isinstance(manifest.get("auth"), dict) else {}
    out: Dict[str, Dict[str, str]] = {}
    for name, cfg in sorted(roles.items()):
        if not isinstance(cfg, dict):
            continue
        if cfg.get("anonymous"):
            out[name] = {}
            continue
        fills = [s["fill"] for s in cfg.get("steps") or [] if isinstance(s, dict) and isinstance(s.get("fill"), dict)]
        creds = {}
        for f in fills:
            sel = str(f.get("selector", "")).lower()
            if "pass" in sel:
                creds["password"] = str(f.get("value", ""))
            elif "user" in sel or "email" in sel or "login" in sel:
                creds["username"] = str(f.get("value", ""))
        out[name] = creds
    return out


def _modules(manifest: dict, role_logins: Dict[str, Dict[str, str]]) -> List[Dict[str, Any]]:
    out = []
    for m in manifest.get("modules") or []:
        if not isinstance(m, dict) or not m.get("id"):
            continue
        users = [str(s["fill"].get("value")) for s in m.get("setup") or []
                 if isinstance(s, dict) and isinstance(s.get("fill"), dict)
                 and "user" in str(s["fill"].get("selector", "")).lower()]
        role = None
        for rname, creds in role_logins.items():
            if creds and creds.get("username") in users:
                role = rname
                break
        if role is None and not m.get("setup"):
            role = next((r for r, c in role_logins.items() if not c), None)
        out.append({"id": m["id"], "name": m.get("name") or m["id"], "url": m.get("url") or "",
                    "path": url_path(m.get("url") or ""), "role": role})
    return out


def _prefix_module(template: str, modules: List[Dict[str, Any]]) -> Optional[str]:
    t = norm_template(template)
    best = None
    for m in modules:
        p = m["path"]
        if p != "/" and (t == p or t.startswith(p + "/")) and (best is None or len(p) > len(best[0])):
            best = (p, m["id"])
    return best[1] if best else None


def _datasets(test_data: Any) -> Dict[str, Dict[str, Any]]:
    if isinstance(test_data, dict):
        test_data = test_data.get("datasets") or []
    out = {}
    for rec in test_data or []:
        if isinstance(rec, dict) and rec.get("scenario_id"):
            out[rec["scenario_id"]] = rec
    return out


# ── valid filler values ────────────────────────────────────────────────────────

def valid_value_for(fld: Field) -> Any:
    c = fld.constraints
    if fld.type == "select" or fld.options:
        opts = [o for o in fld.options if o.get("value") not in (None, "") and not o.get("disabled")]
        allowed = (c.get("options") or {}).get("values")
        if allowed:
            opts = [o for o in opts if o.get("text") in allowed or o.get("value") in allowed] or opts
        return (opts[0].get("text") or opts[0].get("value")) if opts else None
    if fld.type == "file":
        exts = (c.get("accept") or {}).get("values") or [".csv"]
        return {"file_name": f"valid{exts[0]}", "size_bytes": 1024}
    if "range" in c:
        r = c["range"]
        lo = r.get("min", 0)
        hi = r.get("max", lo + 10 if lo is not None else 10)
        v = lo if not r.get("min_exclusive") else lo + 1
        v = v if v is not None else 1
        if hi is not None and v > hi:
            v = hi
        return str(int(v) if float(v).is_integer() else v) if (r.get("integer") or float(v).is_integer()) else str(v)
    if fld.type == "number":
        return "1"
    if fld.type == "email":
        return "qa.user@example.com"
    if fld.type == "date":
        return (c.get("date") or {}).get("min") or "2024-06-15"
    if fld.default_value not in (None, ""):
        return fld.default_value
    length = c.get("length") or {}
    n = max(int(length.get("min") or 1), min(8, int(length.get("max") or 8)))
    return ("Valid" + "x" * n)[:n] if n >= 5 else "x" * n
