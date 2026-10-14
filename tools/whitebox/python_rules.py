"""
python_rules.py — Phase 8.2: white-box rules from Python source (stdlib `ast`, no import of the code under test).

Extracts, per file:
  routes   FastAPI / Flask / APIRouter / Blueprint decorators and add_api_route / add_url_rule: method, templated path,
           handler, its parameters (path / query / form / file / JSON body), auth style (session redirect / 401 API),
           role checks, access-check helpers, literal status codes, the validation-error status, response keys.
  rules    input rules with a `file:line` citation:
             if guards   `not x` (required), `len(x) > N` (length), `x < N` (range), `x not in C` (options),
                         `not RE.match(x)` (pattern) — a guard counts when its branch rejects (append / raise / return)
             pydantic    Field(...)/constr/conint/confloat arguments, required = no default
             marshmallow fields.X(required=..., validate=Length/Range/OneOf/Regexp)
           A variable is tied to its field through `x = ...data.get("f")...`, `data["f"]`, a `Form(...)` / query
           parameter, or a helper call `parse_quantity(quantity)` (the helper's parameter gets the caller's field).
           Feature-flag conditions (`is_on("X")`, `flags.x`, `settings.FEATURE_X`) are recorded as `guards`; the rule
           kept is the flag-off behaviour (an IfExp on a flag takes its else branch).
"""

from __future__ import annotations

import ast
import re
from typing import Any, Dict, List, Optional, Tuple

HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")
_FLAG_CALLS = re.compile(r"^(is_on|is_enabled|feature_enabled|flag|is_active)$|feature", re.I)
_REJECT_NAMES = ("errors", "error", "problems", "messages")
_AUTH_401 = re.compile(r"\bapi_auth\(|require_api_auth|get_current_user|verify_token|Depends\(\w*auth", re.I)
_CONVERSIONS = {"str", "int", "float", "Decimal", "strip", "lower", "upper", "bool", "lstrip", "rstrip", "isinstance",
                "len"}
_AUTH_REDIRECT = re.compile(r"to_login|login_required|redirect.*login", re.I)


def template_path(path: str) -> str:
    """'/products/{pid}' '/products/<int:pid>' '/products/:pid' -> '/products/{id}' (one placeholder name)."""
    p = re.sub(r"<(?:\w+:)?\w+>", "{id}", path or "")
    p = re.sub(r"\{[^}]+\}", "{id}", p)
    p = re.sub(r":\w+", "{id}", p)
    return p if p == "/" else p.rstrip("/") or "/"


def _const(node: ast.AST, consts: Dict[str, Any]) -> Any:
    """Literal value of a node, resolving module constants (ints, floats, strings, tuples, sets, lists)."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name) and node.id in consts:
        return consts[node.id]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        v = _const(node.operand, consts)
        return -v if isinstance(v, (int, float)) else None
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        vals = [_const(e, consts) for e in node.elts]
        return None if any(v is None for v in vals) else list(vals)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mult, ast.Add, ast.Sub)):
        a, b = _const(node.left, consts), _const(node.right, consts)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return a * b if isinstance(node.op, ast.Mult) else a + b if isinstance(node.op, ast.Add) else a - b
    if isinstance(node, ast.Call) and _name(node.func) in ("frozenset", "set", "tuple", "list") and node.args:
        return _const(node.args[0], consts)
    return None


def _name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _name(node.func)
    return ""


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    return ""


def module_constants(tree: ast.Module) -> Dict[str, Any]:
    """NAME = literal / re.compile(r"...") (pattern string) at module level, also inside functions (first wins)."""
    out: Dict[str, Any] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            if value is None:
                continue
            if isinstance(node, ast.Assign) and len(targets) == 1 and isinstance(targets[0], ast.Tuple)                     and isinstance(value, ast.Tuple) and len(targets[0].elts) == len(value.elts):
                for t, v in zip(targets[0].elts, value.elts):          # QTY_MIN, QTY_MAX = 1, 99
                    cv = _const(v, out)
                    if isinstance(t, ast.Name) and cv is not None and t.id not in out:
                        out[t.id] = cv
                continue
            for t in targets:
                if not isinstance(t, ast.Name) or t.id in out:
                    continue
                if isinstance(value, ast.Call) and _dotted(value.func) in ("re.compile", "compile") and value.args:
                    pat = _const(value.args[0], out)
                    if isinstance(pat, str):
                        out[t.id] = {"__regex__": pat}
                    continue
                v = _const(value, out)
                if v is not None:
                    out[t.id] = v
    return out


def _is_flag(node: ast.AST) -> bool:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return _is_flag(node.operand)
    if isinstance(node, ast.Call):
        return bool(_FLAG_CALLS.search(_name(node.func)))
    if isinstance(node, ast.Attribute):
        return bool(re.search(r"feature|flag", _dotted(node), re.I))
    return False


def _flag_text(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return "flag"


def _strip_flags(test: ast.AST, guards: List[str]) -> Optional[ast.AST]:
    """Remove feature-flag operands (recorded in `guards`); an IfExp on a flag keeps its flag-off (else) side."""
    if _is_flag(test):
        guards.append(_flag_text(test))
        return None
    if isinstance(test, ast.BoolOp):
        keep = []
        for v in test.values:
            s = _strip_flags(v, guards)
            if s is not None:
                keep.append(s)
        if not keep:
            return None
        return keep[0] if len(keep) == 1 else ast.BoolOp(op=test.op, values=keep)
    if isinstance(test, ast.IfExp) and _is_flag(test.test):
        guards.append(f"when not {_flag_text(test.test)}")
        return _strip_flags(test.orelse, guards)
    return test


def _rejects(body: List[ast.stmt]) -> bool:
    """The branch rejects the input: appends to an errors list, raises, returns (None / an error), or aborts."""
    for st in body:
        for n in ast.walk(st):
            if isinstance(n, ast.Raise) or isinstance(n, ast.Return):
                return True
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("append", "add") \
                    and _name(n.func.value).lower() in _REJECT_NAMES:
                return True
            if isinstance(n, ast.Call) and _name(n.func) in ("abort", "HTTPException", "ValidationError"):
                return True
    return False


def _message(body: List[ast.stmt], consts: Dict[str, Any]) -> Optional[str]:
    for st in body:
        for n in ast.walk(st):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("append", "add") \
                    and n.args:
                v = _const(n.args[0], consts)
                if isinstance(v, str):
                    return v
            if isinstance(n, ast.Call) and _name(n.func) in ("HTTPException", "ValidationError", "abort"):
                for kw in n.keywords:
                    v = _const(kw.value, consts)
                    if kw.arg in ("detail", "message", "description") and isinstance(v, str):
                        return v
    return None


class _FieldMap:
    """Variable -> request field for one function."""

    def __init__(self, func: ast.AST, param_fields: Dict[str, str]):
        self.vars: Dict[str, str] = dict(param_fields)
        self.lookups: set = set()        # vars holding a LOOKUP result (store.get(pid)) — not the raw input
        self.ints: set = set()           # vars converted with int(...) — their ranges step by 1
        for n in ast.walk(func):
            if isinstance(n, ast.Assign) and len(n.targets) == 1:
                tgt = n.targets[0]
                field = _field_read(n.value)
                if field is None:
                    src = _first_name(n.value)
                    field = self.vars.get(src) if src else None
                    if field and _is_lookup(n.value):
                        if isinstance(tgt, ast.Name):
                            self.lookups.add(tgt.id)
                if isinstance(tgt, ast.Name) and field:
                    self.vars.setdefault(tgt.id, field)
                    if isinstance(n.value, ast.Call) and _name(n.value.func) == "int":
                        self.ints.add(tgt.id)

    def field_of(self, node: ast.AST) -> Optional[str]:
        direct = _field_read(node)
        if direct:
            return direct
        if isinstance(node, ast.Name):
            return self.vars.get(node.id)
        if isinstance(node, ast.Call) and node.args and _name(node.func) in ("len", "str", "int", "float", "Decimal",
                                                                             "strip", "lower"):
            return self.field_of(node.args[0])
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):    # name.strip(), x.lower()
            return self.field_of(node.func.value)
        return None


def _is_lookup(node: ast.AST) -> bool:
    """The value is derived through a call that is not a plain conversion (a DB / dict lookup, a parser)."""
    return any(isinstance(c, ast.Call) and _name(c.func) not in _CONVERSIONS for c in ast.walk(node))


def _field_read(node: ast.AST) -> Optional[str]:
    """data.get("f") / data["f"] / request.form["f"] anywhere inside the expression."""
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("get", "getlist") \
                and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
            return n.args[0].value
        if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant) and isinstance(n.slice.value, str) \
                and _name(n.value) in ("data", "form", "json", "body", "payload", "args", "params", "values"):
            return n.slice.value
    return None


def _first_name(node: ast.AST) -> Optional[str]:
    """The first variable the expression reads — never the name of a function it calls."""
    callees = {id(c.func) for c in ast.walk(node) if isinstance(c, ast.Call)}
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and id(n) not in callees and n.id not in ("str", "int", "float", "len", "Decimal"):
            return n.id
    return None


def _rule(field, kind, value, path, line, func, guards, message):
    r = {"field": field, "kind": kind, "value": value, "source": "code", "citation": f"{path}:{line}",
         "function": func}
    if guards:
        r["guards"] = sorted(set(guards))
    if message:
        r["message"] = message
    return r


def _rules_from_test(test: ast.AST, fmap: _FieldMap, consts, path, line, func, guards, message) -> List[dict]:
    out: List[dict] = []
    if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.Or):
        for v in test.values:
            out += _rules_from_test(v, fmap, consts, path, line, func, guards, message)
        return out
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        inner = test.operand
        if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute) and inner.func.attr in (
                "match", "fullmatch", "search") and inner.args:
            rx = consts.get(_name(inner.func.value)) if isinstance(inner.func.value, ast.Name) else None
            field = fmap.field_of(inner.args[0])
            if field and isinstance(rx, dict):
                out.append(_rule(field, "pattern", {"value": rx["__regex__"]}, path, line, func, guards, message))
            return out
        field = fmap.field_of(inner)
        if field and not (isinstance(inner, ast.Name) and inner.id in fmap.lookups):
            out.append(_rule(field, "required", {"value": True}, path, line, func, guards, message))
        return out
    if isinstance(test, ast.Compare) and len(test.ops) == 1:
        left, op, right = test.left, test.ops[0], test.comparators[0]
        if isinstance(op, (ast.NotIn,)):
            field, vals = fmap.field_of(left), _const(right, consts)
            if field and isinstance(vals, list):
                out.append(_rule(field, "options", {"values": vals}, path, line, func, guards, message))
            return out
        if isinstance(op, (ast.Is, ast.Eq)) and isinstance(right, ast.Constant) and right.value in (None, ""):
            field = fmap.field_of(left)
            if field and not (isinstance(left, ast.Name) and left.id in fmap.lookups):   # "not found", not input
                out.append(_rule(field, "required", {"value": True}, path, line, func, guards, message))
            return out
        num = _const(right, consts)
        if not isinstance(num, (int, float)) or isinstance(num, bool):
            return out
        is_len = isinstance(left, ast.Call) and _name(left.func) == "len"
        field = fmap.field_of(left)
        if not field:
            return out
        kind = "length" if is_len else "range"
        integer = is_len or (isinstance(left, ast.Name) and left.id in fmap.ints)
        step = 1 if integer else 0.01
        # the guard is the REJECTED region: `x > N` rejects -> max N; `x >= N` rejects -> max N-1 ...
        if isinstance(op, ast.Gt):
            val = {"max": num}
        elif isinstance(op, ast.GtE):
            val = {"max": num - step if integer else num, **({} if integer else {"max_exclusive": True})}
        elif isinstance(op, ast.Lt):
            val = {"min": num}
        elif isinstance(op, ast.LtE):
            val = {"min": num + step if integer else num, **({} if integer else {"min_exclusive": True})}
        else:
            return out
        if kind == "range" and integer:
            val["integer"] = True
        out.append(_rule(field, kind, val, path, line, func, guards, message))
    return out


def _func_rules(func: ast.AST, fmap: _FieldMap, consts, path) -> List[dict]:
    out: List[dict] = []

    def visit(stmts: List[ast.stmt], outer_guards: List[str]):
        for st in stmts:
            if isinstance(st, ast.If):
                guards = list(outer_guards)
                test = _strip_flags(st.test, guards)
                if test is not None and _rejects(st.body):
                    # a nested `if flag:` around the rejection is a guard of this rule too
                    inner_guards = list(guards)
                    for n in st.body:
                        if isinstance(n, ast.If) and _is_flag(n.test):
                            inner_guards.append(_flag_text(n.test))
                    out.extend(_rules_from_test(test, fmap, consts, path, st.lineno, func.name, inner_guards,
                                                _message(st.body, consts)))
                visit(st.body, guards)
                visit(st.orelse, guards)
            elif isinstance(st, (ast.For, ast.While, ast.With, ast.Try, ast.AsyncWith, ast.AsyncFor)):
                for attr in ("body", "orelse", "finalbody"):
                    visit(getattr(st, attr, []) or [], outer_guards)
                for h in getattr(st, "handlers", []) or []:
                    visit(h.body, outer_guards)
    visit(func.body, [])
    return out


# ── pydantic / marshmallow ───────────────────────────────────────────────────

_PYD_KW = {"max_length": ("length", "max"), "min_length": ("length", "min"), "le": ("range", "max"),
           "ge": ("range", "min"), "lt": ("range", "max"), "gt": ("range", "min"), "max_items": ("length", "max"),
           "min_items": ("length", "min")}


def _pydantic_rules(cls: ast.ClassDef, consts, path) -> List[dict]:
    out = []
    for st in cls.body:
        if not isinstance(st, ast.AnnAssign) or not isinstance(st.target, ast.Name):
            continue
        field = st.target.id
        ann = ast.unparse(st.annotation) if st.annotation is not None else ""
        optional = "Optional" in ann or "None" in ann
        calls = [n for n in ast.walk(st) if isinstance(n, ast.Call)]
        has_default = st.value is not None and not (
            isinstance(st.value, ast.Call) and _name(st.value.func) == "Field"
            and st.value.args and isinstance(st.value.args[0], ast.Constant) and st.value.args[0].value is Ellipsis)
        if isinstance(st.value, ast.Call) and _name(st.value.func) == "Field" and not st.value.args and not any(
                k.arg == "default" for k in st.value.keywords):
            has_default = False
        if not has_default and not optional:
            out.append(_rule(field, "required", {"value": True}, path, st.lineno, cls.name, [], None))
        for c in calls:
            if _name(c.func) not in ("Field", "constr", "conint", "confloat", "condecimal", "conlist", "StringConstraints"):
                continue
            agg: Dict[str, Dict[str, Any]] = {}
            for kw in c.keywords:
                v = _const(kw.value, consts)
                if kw.arg in _PYD_KW and isinstance(v, (int, float)):
                    kind, bound = _PYD_KW[kw.arg]
                    if kw.arg == "lt":
                        v = v - 1 if isinstance(v, int) else v
                    if kw.arg == "gt":
                        v = v + 1 if isinstance(v, int) else v
                    agg.setdefault(kind, {})[bound] = v
                elif kw.arg in ("regex", "pattern") and isinstance(v, str):
                    agg["pattern"] = {"value": v}
            for kind, val in agg.items():
                out.append(_rule(field, kind, val, path, st.lineno, cls.name, [], None))
        if "Literal[" in ann:
            vals = re.findall(r"['\"]([^'\"]+)['\"]", ann.split("Literal[", 1)[1])
            if vals:
                out.append(_rule(field, "options", {"values": vals}, path, st.lineno, cls.name, [], None))
    return out


def _marshmallow_rules(cls: ast.ClassDef, consts, path) -> List[dict]:
    out = []
    for st in cls.body:
        if not isinstance(st, ast.Assign) or len(st.targets) != 1 or not isinstance(st.targets[0], ast.Name):
            continue
        if not isinstance(st.value, ast.Call) or _dotted(st.value.func).split(".")[0] not in ("fields", "ma"):
            continue
        field = st.targets[0].id
        for kw in st.value.keywords:
            if kw.arg == "required" and _const(kw.value, consts) is True:
                out.append(_rule(field, "required", {"value": True}, path, st.lineno, cls.name, [], None))
            if kw.arg == "validate":
                vals = kw.value.elts if isinstance(kw.value, (ast.List, ast.Tuple)) else [kw.value]
                for v in vals:
                    if not isinstance(v, ast.Call):
                        continue
                    kind = _name(v.func)
                    kws = {k.arg: _const(k.value, consts) for k in v.keywords}
                    if kind == "Length":
                        val = {b: kws[b] for b in ("min", "max") if isinstance(kws.get(b), int)}
                        if val:
                            out.append(_rule(field, "length", val, path, st.lineno, cls.name, [], None))
                    elif kind == "Range":
                        val = {b: kws[b] for b in ("min", "max") if isinstance(kws.get(b), (int, float))}
                        if val:
                            out.append(_rule(field, "range", val, path, st.lineno, cls.name, [], None))
                    elif kind == "OneOf" and v.args:
                        choices = _const(v.args[0], consts)
                        if isinstance(choices, list):
                            out.append(_rule(field, "options", {"values": choices}, path, st.lineno, cls.name, [], None))
                    elif kind == "Regexp" and v.args:
                        rx = _const(v.args[0], consts)
                        if isinstance(rx, str):
                            out.append(_rule(field, "pattern", {"value": rx}, path, st.lineno, cls.name, [], None))
    return out


# ── routes ──────────────────────────────────────────────────────────────────

def _route_decorators(func: ast.AST, prefixes: Dict[str, str]) -> List[Tuple[str, str]]:
    out = []
    for dec in getattr(func, "decorator_list", []):
        if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute) or not dec.args:
            continue
        path = dec.args[0].value if isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str) else None
        if path is None:
            continue
        owner = _name(dec.func.value)
        prefix = prefixes.get(owner, "")
        attr = dec.func.attr
        if attr in HTTP_METHODS:
            out.append((attr.upper(), prefix + path))
        elif attr in ("route", "api_route"):
            methods = ["GET"]
            for kw in dec.keywords:
                if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
                    methods = [str(_const(e, {})).upper() for e in kw.value.elts if _const(e, {})]
            out += [(m, prefix + path) for m in methods]
    return out


def _router_prefixes(tree: ast.Module) -> Dict[str, str]:
    """router = APIRouter(prefix="/api") / Blueprint("x", __name__, url_prefix="/x")."""
    out = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) \
                and isinstance(n.value, ast.Call) and _name(n.value.func) in ("APIRouter", "Blueprint"):
            for kw in n.value.keywords:
                if kw.arg in ("prefix", "url_prefix") and isinstance(kw.value, ast.Constant):
                    out[n.targets[0].id] = kw.value.value
    return out


def _route_params(func: ast.AST, path: str) -> Dict[str, Any]:
    path_params = re.findall(r"\{(\w+)(?::[^}]*)?\}|<(?:\w+:)?(\w+)>", path)
    path_names = {a or b for a, b in path_params}
    params: Dict[str, Any] = {"path": sorted(path_names), "query": [], "form": [], "file": [], "json_body": False}
    args = func.args
    defaults = [None] * (len(args.args) - len(args.defaults)) + list(args.defaults)
    for a, d in zip(args.args, defaults):
        if a.arg in path_names or a.arg in ("request", "self", "req", "db", "session", "response"):
            continue
        ann = ast.unparse(a.annotation) if a.annotation is not None else ""
        if isinstance(d, ast.Call) and _name(d.func) == "Form":
            params["form"].append(a.arg)
        elif isinstance(d, ast.Call) and _name(d.func) in ("File", "UploadFile") or "UploadFile" in ann:
            params["file"].append(a.arg)
        elif "Request" in ann:
            continue
        else:
            params["query"].append(a.arg)
    for n in ast.walk(func):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("json", "get_json"):
            params["json_body"] = True
    return params


def _statuses(func: ast.AST) -> List[int]:
    out = set()
    for n in ast.walk(func):
        if isinstance(n, ast.keyword) and n.arg == "status_code" and isinstance(n.value, ast.Constant) \
                and isinstance(n.value.value, int):
            out.add(n.value.value)
        if isinstance(n, ast.Call) and _name(n.func) in ("JSONResponse", "HTMLResponse", "Response",
                                                         "RedirectResponse", "abort") and len(n.args) >= 2 \
                and isinstance(n.args[1], ast.Constant) and isinstance(n.args[1].value, int):
            out.add(n.args[1].value)
        if isinstance(n, ast.Call) and _name(n.func) == "abort" and n.args and isinstance(n.args[0], ast.Constant):
            out.add(n.args[0].value)
    return sorted(s for s in out if isinstance(s, int))


def _error_status(func: ast.AST, validators: List[str]) -> Optional[int]:
    """`errors = validate_x(...)` then `if errors: return ...(status_code=4xx)` -> 4xx."""
    if not validators:
        return None
    for n in ast.walk(func):
        if isinstance(n, ast.If) and isinstance(n.test, ast.Name) and n.test.id in _REJECT_NAMES:
            codes = _statuses(ast.Module(body=n.body, type_ignores=[]))
            for st in n.body:
                for c in ast.walk(st):
                    if isinstance(c, ast.Call) and len(c.args) >= 5 and isinstance(c.args[-1], ast.Constant) \
                            and isinstance(c.args[-1].value, int) and 400 <= c.args[-1].value < 500:
                        codes.append(c.args[-1].value)
            bad = [c for c in codes if 400 <= c < 500]
            if bad:
                return bad[0]
    return None


def _stateful_fields(func: ast.AST, fmap: "_FieldMap") -> List[str]:
    """Fields the handler combines with stored state before checking (`new = items.get(id, 0) + qty; if new > MAX`):
    the accepted limit then depends on what is already stored, not on the request alone."""
    out = set()
    for n in ast.walk(func):
        if isinstance(n, ast.Assign) and isinstance(n.value, (ast.BinOp, ast.IfExp)):
            names = {x.id for x in ast.walk(n.value) if isinstance(x, ast.Name)}
            has_lookup = any(isinstance(c, ast.Call) and _name(c.func) not in _CONVERSIONS for c in ast.walk(n.value))
            fields = {fmap.vars[x] for x in names if x in fmap.vars}
            if has_lookup and fields:
                out |= fields
    return sorted(out)


def _preconditions(func: ast.AST, fmap: "_FieldMap") -> List[str]:
    """`if product_id not in items: return 400` where `items` is stored state: the request is valid only when the store
    already holds something (a cart line, a draft) — a generic test cannot set that up."""
    out = []
    for n in ast.walk(func):
        if isinstance(n, ast.If) and isinstance(n.test, ast.Compare) and len(n.test.ops) == 1                 and isinstance(n.test.ops[0], (ast.In, ast.NotIn)) and isinstance(n.test.comparators[0], ast.Name):
            field = fmap.field_of(n.test.left)
            store = n.test.comparators[0].id
            if field and store not in fmap.vars and _rejects(n.body):
                out.append(f"{field} must already be in {store} (line {n.lineno})")
    return out


def _role_checks(func: ast.AST) -> List[str]:
    roles = set()
    for n in ast.walk(func):
        if isinstance(n, ast.Compare) and len(n.ops) == 1 and isinstance(n.ops[0], (ast.NotEq, ast.Eq, ast.NotIn, ast.In)):
            left = ast.unparse(n.left)
            if re.search(r"role|is_admin|is_staff|permission", left, re.I):
                v = _const(n.comparators[0], {})
                if isinstance(v, str):
                    roles.add(v)
                elif isinstance(v, list):
                    roles.update(str(x) for x in v)
    return sorted(roles)


def _response_keys(func: ast.AST, funcs: Dict[str, ast.AST]) -> List[str]:
    for n in ast.walk(func):
        if isinstance(n, ast.Return) and n.value is not None:
            v = n.value
            if isinstance(v, ast.Dict):
                return sorted(k.value for k in v.keys if isinstance(k, ast.Constant) and isinstance(k.value, str))
            if isinstance(v, ast.Call) and _name(v.func) in funcs and _name(v.func).endswith("_json"):
                return _response_keys(funcs[_name(v.func)], funcs)
    return []


def extract_file(path: str, source: str, rel: Optional[str] = None,
                 shared_consts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """{routes, rules, flags, functions: {name: (start, end)}, calls: {func: [callees]}} for one Python file.
    `shared_consts`: constants of the other files of the project (imports are resolved by name)."""
    rel = rel or path
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {"routes": [], "rules": [], "flags": [], "functions": {}, "calls": {}}
    consts = {**(shared_consts or {}), **module_constants(tree)}
    prefixes = _router_prefixes(tree)
    funcs: Dict[str, ast.AST] = {}
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.setdefault(n.name, n)
    calls = {name: sorted({_name(c.func) for c in ast.walk(f) if isinstance(c, ast.Call)
                           and _name(c.func) in funcs and _name(c.func) != name}) for name, f in funcs.items()}

    # helper parameter -> field, from the call sites (`parse_quantity(quantity)` in a handler with a quantity field)
    route_funcs = {name for name, f in funcs.items() if _route_decorators(f, prefixes)}
    param_fields: Dict[str, Dict[str, str]] = {name: {} for name in funcs}
    for name in route_funcs:
        f = funcs[name]
        param_fields[name] = {a.arg: a.arg for a in f.args.args if a.arg not in ("request", "self")}
    for _ in range(2):                   # two hops: handler -> helper -> helper
        for name, f in funcs.items():
            fmap = _FieldMap(f, param_fields[name])
            for c in ast.walk(f):
                if isinstance(c, ast.Call) and _name(c.func) in funcs:
                    callee = funcs[_name(c.func)]
                    for i, arg in enumerate(c.args):
                        fld = fmap.field_of(arg)
                        if fld and i < len(callee.args.args):
                            param_fields[_name(c.func)].setdefault(callee.args.args[i].arg, fld)

    rules: List[dict] = []
    for name, f in funcs.items():
        rules += _func_rules(f, _FieldMap(f, param_fields[name]), consts, rel)
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef):
            bases = {_name(b) for b in n.bases}
            if bases & {"BaseModel", "BaseSettings"} or any("BaseModel" in _dotted(b) for b in n.bases):
                rules += _pydantic_rules(n, consts, rel)
            if bases & {"Schema"} or any(_dotted(b).endswith("Schema") for b in n.bases):
                rules += _marshmallow_rules(n, consts, rel)

    def reach(name: str, seen=None) -> List[str]:
        seen = seen or set()
        for c in calls.get(name, []):
            if c not in seen:
                seen.add(c)
                reach(c, seen)
        return sorted(seen)

    rule_funcs = {r["function"] for r in rules}
    routes = []
    for name in route_funcs:
        f = funcs[name]
        body_src = ast.unparse(f)
        callees = reach(name)
        validators = [c for c in callees if c in rule_funcs]
        access = [c for c in callees if re.search(r"can_|allowed|owns|permission|authori", c)]
        for method, p in _route_decorators(f, prefixes):
            routes.append({
                "method": method, "path": p, "path_template": template_path(p), "handler": name,
                "citation": f"{rel}:{f.lineno}", "params": _route_params(f, p),
                "auth": ("api_401" if _AUTH_401.search(body_src) else
                         "session_redirect" if _AUTH_REDIRECT.search(body_src) else None),
                "roles": _role_checks(f), "access_checks": access, "validators": validators,
                "statuses": _statuses(f), "error_status": _error_status(f, validators),
                "response_keys": _response_keys(f, funcs),
                "stateful_fields": _stateful_fields(f, _FieldMap(f, param_fields[name])),
                "preconditions": _preconditions(f, _FieldMap(f, param_fields[name])),
            })
    flags = sorted({str(_const(c.args[0], consts)) for c in ast.walk(tree)
                    if isinstance(c, ast.Call) and _FLAG_CALLS.search(_name(c.func)) and c.args
                    and isinstance(_const(c.args[0], consts), str)})
    functions = {name: (f.lineno, getattr(f, "end_lineno", f.lineno)) for name, f in funcs.items()}
    return {"routes": routes, "rules": rules, "flags": flags, "functions": functions, "calls": calls}
