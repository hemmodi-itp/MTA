"""
js_rules.py — Phase 8.2: white-box rules from JavaScript / TypeScript source (pattern-based; no JS parser in MTA).

Schema libraries, one rule per constraint with a `file:line` citation:
  zod              name: z.string().min(1).max(50).regex(/x/), z.number().int().min(0).max(99), z.enum([...]),
                   .optional() / .nullable() make it not required
  yup              name: yup.string().required().max(50).matches(/x/), .oneOf([...]), .min/.max on numbers
  joi              name: Joi.string().min(1).max(50).required().pattern(/x/), .valid('a','b')
  class-validator  @IsNotEmpty() @MaxLength(50) @MinLength(1) @Min(0) @Max(99) @Matches(/x/) @IsIn([...]) on `name`
Routes: Express / Koa routers (app.get('/x/:id', ...), router.post(...)) — templated like the Python side.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from tools.whitebox.python_rules import template_path

_CHAIN = r"((?:\s*\.\s*\w+\s*\([^()]*(?:\([^()]*\)[^()]*)*\))*)"
_ZOD = re.compile(r"(\w+)\s*:\s*z\s*\.\s*(string|number|enum|boolean|date)\s*\(([^()]*(?:\[[^\]]*\])?[^()]*)\)" + _CHAIN)
_YUP = re.compile(r"(\w+)\s*:\s*(?:yup|Yup|y)\s*\.\s*(string|number|mixed|date|boolean)\s*\(\s*\)" + _CHAIN)
_JOI = re.compile(r"(\w+)\s*:\s*Joi\s*\.\s*(string|number|any|date|boolean)\s*\(\s*\)" + _CHAIN)
_CALL = re.compile(r"\.\s*(\w+)\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)")
_DECORATOR = re.compile(r"@(\w+)\(([^)]*)\)")
_PROP = re.compile(r"^\s*(?:readonly\s+)?(\w+)\s*[?!]?\s*:\s*[\w\[\]<>|' ]+;")
_ROUTE = re.compile(r"\b(app|router|api|server)\s*\.\s*(get|post|put|patch|delete)\s*\(\s*['\"`]([^'\"`]+)['\"`]")


def _num(text: str):
    try:
        v = float(text.strip())
        return int(v) if v.is_integer() else v
    except ValueError:
        return None


def _regex(text: str):
    m = re.match(r"\s*/(.+)/[gimsuy]*\s*$", text)
    return m.group(1) if m else None


def _values(text: str) -> List[Any]:
    text = text.strip()
    if text.startswith("["):
        text = text[1:text.rfind("]")]
    return [v.strip().strip("'\"`") for v in text.split(",") if v.strip()]


def _rule(field, kind, value, rel, line, lib):
    return {"field": field, "kind": kind, "value": value, "source": "code", "citation": f"{rel}:{line}",
            "function": lib}


def _chain_rules(field: str, base: str, base_args: str, chain: str, rel: str, line: int, lib: str) -> List[dict]:
    out: List[dict] = []
    calls = [(m.group(1), m.group(2)) for m in _CALL.finditer(chain or "")]
    names = [c for c, _ in calls]
    is_str = base in ("string",)
    optional = any(c in ("optional", "nullable", "nullish", "allow") for c in names)
    if lib == "zod" and not optional:
        out.append(_rule(field, "required", {"value": True}, rel, line, lib))
    if lib in ("yup", "joi") and "required" in names:
        out.append(_rule(field, "required", {"value": True}, rel, line, lib))
    if lib == "zod" and base == "enum":
        vals = _values(base_args)
        if vals:
            out.append(_rule(field, "options", {"values": vals}, rel, line, lib))
    length: Dict[str, Any] = {}
    rng: Dict[str, Any] = {}
    for name, args in calls:
        n = _num(args.split(",")[0]) if args.strip() else None
        if name in ("min", "max", "length") and n is not None:
            target = length if is_str else rng
            if name == "length":
                target.update({"min": n, "max": n})
            else:
                target[name] = n
        elif name in ("positive",):
            rng["min"] = 1 if "int" in names or "integer" in names else 0.01
        elif name in ("nonnegative",):
            rng["min"] = 0
        elif name in ("int", "integer"):
            rng["integer"] = True
        elif name in ("regex", "matches", "pattern"):
            rx = _regex(args.split(",")[0])
            if rx:
                out.append(_rule(field, "pattern", {"value": rx}, rel, line, lib))
        elif name in ("oneOf", "valid") and args.strip():
            out.append(_rule(field, "options", {"values": _values(args)}, rel, line, lib))
        elif name == "email":
            out.append(_rule(field, "pattern", {"value": "email"}, rel, line, lib))
    if length:
        out.append(_rule(field, "length", length, rel, line, lib))
    if {k for k in rng if k != "integer"}:
        out.append(_rule(field, "range", rng, rel, line, lib))
    return out


def _class_validator(lines: List[str], rel: str) -> List[dict]:
    out: List[dict] = []
    pending: List[tuple] = []
    for i, line in enumerate(lines, start=1):
        decs = _DECORATOR.findall(line)
        if decs and line.strip().startswith("@"):
            pending += [(name, args, i) for name, args in decs]
            continue
        prop = _PROP.match(line)
        if prop and pending:
            field = prop.group(1)
            optional = any(n == "IsOptional" for n, _, _ in pending)
            length: Dict[str, Any] = {}
            rng: Dict[str, Any] = {}
            for name, args, ln in pending:
                n = _num(args.split(",")[0]) if args.strip() else None
                if name in ("IsNotEmpty", "IsDefined") and not optional:
                    out.append(_rule(field, "required", {"value": True}, rel, ln, "class-validator"))
                elif name == "MaxLength" and n is not None:
                    length["max"] = n
                elif name == "MinLength" and n is not None:
                    length["min"] = n
                elif name == "Length" and args.strip():
                    parts = [_num(x) for x in args.split(",")[:2]]
                    if parts[0] is not None:
                        length["min"] = parts[0]
                    if len(parts) > 1 and parts[1] is not None:
                        length["max"] = parts[1]
                elif name == "Max" and n is not None:
                    rng["max"] = n
                elif name == "Min" and n is not None:
                    rng["min"] = n
                elif name == "IsInt":
                    rng["integer"] = True
                elif name == "Matches":
                    rx = _regex(args.split(",")[0])
                    if rx:
                        out.append(_rule(field, "pattern", {"value": rx}, rel, ln, "class-validator"))
                elif name == "IsIn" and args.strip():
                    out.append(_rule(field, "options", {"values": _values(args)}, rel, ln, "class-validator"))
                elif name == "IsEmail":
                    out.append(_rule(field, "pattern", {"value": "email"}, rel, ln, "class-validator"))
            line_no = pending[0][2]
            if length:
                out.append(_rule(field, "length", length, rel, line_no, "class-validator"))
            if {k for k in rng if k != "integer"}:
                out.append(_rule(field, "range", rng, rel, line_no, "class-validator"))
            pending = []
        elif line.strip() and not line.strip().startswith(("//", "*", "/*")):
            pending = [] if not decs else pending
    return out


def extract_file(path: str, source: str, rel: str) -> Dict[str, Any]:
    lines = source.splitlines()
    line_of = lambda pos: source.count("\n", 0, pos) + 1  # noqa: E731
    rules: List[dict] = []
    for lib, rx in (("zod", _ZOD), ("yup", _YUP), ("joi", _JOI)):
        for m in rx.finditer(source):
            groups = m.groups()
            if lib == "zod":
                field, base, base_args, chain = groups
            else:
                field, base, chain = groups
                base_args = ""
            rules += _chain_rules(field, base, base_args, chain, rel, line_of(m.start()), lib)
    if "class-validator" in source:
        rules += _class_validator(lines, rel)
    routes = [{"method": m.group(2).upper(), "path": m.group(3), "path_template": template_path(m.group(3)),
               "handler": None, "citation": f"{rel}:{line_of(m.start())}",
               "params": {"path": re.findall(r":(\w+)", m.group(3)), "query": [], "form": [], "file": [],
                          "json_body": m.group(2) in ("post", "put", "patch")},
               "auth": None, "roles": [], "access_checks": [], "validators": [], "statuses": [], "error_status": None,
               "response_keys": []} for m in _ROUTE.finditer(source)]
    return {"routes": routes, "rules": rules, "flags": [], "functions": {}, "calls": {}}

