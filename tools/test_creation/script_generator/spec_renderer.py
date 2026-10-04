"""
spec_renderer.py — deterministic (non-LLM) renderer that turns a validated
JSON test plan into a runnable .spec.ts file using the shared ActionEngine
runtime, instead of asking an LLM to write Playwright code directly.

Expected plan shape (already validated against ALLOWED_ACTIONS, the
project's locator_map.json keys, and flows.json names before this is
called — see agents/test_creation/script_generation/agent.py :: _validate_plan):

    {
      "tests": [
        {
          "name": "positive — valid login",
          "type": "positive",
          "steps": [
            {"action": "useFlow", "flow": "login", "args": {"username": "standard_user", "password": "secret_sauce"}},
            {"action": "verifyUrl", "value": "inventory.html", "message": "Should land on inventory page"}
          ]
        }
      ],
      "missing_actions": [],
      "missing_locators": []
    }

Step fields beyond {action, locator_key, value} (target_locator_key for
dragAndDrop, message for assertions, soft for verify* actions, flow/args for
useFlow) are additive/optional — every action only needs the fields relevant
to it.

Flows (application_assets/projects/{project}/test_creation/flows.json) are
reusable, named, parameterized action sequences — the same idea as a Page
Object's business-level methods — rendered once per project into
flows.generated.ts and imported by every spec that uses one, instead of
duplicating the same action calls into every test. A flow step's values
may reference a flow parameter with `"{{paramName}}"`, which renders as the
raw TS identifier instead of a quoted string literal.

Import style: this repo's tsconfig.json uses moduleResolution "node" +
module "commonjs" (not NodeNext/bundler), so imports are plain extensionless
relative paths — verify this resolves under `npx playwright test` before
relying on it; adjust tsconfig only if that real run proves it's necessary.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional


def _ts_str(value) -> str:
    """JSON string-literal syntax is valid TS/JS double-quoted string syntax."""
    return json.dumps(value, ensure_ascii=False)


def _val(value, params: set) -> str:
    """
    Render a step's value/message field. If it's a "{{paramName}}" reference
    to a declared flow parameter, emit the raw TS identifier; otherwise emit
    a quoted TS string literal. `params` is empty for ordinary (non-flow)
    test steps, so this always falls through to a literal there.
    """
    if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
        name = value[2:-2].strip()
        if name in params:
            return name
    return _ts_str(value)


def _relative_import(from_dir: str, target_no_ext: str) -> str:
    """
    Both args are paths relative to `application_assets/`. Returns a plain
    extensionless relative import specifier (POSIX slashes) — see the module
    docstring on why this repo doesn't use the `.js`-suffixed convention.
    """
    rel = os.path.relpath(target_no_ext, start=from_dir or ".")
    rel = rel.replace(os.sep, "/")
    if not rel.startswith("."):
        rel = "./" + rel
    return rel


def _import_path_to_shared_fixture(spec_rel_path: str) -> str:
    """
    spec_rel_path is relative to `application_assets/`, e.g.
    'projects/sauceLabs/test_creation/test_scripts/M01/test_M01_BS_001_login.spec.ts'.
    """
    return _relative_import(
        os.path.dirname(spec_rel_path), "_shared/runtime/fixtures/testFixture"
    )


def _import_path_to_flows_module(spec_rel_path: str, project: str) -> str:
    return _relative_import(
        os.path.dirname(spec_rel_path),
        f"projects/{project}/test_creation/flows.generated",
    )


# ── Step argument builders ─────────────────────────────────────────────────

def _soft_suffix(step: dict) -> List[str]:
    return ["{ soft: true }"] if step.get("soft") else []


def _no_extra_args(step: dict, params: set) -> List[str]:
    return []


def _single_value_args(step: dict, params: set) -> List[str]:
    return [_val(step["value"], params)]


def _optional_message_args(step: dict, params: set) -> List[str]:
    """No required value; optional message; optional soft flag — the shape
    shared by verifyVisible/verifyHidden/verifyEnabled/verifyDisabled/verifyChecked."""
    msg = step.get("message")
    soft_tail = _soft_suffix(step)
    if soft_tail:
        return [_val(msg, params) if msg else "undefined"] + soft_tail
    return [_val(msg, params)] if msg else []


def _value_and_message_args(step: dict, params: set) -> List[str]:
    """Required value; optional message; optional soft flag — the shape
    shared by verifyText/verifyContainsText/verifyValue/verifyUrl/verifyTitle."""
    args = [_val(step["value"], params)]
    msg = step.get("message")
    soft_tail = _soft_suffix(step)
    if soft_tail:
        args.append(_val(msg, params) if msg else "undefined")
        args += soft_tail
    elif msg:
        args.append(_val(msg, params))
    return args


def _wait_for_element_args(step: dict, params: set) -> List[str]:
    state = step.get("value")
    return [_val(state, params)] if state else []


def _wait_for_timeout_args(step: dict, params: set) -> List[str]:
    return [str(int(step["value"]))]


def _verify_count_args(step: dict, params: set) -> List[str]:
    args = [str(int(step["value"]))]
    msg = step.get("message")
    soft_tail = _soft_suffix(step)
    if soft_tail:
        args.append(_val(msg, params) if msg else "undefined")
        args += soft_tail
    elif msg:
        args.append(_val(msg, params))
    return args


def _navigate_args(step: dict, params: set) -> List[str]:
    url = step.get("value")
    return [_val(url, params)] if url else []


def _no_page_errors_args(step: dict, params: set) -> List[str]:
    msg = step.get("message")
    return [_val(msg, params)] if msg else []


# action -> function(step, params) -> list[str] of TS argument expressions,
# NOT including the leading locator_key (added by _render_step below).
ARG_BUILDERS = {
    "navigate": _navigate_args,
    "click": _no_extra_args,
    "doubleClick": _no_extra_args,
    "hover": _no_extra_args,
    "enterText": _single_value_args,
    "clearAndEnterText": _single_value_args,
    "pressKey": _single_value_args,
    "checkCheckbox": _no_extra_args,
    "uncheckCheckbox": _no_extra_args,
    "selectDropdownByText": _single_value_args,
    "selectDropdownByValue": _single_value_args,
    "scrollIntoView": _no_extra_args,
    "waitForElement": _wait_for_element_args,
    "waitForTimeout": _wait_for_timeout_args,
    "uploadFile": _single_value_args,
    "verifyVisible": _optional_message_args,
    "verifyHidden": _optional_message_args,
    "verifyText": _value_and_message_args,
    "verifyContainsText": _value_and_message_args,
    "verifyValue": _value_and_message_args,
    "verifyEnabled": _optional_message_args,
    "verifyDisabled": _optional_message_args,
    "verifyChecked": _optional_message_args,
    "verifyCount": _verify_count_args,
    "verifyUrl": _value_and_message_args,
    "verifyUrlContains": _value_and_message_args,
    "verifyTitle": _value_and_message_args,
    "verifyTitleContains": _value_and_message_args,
    "verifyNoPageErrors": _no_page_errors_args,
    "takeScreenshot": _single_value_args,
    "goBack": _no_extra_args,
    "reload": _no_extra_args,
}

# Actions whose first constructor argument is a locator_key.
LOCATOR_FIRST_ACTIONS = {
    "click", "doubleClick", "hover", "enterText", "clearAndEnterText",
    "checkCheckbox", "uncheckCheckbox", "selectDropdownByText",
    "selectDropdownByValue", "scrollIntoView", "waitForElement",
    "uploadFile", "verifyVisible", "verifyHidden", "verifyText",
    "verifyContainsText", "verifyValue", "verifyEnabled", "verifyDisabled",
    "verifyChecked", "verifyCount",
}

# pressKey takes a locator_key OR null (page-level key press) as first arg.
LOCATOR_OR_NULL_ACTIONS = {"pressKey"}

# Page-level actions with no locator argument at all.
NO_LOCATOR_ACTIONS = {
    "navigate", "waitForTimeout", "verifyUrl", "verifyUrlContains", "verifyTitle",
    "verifyTitleContains", "takeScreenshot", "goBack", "reload", "verifyNoPageErrors",
}

# Actions whose ARG_BUILDERS entry does `step["value"]` (hard KeyError if
# absent) rather than `step.get("value")` — mirrors _single_value_args /
# _value_and_message_args / _verify_count_args / _wait_for_timeout_args above.
# _validate_plan in agents/test_creation/script_generation/agent.py checks a
# plan against this set before it ever reaches render_spec_from_plan, since a
# plan that passes action/locator_key validation but omits "value" here would
# otherwise crash the renderer instead of routing back through the normal
# retry/fallback path.
VALUE_REQUIRED_ACTIONS = {
    "enterText", "clearAndEnterText", "pressKey", "selectDropdownByText",
    "selectDropdownByValue", "uploadFile", "verifyText", "verifyContainsText",
    "verifyValue", "verifyUrl", "verifyUrlContains", "verifyTitle",
    "verifyTitleContains", "verifyCount", "waitForTimeout",
}

# Deterministic tag appended by the renderer (never LLM-authored, so tagging
# can't be hallucinated) — @smoke for the one required positive/happy-path
# test, @regression for negative/boundary variants.
_TAG_BY_TYPE = {"positive": "@smoke", "negative": "@regression", "boundary": "@regression"}


def _render_use_flow_step(step: dict, flows_meta: Dict[str, List[str]], indent: str) -> str:
    flow_name = step["flow"]
    if flow_name not in flows_meta:
        raise ValueError(f"render_spec_from_plan: unknown flow '{flow_name}' (not in flows.json)")
    flow_params = flows_meta[flow_name]
    args_dict = step.get("args", {})
    arg_exprs = [_val(args_dict.get(p), set()) for p in flow_params]
    call_args = ["action"] + arg_exprs
    return f"{indent}await flows.{flow_name}({', '.join(call_args)});"


def _render_step(
    step: dict,
    flows_meta: Optional[Dict[str, List[str]]] = None,
    params: Optional[set] = None,
    indent: str = "    ",
) -> str:
    action = step["action"]
    params = params or set()

    if action == "useFlow":
        return _render_use_flow_step(step, flows_meta or {}, indent)

    if action == "dragAndDrop":
        source = _ts_str(step["locator_key"])
        target = _ts_str(step["target_locator_key"])
        return f"{indent}await action.dragAndDrop({source}, {target});"

    builder = ARG_BUILDERS.get(action, _no_extra_args)
    extra_args = builder(step, params)

    if action in LOCATOR_FIRST_ACTIONS:
        args = [_ts_str(step["locator_key"])] + extra_args
    elif action in LOCATOR_OR_NULL_ACTIONS:
        locator_key = step.get("locator_key")
        args = [_ts_str(locator_key) if locator_key else "null"] + extra_args
    else:  # NO_LOCATOR_ACTIONS
        args = extra_args

    return f"{indent}await action.{action}({', '.join(args)});"


def _render_test(test: dict, flows_meta: Optional[Dict[str, List[str]]]) -> str:
    tag = _TAG_BY_TYPE.get(test.get("type", ""), "")
    name = test["name"]
    if tag and tag not in name:
        name = f"{name} {tag}"
    name_ts = _ts_str(name)
    lines = [f"  test({name_ts}, async ({{ action }}) => {{"]
    for step in test["steps"]:
        lines.append(_render_step(step, flows_meta=flows_meta))
    lines.append("  });")
    return "\n".join(lines)


def _uses_flows(plan: dict) -> bool:
    return any(
        step.get("action") == "useFlow"
        for test in plan.get("tests", [])
        for step in test.get("steps", [])
    )


def render_spec_from_plan(
    plan: dict,
    scenario: dict,
    base_url: str,
    spec_rel_path: str,
    project: Optional[str] = None,
    flows_meta: Optional[Dict[str, List[str]]] = None,
) -> str:
    """
    Pure, deterministic renderer — no LLM involved. Turns a validated JSON
    test plan into a runnable .spec.ts file that imports the shared
    ActionEngine fixture (and the project's flows module, if any step uses
    one) and calls only action.<verb>(...) / flows.<name>(...) per step.
    """
    fixture_import = _import_path_to_shared_fixture(spec_rel_path)

    title = scenario.get("title") or scenario.get("scenario_title") or scenario.get("scenario_id", "")
    scenario_id = scenario.get("scenario_id") or scenario.get("id", "")
    describe_title = _ts_str(f"{title} ({scenario_id})" if scenario_id else title)

    lines = [
        f"// Base URL (from project.yaml, resolved via playwright.config.ts): {base_url}",
        f"import {{ test, expect }} from '{fixture_import}';",
    ]

    if _uses_flows(plan):
        if not project:
            raise ValueError("render_spec_from_plan: plan uses a flow but no `project` was given")
        flows_import = _import_path_to_flows_module(spec_rel_path, project)
        lines.append(f"import * as flows from '{flows_import}';")

    lines += [
        "",
        f"test.describe({describe_title}, () => {{",
        "",
    ]

    for test in plan.get("tests", []):
        lines.append(_render_test(test, flows_meta))
        lines.append("")

    lines.append("});")
    lines.append("")

    return "\n".join(lines)


# ── Flows module rendering ──────────────────────────────────────────────────

def render_flows_module(flows: dict, project: str) -> str:
    """
    Pure, deterministic renderer — no LLM involved. Turns flows.json into
    one exported async function per flow:

        export async function login(action: ActionEngine, username: string, password: string): Promise<void> {
            await action.enterText("login", username);
            ...
        }
    """
    from_dir = f"projects/{project}/test_creation"
    action_engine_import = _relative_import(from_dir, "_shared/runtime/ActionEngine")

    lines = [f"import {{ ActionEngine }} from '{action_engine_import}';", ""]

    for flow_name, flow in flows.items():
        params = flow.get("params", [])
        param_list = ", ".join(f"{p}: string" for p in params)
        sig = f"action: ActionEngine{', ' + param_list if param_list else ''}"
        lines.append(f"export async function {flow_name}({sig}): Promise<void> {{")
        for step in flow.get("steps", []):
            lines.append(_render_step(step, params=set(params), indent="    "))
        lines.append("}")
        lines.append("")

    return "\n".join(lines)
