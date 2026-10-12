"""
suite_grep.py — test_suites/<name>_suite.json -> one Playwright --grep expression (Phase 4.9).

Playwright matches --grep against "<project> <spec file path> <describe titles> <test title> <tags>"
(case-insensitive). Every rendered spec carries its spec id in its file name
(test_M03_BS_003_….spec.ts) and its describe title ("… (M03_BS_003)"), so a suite's spec ids select
the same tests by grep as by file path — including specs generated before Phase 1 tags existed.

Suite JSON (all keys optional, unchanged meaning):
    "scenarios": ["M01_BS_001", "SC-M01-003", {"id": "BS-002", "grep": "login"}]
    "all_modules": true                         -> no grep (everything)
    "tags": ["@smoke", "@P0"]                   -> new: any of these tags (exact tag, not a prefix)
    "grep": "<regex>"                           -> new: ORed in as-is
"""

import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

_JS_SPECIAL = re.compile(r"([\\^$.*+?()\[\]{}|/])")
_ORDINAL = re.compile(r"^SC-([A-Z]\d+)-(\d+)$")


@dataclass
class SuiteGrep:
    suite: str
    grep: Optional[str] = None          # None -> run everything in scope
    spec_ids: List[str] = field(default_factory=list)
    modules: List[str] = field(default_factory=list)   # modules of the resolved spec ids ([] = unknown / all)
    unresolved: List[str] = field(default_factory=list)
    all_modules: bool = False
    empty: bool = False                 # the suite selects nothing (every id unresolved, no tags/grep)


def js_escape(text: str) -> str:
    """Escape a literal for a JavaScript RegExp source."""
    return _JS_SPECIAL.sub(r"\\\1", text)


def id_pattern(spec_ids: List[str]) -> str:
    """Spec ids as a bounded alternation: M01_BS_001 must not match M01_BS_0010 or XM01_BS_001."""
    alts = "|".join(js_escape(s) for s in spec_ids)
    return f"(?<![A-Za-z0-9])(?:{alts})(?![0-9])"


def tag_pattern(tags: List[str]) -> str:
    """Exact tags: @P1 must not match @P10, @AC-01.2 must not match @AC-01.2.1."""
    norm = [t if t.startswith("@") else f"@{t}" for t in tags]
    return f"(?:{'|'.join(js_escape(t) for t in norm)})(?![\\w.-])"


def _load_specs(manifest_file: Path) -> List[Dict[str, Any]]:
    with open(manifest_file, encoding="utf-8") as f:
        data = json.load(f)
    specs = data.get("specs", []) if isinstance(data, dict) else []
    return [s for s in specs if isinstance(s, dict) and s.get("spec_id")]


def _module_of(spec: Dict[str, Any]) -> str:
    return str(spec.get("module_id") or spec.get("module") or "")


def resolve_spec_id(entry_id: str, specs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """A suite entry id -> its test_suite.json spec. SC-M01-003 = 3rd spec of M01 by spec_id
    (the same rule as suite_orchestrator._resolve_scenario_id); anything else is a spec_id."""
    m = _ORDINAL.match(entry_id)
    if m:
        in_module = sorted((s for s in specs if _module_of(s) == m.group(1)), key=lambda s: s["spec_id"])
        seq = int(m.group(2))
        return in_module[seq - 1] if 1 <= seq <= len(in_module) else None
    return next((s for s in specs if s["spec_id"] == entry_id), None)


def build_suite_grep(project_dir: str, suite_name: str) -> SuiteGrep:
    """Translate a suite file into a grep. Raises FileNotFoundError like resolve_suite_spec_files."""
    project_path = Path(project_dir)
    suite_file = project_path / "test_suites" / f"{suite_name}_suite.json"
    manifest_file = project_path / "test_creation" / "test_suite.json"
    if not suite_file.exists():
        raise FileNotFoundError(f"Suite file not found: {suite_file}")
    with open(suite_file, encoding="utf-8") as f:
        suite = json.load(f)
    return suite_config_to_grep(suite, _load_specs(manifest_file) if manifest_file.exists() else [], suite_name)


def suite_config_to_grep(suite: Dict[str, Any], specs: List[Dict[str, Any]], suite_name: str = "") -> SuiteGrep:
    out = SuiteGrep(suite=suite_name or str(suite.get("suite_id", "")))
    if suite.get("all_modules"):
        out.all_modules = True
        return out

    plain: List[str] = []
    filtered: List[str] = []          # "^(?=.*ID)(?=.*GREP)" alternatives
    modules = set()
    for entry in suite.get("scenarios", []) or []:
        if isinstance(entry, dict):
            entry_id, entry_grep = str(entry.get("id", "")), entry.get("grep") or None
        else:
            entry_id, entry_grep = str(entry), None
        if not entry_id:
            continue
        spec = resolve_spec_id(entry_id, specs)
        if spec is None:
            out.unresolved.append(entry_id)
            print(f"[suite_grep] WARNING: '{entry_id}' not found in test_suite.json", file=sys.stderr)
            continue
        sid = spec["spec_id"]
        if _module_of(spec):
            modules.add(_module_of(spec))
        if sid not in out.spec_ids:
            out.spec_ids.append(sid)
        if entry_grep:
            filtered.append(f"^(?=.*{id_pattern([sid])})(?=.*(?:{entry_grep}))")
        elif sid not in plain:
            plain.append(sid)

    alts: List[str] = []
    if plain:
        alts.append(id_pattern(plain))
    alts.extend(filtered)
    tags = [str(t) for t in (suite.get("tags") or []) if str(t).strip()]
    if tags:
        alts.append(tag_pattern(tags))
    if suite.get("grep"):
        alts.append(f"(?:{suite['grep']})")

    if not alts:
        out.empty = True
        return out
    out.grep = alts[0] if len(alts) == 1 else "|".join(alts)
    # Tag/grep selections can reach any module; only a pure id list narrows the modules.
    out.modules = sorted(modules) if not (tags or suite.get("grep")) else []
    return out
