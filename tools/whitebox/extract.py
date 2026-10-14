"""
extract.py — Phase 8.2 / 8.4: white-box rules for a project, written to test_comprehension/code_rules.json.

    project.yaml   white_box: {enabled: true, source_dir: <path to the app's source>, exclude: [glob, ...]}
    CLI            python -m tools.whitebox.extract <project_dir>

code_rules.json
    routes     [{method, path, path_template, handler, citation, params, auth, roles, access_checks, validators,
                 statuses, error_status, response_keys}]
    rules      [{field, kind, value, source: "code", citation, function, guards?, message?, routes: ["POST /x"]}]
    flags      feature flags seen in the code
    contract   frontend vs backend (8.4): a form / call the UI makes with no backend route, a field the backend never
               reads, a required backend field the form does not send, and a client rule the server does not enforce
               ("server accepts what the client rejects")
"""

from __future__ import annotations

import ast
import fnmatch
import re
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from tools.whitebox import js_rules, python_rules

SKIP_DIRS = {"node_modules", ".venv", "venv", ".git", "__pycache__", "dist", "build", ".next", "coverage",
             "tests", "test", "__tests__", "migrations"}
JS_EXT = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")


def _files(root: Path, exclude: List[str]) -> List[Path]:
    out = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for f in files:
            p = Path(dirpath) / f
            rel = p.relative_to(root).as_posix()
            if any(fnmatch.fnmatch(rel, g) for g in exclude) or f.endswith((".spec.ts", ".test.ts", ".test.js")):
                continue
            if f.endswith(".py") or f.endswith(JS_EXT):
                out.append(p)
    return sorted(out)


def extract_source(source_dir: str, exclude: Optional[List[str]] = None, rel_to: Optional[str] = None) -> Dict[str, Any]:
    root = Path(source_dir)
    base = Path(rel_to) if rel_to else root
    files = _files(root, exclude or [])
    shared: Dict[str, Any] = {}
    texts = {}
    for p in files:
        texts[p] = p.read_text(encoding="utf-8", errors="replace")
        if p.suffix == ".py":
            try:
                for k, v in python_rules.module_constants(ast.parse(texts[p])).items():
                    shared.setdefault(k, v)
            except SyntaxError:
                pass
    routes: List[dict] = []
    rules: List[dict] = []
    flags: set = set()
    functions: Dict[str, Dict[str, Any]] = {}
    calls: Dict[str, List[str]] = {}
    for p in files:
        try:
            rel = p.resolve().relative_to(base.resolve()).as_posix()
        except ValueError:
            rel = p.as_posix()
        part = (python_rules.extract_file(str(p), texts[p], rel, shared) if p.suffix == ".py"
                else js_rules.extract_file(str(p), texts[p], rel))
        routes += part["routes"]
        rules += part["rules"]
        flags |= set(part["flags"])
        for name, span in part["functions"].items():
            functions[f"{rel}::{name}"] = {"file": rel, "name": name, "start": span[0], "end": span[1]}
        for name, callees in part["calls"].items():
            calls[f"{rel}::{name}"] = [f"{rel}::{c}" for c in callees]
    _link(routes, rules)
    # a rule of a plain function that no route reaches is not about request input (an env var, a config read);
    # schema classes (pydantic / marshmallow / zod / ...) are kept — they describe input wherever they are used
    rules = [r for r in rules if r["routes"] or r["function"] in _schema_functions(rules, functions)]
    return {"routes": routes, "rules": _dedupe(rules), "flags": sorted(flags), "functions": functions, "calls": calls}


def _schema_functions(rules: List[dict], functions: Dict[str, Any]) -> set:
    plain = {f["name"] for f in functions.values()}
    return {r["function"] for r in rules if r["function"] not in plain}


def _link(routes: List[dict], rules: List[dict]) -> None:
    """A rule applies to every route whose handler is its function or calls it (directly or through a helper)."""
    for r in rules:
        r["routes"] = sorted({f"{rt['method']} {rt['path_template']}" for rt in routes
                              if r["function"] in rt.get("validators", []) or r["function"] == rt.get("handler")
                              or (r["field"] in (rt["params"].get("form") or []) + (rt["params"].get("query") or [])
                                  and r["function"] in _helpers(rt))})


def _helpers(route: dict) -> List[str]:
    return list(route.get("validators") or [])


def _dedupe(rules: List[dict]) -> List[dict]:
    seen, out = set(), []
    for r in rules:
        key = (r["field"], r["kind"], json.dumps(r["value"], sort_keys=True), r["citation"])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


# ── 8.4 contract checks ─────────────────────────────────────────────────────

def _route_fields(route: dict, rules: List[dict]) -> set:
    p = route.get("params") or {}
    fields = set(p.get("form") or []) | set(p.get("query") or []) | set(p.get("file") or [])
    key = f"{route['method']} {route['path_template']}"
    fields |= {r["field"] for r in rules if key in r.get("routes", [])}
    return fields


def contract(code: Dict[str, Any], form_model: Optional[dict], api_inventory: Optional[dict]) -> List[dict]:
    routes = {(r["method"], r["path_template"]): r for r in code["routes"]}
    out: List[dict] = []
    seen = set()
    for f in (form_model or {}).get("forms") or []:
        method = (f.get("method") or "get").upper()
        action = python_rules.template_path(re.sub(r"/\d+(?=/|$)", "/{id}", _path(f.get("action") or f.get("url_template") or "")))
        route = routes.get((method, action))
        where = f"{method} {action} (form {f.get('dom_id') or f.get('form_id')} on {f.get('url_template')})"
        if route is None:
            if (method, action) not in seen:
                out.append({"type": "no_route", "where": where, "detail": "the form submits to a route the code does not define"})
                seen.add((method, action))
            continue
        accepted = _route_fields(route, code["rules"])
        sent = {x.get("name") for x in f.get("fields") or [] if x.get("name")}
        for name in sorted(sent - accepted):
            out.append({"type": "field_ignored", "where": where, "field": name,
                        "detail": "the form sends a field the backend never reads", "citation": route["citation"]})
        server = {(r["field"], r["kind"]) for r in code["rules"] if f"{method} {action}" in r.get("routes", [])}
        # an options / pattern / range rule also rejects the empty value — it enforces "required" too
        server |= {(f_, "required") for f_, k in server if k in ("options", "pattern", "range", "length")}
        for x in f.get("fields") or []:
            c = x.get("constraints") or {}
            client = []
            if c.get("effective_required") or c.get("required"):
                client.append("required")
            if c.get("maxlength") or c.get("minlength"):
                client.append("length")
            if c.get("min") is not None or c.get("max") is not None:
                client.append("range")
            if c.get("pattern"):
                client.append("pattern")
            for kind in client:
                if (x.get("name"), kind) not in server:
                    out.append({"type": "server_weaker", "where": where, "field": x.get("name"), "kind": kind,
                                "detail": f"the browser enforces {kind} on '{x.get('name')}' but the server does not — "
                                          "a request that skips the UI is accepted", "citation": route["citation"]})
    for e in (api_inventory or {}).get("endpoints") or []:
        key = (e.get("method", "GET").upper(), python_rules.template_path(e.get("path_template") or ""))
        if e.get("kind") in ("xhr", "fetch", "form_submit") and key not in routes and key not in seen:
            out.append({"type": "no_route", "where": f"{key[0]} {key[1]}", "detail": "the UI calls an endpoint the code does not define"})
            seen.add(key)
    return out


def _path(url: str) -> str:
    from urllib.parse import urlsplit
    return urlsplit(url).path or url


# ── project driver ──────────────────────────────────────────────────────────

def load_config(project_dir: Path) -> Dict[str, Any]:
    try:
        raw = yaml.safe_load((project_dir / "project.yaml").read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        raw = {}
    wb = raw.get("white_box") if isinstance(raw.get("white_box"), dict) else {}
    return {"enabled": bool(wb.get("enabled")), "source_dir": wb.get("source_dir") or "",
            "exclude": list(wb.get("exclude") or [])}


def run(project_dir: Path, root: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Extract and write code_rules.json when `white_box.enabled`; returns the document (None = off / no source)."""
    project_dir = Path(project_dir)
    cfg = load_config(project_dir)
    if not cfg["enabled"] or not cfg["source_dir"]:
        return None
    root = root or Path(__file__).resolve().parents[2]
    src = Path(cfg["source_dir"])
    src = src if src.is_absolute() else root / src
    if not src.is_dir():
        raise FileNotFoundError(f"white_box.source_dir {src} does not exist")
    code = extract_source(str(src), cfg["exclude"], rel_to=str(root))
    comp = project_dir / "test_comprehension"

    def _load(name):
        p = comp / f"{name}.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    doc = {"schema_version": 1, "artifact": "code_rules", "project": project_dir.name,
           "generated_at": datetime.now(timezone.utc).isoformat(), "source_dir": str(cfg["source_dir"]), **code,
           "contract": contract(code, _load("form_model"), _load("api_inventory"))}
    comp.mkdir(parents=True, exist_ok=True)
    (comp / "code_rules.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return doc


if __name__ == "__main__":
    d = run(Path(sys.argv[1]))
    if d is None:
        print("white_box is not enabled (project.yaml white_box: {enabled: true, source_dir: ...})")
    else:
        print(f"{len(d['routes'])} routes, {len(d['rules'])} rules, {len(d['contract'])} contract findings")
