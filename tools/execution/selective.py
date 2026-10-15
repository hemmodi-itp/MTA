"""
selective.py — Phase 10.5: run only what a change can affect (pull requests); nightly runs everything.

Fingerprint (test_execution/fingerprint.json, written after a full run):
    pages      url_template -> structural hash (app_map.json, Phase 2)
    acs        AC id -> hash of its statement (requirements.json)
    endpoints  "METHOD /template" -> hash of its request shape (api_inventory.json + code_rules.json)
    specs      spec file -> hash of its text
    sources    app source file -> hash (code_rules.json — the white-box source, when there is one)

Impacted tests (the current fingerprint vs the stored one, plus `git diff --name-only <base>` when given):
    every test of a changed / new spec file; plan tests whose AC changed; tests of design cases whose page changed;
    API tests of a changed endpoint, or of a route whose source file changed; and every P0 test, always.
Output: {tests: [titles], grep: "<exact titles>", reasons: {...}} — feed `grep` to UIExecutionAgent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
FILE = "fingerprint.json"


def _h(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def _load(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def fingerprint(project_dir: Path) -> Dict[str, Dict[str, str]]:
    project_dir = Path(project_dir)
    comp = project_dir / "test_comprehension"
    app_map = _load(comp / "app_map.json", {}) or {}
    pages: Dict[str, str] = {}
    for s in app_map.get("states") or []:
        if s.get("url_template") and s.get("structural_hash"):
            pages.setdefault(s["url_template"], s["structural_hash"])
    reqs = _load(comp / "requirements.json", {}) or {}
    reqs = reqs.get("requirements", reqs) if isinstance(reqs, dict) else reqs
    acs = {ac["id"]: _h(ac.get("statement", "")) for r in reqs or [] for ac in r.get("acceptance_criteria", [])
           if isinstance(ac, dict) and ac.get("id")}
    endpoints: Dict[str, str] = {}
    for e in (_load(comp / "api_inventory.json", {}) or {}).get("endpoints") or []:
        endpoints[f"{e.get('method')} {e.get('path_template')}"] = _h(json.dumps(e.get("request"), sort_keys=True))
    code = _load(comp / "code_rules.json", {}) or {}
    for r in code.get("routes") or []:
        endpoints[f"{r['method']} {r['path_template']}"] = _h(json.dumps(
            {k: r.get(k) for k in ("params", "auth", "roles", "error_status")}, sort_keys=True))
    sources: Dict[str, str] = {}
    for fn in (code.get("functions") or {}).values():
        f = ROOT / fn["file"]
        if fn["file"] not in sources and f.is_file():
            sources[fn["file"]] = _h(f.read_text(encoding="utf-8", errors="replace"))
    scripts = project_dir / "test_creation" / "test_scripts"
    specs = {p.relative_to(scripts).as_posix(): _h(p.read_text(encoding="utf-8", errors="replace"))
             for p in scripts.rglob("*.spec.ts")} if scripts.is_dir() else {}
    return {"pages": pages, "acs": acs, "endpoints": endpoints, "specs": specs, "sources": sources}


def save_fingerprint(project_dir: Path) -> Path:
    path = Path(project_dir) / "test_execution" / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fingerprint(project_dir), indent=2), encoding="utf-8")
    return path


def diff(old: Dict[str, Dict[str, str]], new: Dict[str, Dict[str, str]]) -> Dict[str, List[str]]:
    out = {}
    for part in ("pages", "acs", "endpoints", "specs", "sources"):
        a, b = (old or {}).get(part) or {}, new.get(part) or {}
        out[part] = sorted(k for k in b if a.get(k) != b[k])
    return out


def git_changed(base: str, cwd: Path = ROOT) -> List[str]:
    try:
        out = subprocess.run(["git", "diff", "--name-only", base], cwd=cwd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [ln.strip() for ln in out.stdout.splitlines() if ln.strip()] if out.returncode == 0 else []


def _spec_titles(text: str) -> List[str]:
    return [json.loads(t) for t in _TITLE_RE.findall(text)]


# test("<JSON string>", ...) — the title is a full JSON string literal (escaped quotes and commas inside are fine)
_TITLE_RE = re.compile(r'^\s*test(?:\.skip)?\(("(?:[^"\\\n]|\\.)*"),', re.M)


def select(project_dir: Path, previous: Optional[dict] = None, git_files: Optional[List[str]] = None) -> Dict[str, Any]:
    project_dir = Path(project_dir)
    previous = previous if previous is not None else _load(project_dir / "test_execution" / FILE, None)
    current = fingerprint(project_dir)
    changed = diff(previous or {}, current) if previous else {k: sorted(v) for k, v in current.items()}
    full = previous is None
    rel_prefix = (project_dir / "test_creation" / "test_scripts").resolve().relative_to(ROOT.resolve()).as_posix() \
        if str(project_dir.resolve()).startswith(str(ROOT.resolve())) else None
    for f in git_files or []:
        f = f.replace("\\", "/")
        if rel_prefix and f.startswith(rel_prefix + "/"):
            changed["specs"] = sorted(set(changed["specs"]) | {f[len(rel_prefix) + 1:]})
        elif f in current["sources"]:
            changed["sources"] = sorted(set(changed["sources"]) | {f})
    code = _load(project_dir / "test_comprehension" / "code_rules.json", {}) or {}
    for r in code.get("routes") or []:
        if r.get("citation") and r["citation"].rsplit(":", 1)[0] in changed["sources"]:
            changed["endpoints"] = sorted(set(changed["endpoints"]) | {f"{r['method']} {r['path_template']}"})

    plans = _load(project_dir / "test_creation" / "test_plans.json", {}) or {}
    plans = plans.get("plans", plans)
    cases = {c["id"]: c for c in (_load(project_dir / "test_creation" / "test_cases.json", {}) or {}).get("test_cases") or []}
    scripts = project_dir / "test_creation" / "test_scripts"
    reasons: Dict[str, str] = {}

    def pick(title: str, why: str):
        reasons.setdefault(title, why)
    for spec in changed["specs"]:
        p = scripts / spec
        if p.is_file():
            for t in _spec_titles(p.read_text(encoding="utf-8")):
                pick(t, f"spec changed: {spec}")
    for plan in plans.values():
        for t in (plan.get("tests") or []) if isinstance(plan, dict) else []:
            title = t.get("title") or t.get("name")
            if not title:
                continue
            if set(t.get("ac_ids") or []) & set(changed["acs"]):
                pick(title, f"AC changed: {sorted(set(t['ac_ids']) & set(changed['acs']))[0]}")
            case = cases.get(t.get("case_id"))
            tmpl = ((case or {}).get("target") or {}).get("url_template")
            if tmpl and tmpl in changed["pages"]:
                pick(title, f"page changed: {tmpl}")
            if t.get("priority") == "P0":
                pick(title, "P0 — always runs")
    for p in (scripts / "api").glob("*.spec.ts") if (scripts / "api").is_dir() else []:
        for t in _spec_titles(p.read_text(encoding="utf-8")):
            ep = t.split(" — ", 1)[0]
            if ep in changed["endpoints"]:
                pick(t, f"endpoint changed: {ep}")
    tests = sorted(reasons)
    from tools.triage.service import grep_for_titles
    return {"full": full, "changed": changed, "tests": tests, "reasons": reasons,
            "grep": grep_for_titles(tests) if tests and not full else None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Impacted tests for a change (Phase 10.5).")
    ap.add_argument("--project", required=True)
    ap.add_argument("--git-base", default="")
    ap.add_argument("--save", action="store_true", help="store the current fingerprint (after a full run)")
    args = ap.parse_args(argv)
    from tools.constants import PROJECTS_BASE
    pdir = Path(PROJECTS_BASE) / args.project
    if args.save:
        print(save_fingerprint(pdir))
        return 0
    sel = select(pdir, git_files=git_changed(args.git_base) if args.git_base else None)
    print(json.dumps({k: sel[k] for k in ("full", "changed")}, indent=2))
    print(f"{len(sel['tests'])} impacted test(s)" + (" — no stored fingerprint: run everything" if sel["full"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
