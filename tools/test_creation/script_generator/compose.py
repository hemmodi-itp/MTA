"""
compose.py — a validated plan -> the final .spec.ts text (Phase 4.5).

One function, compose_spec(), used by ScriptGenerationAgent when it writes a spec and by rerender.py when an
existing spec is rebuilt from test_plans.json, so the two can never drift:

    render_spec_from_plan(...)            spec_renderer.py (test bodies; one test.step per plan step if asked)
    + the module's login                  either `test.use({ role })` (execution.module_roles + modules[].role)
                                          or the module's project.yaml `setup:` steps as a test.beforeEach

Module setup injection (e.g. login before inventory/M02+ tests): project.yaml modules[].setup declares a
goto/fill/click/wait sequence that tools/playwright_scanner.py already runs before DOM-scanning a module. That
sequence is the module's real "how do I get to a usable state" — e.g. log in before testing the inventory page.
Reusing it deterministically (not LLM-prompted) applies it no matter which tier (LLM / NS / Python fallback)
produced the test bodies, and regardless of whether the file uses the per-test `{ action }` fixture or a shared
outer `page` (legacy/fallback-tier specs).
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, Iterable, List, Optional

from tools.test_creation.script_generator.spec_renderer import render_spec_from_plan

_DESCRIBE_OPEN_RE = re.compile(r"test\.describe\([^\n]*=>\s*\{\s*\n")
_BEFORE_ALL_NEWPAGE_RE = re.compile(
    r"test\.beforeAll\(async\s*\(\s*\{\s*browser\s*\}\s*\)\s*=>\s*\{\s*\n"
    r"\s*page\s*=\s*await\s*browser\.newPage\(\);\s*\n"
)
_ENV_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_BASE_URL_USE_RE = re.compile(r"^test\.use\(\{ baseURL: [^\n]*\}\);\n", re.M)
_IMPORT_LINE_RE = re.compile(r"^import [^\n]*;\n", re.M)


def translate_setup_step(step: Dict[str, Any]) -> str:
    """Translate one project.yaml setup step into a Playwright TS statement,
    mirroring tools/playwright_scanner.py._execute_setup_steps' action set."""
    if not isinstance(step, dict) or not step:
        return ""
    action = next(iter(step))
    if action == "goto":
        return f"    await page.goto({json.dumps(step['goto'])});"
    if action == "fill":
        spec = step.get("fill") or {}
        if not spec.get("selector"):
            return ""
        value_env = spec.get("value_env")
        if value_env:
            # Never embed the actual secret in generated source — emit a
            # reference resolved at test run time instead. Validate the name
            # is a safe bare identifier before interpolating it as raw TS.
            if not _ENV_VAR_NAME_RE.match(value_env):
                return ""
            return (
                f"    await page.locator({json.dumps(spec['selector'])})"
                f'.fill(process.env.{value_env} ?? "");'
            )
        return (
            f"    await page.locator({json.dumps(spec['selector'])})"
            f".fill({json.dumps(spec.get('value', ''))});"
        )
    if action == "click":
        return f"    await page.locator({json.dumps(step['click'])}).click();"
    if action == "wait":
        try:
            int(step["wait"])
        except (KeyError, TypeError, ValueError):
            return ""
        # Phase 4.6: no fixed sleep. The preceding click already waited for the navigation it started to commit
        # (Playwright's post-action signal barrier), so waiting for that page's load event is enough.
        return "    await page.waitForLoadState('load');"
    return ""  # unknown action — skip rather than emit broken TS


def inject_setup_steps(spec_content: str, setup_steps: Optional[List[Dict[str, Any]]]) -> str:
    """Insert the module's setup sequence (e.g. login) so every test in this
    spec starts from the module's required state.

    Two shapes are supported:
      - Legacy/fallback-tier specs with a shared page (`test.beforeAll(async
        ({ browser }) => { page = await browser.newPage(); })`): setup runs
        ONCE, inserted right after that line.
      - Current action-library specs (per-test `{ action }` fixture, no
        shared page): falls back to inserting a
        `test.beforeEach(async ({ page }) => {...})` right after the
        `test.describe(...)` opening line — action-library specs don't
        destructure `page` themselves, but Playwright's own fixture always
        provides it, so a beforeEach hook can still use it directly.

    Returns spec_content unchanged if there are no usable setup steps, or if
    neither anchor can be found (never corrupt generated output)."""
    if not setup_steps:
        return spec_content

    lines = [line for line in (translate_setup_step(s) for s in setup_steps) if line]
    if not lines:
        return spec_content

    before_all_match = _BEFORE_ALL_NEWPAGE_RE.search(spec_content)
    if before_all_match:
        insertion = "\n".join(lines) + "\n"
        idx = before_all_match.end()
        return spec_content[:idx] + insertion + spec_content[idx:]

    describe_match = _DESCRIBE_OPEN_RE.search(spec_content)
    if not describe_match:
        return spec_content

    hook = "\n  test.beforeEach(async ({ page }) => {\n" + "\n".join(lines) + "\n  });\n"
    idx = describe_match.end()
    return spec_content[:idx] + hook + spec_content[idx:]


def inject_role(spec_content: str, role: str) -> str:
    """`test.use({ role: "<role>" });` after the baseURL pin (or after the imports when there is none)."""
    line = f"test.use({{ role: {json.dumps(role)} }});\n"
    m = _BASE_URL_USE_RE.search(spec_content)
    if m:
        return spec_content[:m.end()] + line + spec_content[m.end():]
    imports = list(_IMPORT_LINE_RE.finditer(spec_content))
    if not imports:
        return spec_content
    idx = imports[-1].end()
    return spec_content[:idx] + "\n" + line + spec_content[idx:]


def module_role_for(module_role: Optional[str], module_roles: bool, declared_roles: Iterable[str],
                    role_auth: bool = True, warn: Optional[Callable[[str], None]] = None) -> Optional[str]:
    """The role a module's specs start as, or None (-> the module's setup steps)."""
    if not module_roles or not module_role:
        return None
    declared = set(declared_roles or ())
    if module_role not in declared:
        if warn:
            warn(f"modules[].role '{module_role}' is not declared in auth.roles "
                 f"({', '.join(sorted(declared)) or 'none declared'}) — using the module's setup steps")
        return None
    if not role_auth and warn:
        warn(f"execution.module_roles renders test.use({{ role: '{module_role}' }}) but execution.role_auth is off — "
             "log the role in first (python -m tools.auth.role_states) or set execution.role_auth: true")
    return module_role


def compose_spec(
    plan: Optional[dict],
    scenario: dict,
    base_url: str,
    spec_rel_path: str,
    *,
    project: Optional[str] = None,
    flows_meta: Optional[Dict[str, List[str]]] = None,
    module_setup: Optional[List[Dict[str, Any]]] = None,
    role: Optional[str] = None,
    test_steps: bool = False,
    locator_map: Optional[Dict[str, Any]] = None,
    raw_content: Optional[str] = None,
) -> str:
    """Final spec text. `raw_content` (legacy tier-2 fallback output) replaces rendering; `role` (already resolved
    by module_role_for) replaces the setup steps."""
    if raw_content is not None:
        content = raw_content
    else:
        content = render_spec_from_plan(plan, scenario, base_url, spec_rel_path, project=project,
                                        flows_meta=flows_meta, test_steps=test_steps, locator_map=locator_map)
    if role and raw_content is None:
        return inject_role(content, role)
    return inject_setup_steps(content, module_setup)
