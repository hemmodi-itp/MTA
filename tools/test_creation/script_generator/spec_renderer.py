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
import re
from typing import Dict, List, Optional

from tools.safety.hosts import is_absolute_web_url as _is_absolute_web_url


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


def _msg_tail(step: dict, params: set) -> List[str]:
    msg = step.get("message")
    return [_val(msg, params)] if msg else []


def _trim_undefined(args: List[str]) -> List[str]:
    """Drop trailing `undefined` placeholders, so optional positional arguments only appear when used."""
    while args and args[-1] == "undefined":
        args.pop()
    return args


def _status_expr(status) -> str:
    """200 -> 200; "2xx" -> "2xx" (ActionEngine.statusMatches); None -> undefined."""
    if status is None:
        return "undefined"
    if isinstance(status, int) or (isinstance(status, str) and status.isdigit()):
        return str(int(status))
    return _ts_str(str(status))


def _verify_request_args(step: dict, params: set) -> List[str]:
    args = [_val(str(step["method"]).upper(), params), _val(step["urlPattern"], params),
            _status_expr(step.get("status")),
            _val(step["message"], params) if step.get("message") else "undefined",
            _val(step["bodyContains"], params) if step.get("bodyContains") is not None else "undefined"]
    return _trim_undefined(args)


def _verify_no_request_args(step: dict, params: set) -> List[str]:
    return [_val(str(step["method"]).upper(), params), _val(step["urlPattern"], params)] + _msg_tail(step, params)


def _verify_not_injected_args(step: dict, params: set) -> List[str]:
    return [_val(step["payloadMarker"], params)] + _msg_tail(step, params)


def _ts_obj(value) -> str:
    """A JSON object/array/scalar as a TS expression (JSON is valid TS)."""
    return json.dumps(value, ensure_ascii=False)


def _verify_count_changed_args(step: dict, params: set) -> List[str]:
    return [str(int(step["delta"]))] + _msg_tail(step, params)


def _verify_download_args(step: dict, params: set) -> List[str]:
    args = [_val(step["nameRegex"], params) if step.get("nameRegex") else "undefined",
            str(int(step["minBytes"])) if step.get("minBytes") is not None else "undefined",
            _val(step["message"], params) if step.get("message") else "undefined"]
    return _trim_undefined(args)


def _verify_new_tab_args(step: dict, params: set) -> List[str]:
    return [_val(step["urlContains"], params)] + _msg_tail(step, params)


def _verify_storage_args(step: dict, params: set) -> List[str]:
    args = [_ts_str(step["store"]), _val(step["key"], params), _ts_str(step["rule"]),
            _val(step["value"], params) if step.get("value") is not None else "undefined",
            _val(step["message"], params) if step.get("message") else "undefined"]
    return _trim_undefined(args)


def _verify_response_schema_args(step: dict, params: set) -> List[str]:
    schema = step.get("schema")
    ref = _ts_obj(schema) if isinstance(schema, dict) else _val(step["schemaRef"], params)
    return [_val(step["urlPattern"], params), ref] + _msg_tail(step, params)


_API_EXPECT_FIELDS = ("status", "bodyContains", "bodyNotContains", "path", "equals", "length")


def _verify_api_state_args(step: dict, params: set) -> List[str]:
    expect = {k: v for k, v in (step.get("expect") or {}).items() if k in _API_EXPECT_FIELDS}
    return [_ts_str(str(step.get("method") or "GET").upper()), _val(step["url"], params), _ts_obj(expect)] \
        + _msg_tail(step, params)


_MOCK_FIELDS = ("status", "body", "contentType", "delayMs")


def _mock_route_args(step: dict, params: set) -> List[str]:
    opts = {k: step[k] for k in _MOCK_FIELDS if step.get(k) is not None}
    return [_val(step["urlPattern"], params)] + ([_ts_obj(opts)] if opts else [])


def _set_offline_args(step: dict, params: set) -> List[str]:
    value = step.get("value")
    return ["true" if value in (True, "true", "True", 1, "1") else "false"]


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
    "verifyBusyWhileSubmitting": _optional_message_args,
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
    # Phase 5 oracles
    "verifyRequest": _verify_request_args,
    "verifyNoRequest": _verify_no_request_args,
    "verifyFieldInvalid": _msg_tail,
    "verifyNoDialog": _msg_tail,
    "verifyNotInjected": _verify_not_injected_args,
    "verifyNoNewConsoleErrors": _msg_tail,
    "verifyValidationMessage": _value_and_message_args,
    "verifyAriaSnapshot": _value_and_message_args,
    "rememberCount": _no_extra_args,
    "verifyCountChangedBy": _verify_count_changed_args,
    "verifyDownload": _verify_download_args,
    "verifyNewTab": _verify_new_tab_args,
    "verifyStorage": _verify_storage_args,
    "verifyResponseSchema": _verify_response_schema_args,
    "verifyApiState": _verify_api_state_args,
    "mockRoute": _mock_route_args,
    "setOffline": _set_offline_args,
    "setClock": _single_value_args,
}

# Actions whose first constructor argument is a locator_key.
LOCATOR_FIRST_ACTIONS = {
    "click", "doubleClick", "hover", "enterText", "clearAndEnterText",
    "checkCheckbox", "uncheckCheckbox", "selectDropdownByText",
    "selectDropdownByValue", "scrollIntoView", "waitForElement",
    "uploadFile", "verifyVisible", "verifyHidden", "verifyText",
    "verifyContainsText", "verifyValue", "verifyEnabled", "verifyDisabled", "verifyBusyWhileSubmitting",
    "verifyChecked", "verifyCount", "verifyFieldInvalid",
    "verifyValidationMessage", "verifyAriaSnapshot", "rememberCount", "verifyCountChangedBy",
    "verifyDownload", "verifyNewTab",
}

# pressKey takes a locator_key OR null (page-level key press) as first arg.
LOCATOR_OR_NULL_ACTIONS = {"pressKey"}

# Page-level actions with no locator argument at all.
NO_LOCATOR_ACTIONS = {
    "navigate", "waitForTimeout", "verifyUrl", "verifyUrlContains", "verifyTitle",
    "verifyTitleContains", "takeScreenshot", "goBack", "reload", "verifyNoPageErrors",
    "verifyRequest", "verifyNoRequest", "verifyNoDialog", "verifyNotInjected", "verifyNoNewConsoleErrors",
    "verifyStorage", "verifyResponseSchema", "verifyApiState", "mockRoute", "setOffline", "setClock",
}

# Renderer macro (Phase 5 persistence check): `{"action": "reloadAndVerify", "steps": [<verify* steps>]}` renders as
# action.reload() followed by the nested verify steps.
RELOAD_AND_VERIFY = "reloadAndVerify"

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
    "verifyValidationMessage", "verifyAriaSnapshot", "setOffline", "setClock",
}

# Phase 5: required step fields (not "value") per oracle action — checked by _validate_plan (0 / false are values).
ORACLE_REQUIRED_FIELDS = {
    "verifyRequest": ("method", "urlPattern"),
    "verifyNoRequest": ("method", "urlPattern"),
    "verifyNotInjected": ("payloadMarker",),
    "verifyCountChangedBy": ("delta",),
    "verifyNewTab": ("urlContains",),
    "verifyStorage": ("store", "key", "rule"),
    "verifyResponseSchema": ("urlPattern",),
    "verifyApiState": ("url", "expect"),
    "mockRoute": ("urlPattern",),
    RELOAD_AND_VERIFY: ("steps",),
}

STORAGE_KINDS = ("cookie", "localStorage", "sessionStorage")
STORAGE_RULES = ("present", "absent", "equals", "contains", "httpOnly", "secure", "sameSite")

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

    if action == RELOAD_AND_VERIFY:
        lines = [f"{indent}await action.reload();"]
        lines += [_render_step(s, flows_meta, params, indent) for s in step.get("steps") or []]
        return "\n".join(lines)

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


def _has_trace(test: dict) -> bool:
    """Phase 1: plan tests carry a tc_id only when project.yaml `requirements.enabled` is on."""
    return bool(test.get("tc_id"))


def render_test_title(test: dict) -> str:
    """The exact title a plan test is rendered with (traceability matches results on it).

    Traced tests (Phase 1): the primary AC id prefixes the title and the @smoke/@regression tag moves into
    the details object. Untraced tests keep the original "<name> @smoke" form, byte for byte.
    """
    name = test["name"]
    if _has_trace(test):
        primary = (test.get("ac_ids") or [None])[0]
        return f"{primary} {name}" if primary and primary not in name else name
    tag = _TAG_BY_TYPE.get(test.get("type", ""), "")
    if tag and tag not in name:
        name = f"{name} {tag}"
    return name


def render_test_details(test: dict, scenario_id: str = "") -> str:
    """Playwright details object for a traced test, as ONE line: healing's block regex
    (agents/test_execution/healing/tools.py::_extract_test_block) needs the whole test( header on one line."""
    tags: List[str] = []
    if test.get("priority"):
        tags.append(f"@{test['priority']}")
    if test.get("type") in _TAG_BY_TYPE:
        tags.append(f"@{test['type']}")
        tags.append(_TAG_BY_TYPE[test["type"]])
    tags += [f"@{r}" for r in test.get("req_ids") or []]
    tags += [f"@{a}" for a in test.get("ac_ids") or []]
    if test.get("technique"):                       # Phase 3 design cases: --grep @bva / @role_matrix …
        tags.append(f"@{test['technique']}")
    tags = list(dict.fromkeys(tags))
    annotations = [{"type": "ac", "description": a} for a in test.get("ac_ids") or []]
    annotations.append({"type": "tc", "description": test["tc_id"]})
    if test.get("case_id"):
        annotations.append({"type": "case", "description": test["case_id"]})
    if scenario_id:
        annotations.append({"type": "scenario", "description": scenario_id})
    if test.get("ac_link") in ("inherited", "similarity"):
        annotations.append({"type": "ac_link", "description": test["ac_link"]})
    tag_ts = ", ".join(_ts_str(t) for t in tags)
    ann_ts = ", ".join(
        f"{{ type: {_ts_str(a['type'])}, description: {_ts_str(a['description'])} }}" for a in annotations)
    return f"{{ tag: [{tag_ts}], annotation: [{ann_ts}] }}"


# ── Phase 4.5: one test.step per plan step ─────────────────────────────────
#
# The step title is the plan step in words ("3. Click \"save_button\" — <message>"), so the HTML report, the
# trace and the MTA reporter's attempts[].failed_step name the plan step that failed. Deterministic: built from
# the step only. Values that look secret (password/token/... by locator key, flow parameter or locator entry)
# are shown as ••• — step titles land in reports and traces.

_SECRET_RE = re.compile(r"pass(word|wd|code)?|secret|token|otp|\bpin\b|pin_?code|cvv|credential", re.I)
_MASK = "•••"
_MAX_TITLE = 160
_MAX_VALUE = 60

_VERB = {
    "click": "Click {k}", "doubleClick": "Double-click {k}", "hover": "Hover {k}",
    "enterText": "Enter {v} into {k}", "clearAndEnterText": "Clear and enter {v} into {k}",
    "checkCheckbox": "Check {k}", "uncheckCheckbox": "Uncheck {k}",
    "selectDropdownByText": "Select {v} in {k}", "selectDropdownByValue": "Select value {v} in {k}",
    "scrollIntoView": "Scroll {k} into view", "uploadFile": "Upload {v} to {k}",
    "verifyVisible": "Verify {k} is visible", "verifyHidden": "Verify {k} is hidden",
    "verifyEnabled": "Verify {k} is enabled", "verifyDisabled": "Verify {k} is disabled",
    "verifyBusyWhileSubmitting": "Click {k} and verify it is disabled while the submit is in flight",
    "verifyChecked": "Verify {k} is checked", "verifyText": "Verify {k} has text {v}",
    "verifyContainsText": "Verify {k} contains {v}", "verifyValue": "Verify {k} has value {v}",
    "verifyCount": "Verify {k} count is {n}", "verifyUrl": "Verify URL is {v}",
    "verifyUrlContains": "Verify URL contains {v}", "verifyTitle": "Verify title is {v}",
    "verifyTitleContains": "Verify title contains {v}", "verifyNoPageErrors": "Verify no page errors",
    "takeScreenshot": "Take screenshot {v}", "goBack": "Go back", "reload": "Reload the page",
    "waitForTimeout": "Wait {n} ms (fixed sleep)",
    "verifyFieldInvalid": "Verify {k} is invalid", "verifyNoDialog": "Verify no JS dialog fired",
    "verifyNoNewConsoleErrors": "Verify no new console errors",
    "verifyValidationMessage": "Verify {k} validation message contains {v}",
    "verifyAriaSnapshot": "Verify {k} matches its aria snapshot", "rememberCount": "Remember the count of {k}",
    "setClock": "Set the clock to {v}",
}


def _is_secret(key: Optional[str], locator_map: Optional[dict]) -> bool:
    if key and _SECRET_RE.search(str(key)):
        return True
    entry = (locator_map or {}).get(key) if key else None
    if isinstance(entry, dict):
        text = " ".join(str(entry.get(f) or "") for f in ("locator", "name", "description"))
        return bool(_SECRET_RE.search(text))
    return False


def _preview(value, secret: bool) -> str:
    if secret:
        return _MASK
    text = "" if value is None else str(value)
    if len(text) > _MAX_VALUE:
        text = text[:_MAX_VALUE - 1].rstrip() + "…"
    return _ts_str(text)


def _balanced(text: str) -> bool:
    return text.count("(") == text.count(")") and text.count("{") == text.count("}")


def _cut(text: str, limit: int = _MAX_TITLE) -> str:
    if len(text) <= limit:
        return text
    head = text[:limit - 1]
    if " " in head[limit // 2:]:
        head = head[:head.rfind(" ")]
    return head.rstrip() + "…"


def _step_phrase(step: dict, locator_map: Optional[dict], show_value: bool = True) -> str:
    action = step.get("action", "")
    key = step.get("locator_key")
    k = _ts_str(key) if key else ""
    value = step.get("value")
    v = _preview(value, _is_secret(key, locator_map)) if show_value else "<value>"
    if action == "useFlow":
        args = step.get("args") or {}
        parts = [f"{p}={_preview(a, bool(_SECRET_RE.search(p))) if show_value else '<value>'}"
                 for p, a in args.items()]
        return f"Flow {step.get('flow')}({', '.join(parts)})"
    if action == "navigate":
        return f"Navigate to {v}" if value else "Open the module page"
    if action == "pressKey":
        return f"Press {v}" + (f" in {k}" if key else "")
    if action == "waitForElement":
        return f"Wait for {k} to be {value or 'visible'}"
    if action in ("verifyRequest", "verifyNoRequest"):
        status = f" -> {step['status']}" if step.get("status") is not None else ""
        neg = " no" if action == "verifyNoRequest" else ""
        return f"Verify{neg} {step.get('method')} request {_ts_str(step.get('urlPattern'))}{status}"
    if action == "verifyNotInjected":
        return f"Verify payload {_ts_str(step.get('payloadMarker'))} is not injected"
    if action == "verifyCountChangedBy":
        return f"Verify the count of {k} changed by {step.get('delta')}"
    if action == "verifyDownload":
        return f"Click {k} and verify a download" + (f" matching {_ts_str(step['nameRegex'])}" if step.get("nameRegex") else "")
    if action == "verifyNewTab":
        return f"Click {k} and verify a new tab at {_ts_str(step.get('urlContains'))}"
    if action == "verifyStorage":
        tail = f" {_preview(value, _is_secret(step.get('key'), None))}" if value is not None else ""
        return f"Verify {step.get('store')} {_ts_str(step.get('key'))} is {step.get('rule')}{tail}"
    if action == "verifyResponseSchema":
        return f"Verify responses {_ts_str(step.get('urlPattern'))} match the schema"
    if action == "verifyApiState":
        return f"Verify API {str(step.get('method') or 'GET').upper()} {_ts_str(step.get('url'))} state"
    if action == "mockRoute":
        return f"Mock route {_ts_str(step.get('urlPattern'))}"
    if action == "setOffline":
        return "Go offline" if step.get("value") in (True, "true", 1, "1") else "Go back online"
    if action == RELOAD_AND_VERIFY:
        inner = "; ".join(_step_phrase(s, locator_map, show_value) for s in step.get("steps") or [])
        return f"Reload and verify: {inner}"
    if action == "dragAndDrop":
        return f"Drag {k} onto {_ts_str(step.get('target_locator_key'))}"
    template = _VERB.get(action)
    if template is None:
        return action
    n = value if isinstance(value, (int, float)) else (str(value) if value is not None else "")
    return template.format(k=k, v=v, n=n)


def step_title(index: int, step: dict, locator_map: Optional[dict] = None) -> str:
    """Deterministic, human-readable test.step title for plan step *index* (1-based). Never leaves unbalanced
    () / {} — healing's _structurally_valid_block counts brackets inside strings too."""
    message = step.get("message")
    candidates = []
    for show_value, with_message in ((True, True), (True, False), (False, False)):
        phrase = _step_phrase(step, locator_map, show_value)
        if with_message and message:
            phrase = f"{phrase} — {message}"
        candidates.append(_cut(f"{index}. {phrase}"))
    for title in candidates:
        if _balanced(title):
            return title
    return re.sub(r"[(){}]", "", candidates[-1])


def _render_stepped(step: dict, index: int, flows_meta, locator_map) -> List[str]:
    return [
        f"    await test.step({_ts_str(step_title(index, step, locator_map))}, async () => {{",
        _render_step(step, flows_meta=flows_meta, indent="      "),
        "    });",
    ]


def _render_test(test: dict, flows_meta: Optional[Dict[str, List[str]]], scenario_id: str = "",
                 test_steps: bool = False, locator_map: Optional[dict] = None, oracles: bool = False) -> str:
    name_ts = _ts_str(render_test_title(test))
    if _has_trace(test):
        lines = [f"  test({name_ts}, {render_test_details(test, scenario_id)}, async ({{ action }}) => {{"]
    else:
        lines = [f"  test({name_ts}, async ({{ action }}) => {{"]
    steps = list(test["steps"])
    # Phase 5.2: every test ends with a "no new console errors" check (never LLM-authored) unless the plan has one.
    if oracles and not any(st.get("action") == "verifyNoNewConsoleErrors" for st in steps):
        steps.append({"action": "verifyNoNewConsoleErrors"})
    for i, step in enumerate(steps, start=1):
        if test_steps:
            lines += _render_stepped(step, i, flows_meta, locator_map)
        else:
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
    test_steps: bool = False,
    locator_map: Optional[dict] = None,
    oracles: bool = False,
) -> str:
    """
    Pure, deterministic renderer — no LLM involved. Turns a validated JSON
    test plan into a runnable .spec.ts file that imports the shared
    ActionEngine fixture (and the project's flows module, if any step uses
    one) and calls only action.<verb>(...) / flows.<name>(...) per step.

    test_steps (Phase 4.5): wrap each plan step in `await test.step("<n>. <step in words>", ...)`
    (execution.test_steps). Off by default here, so legacy callers render byte-identical specs.
    locator_map: only used to mask secret-looking values in step titles.
    oracles (Phase 5, project.yaml `oracles.enabled`): append verifyNoNewConsoleErrors to every test.
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

    # Phase 0.6: pin the spec to its own module's URL, so a run spanning several
    # modules can never send this spec to another module's (or a default) URL.
    if _is_absolute_web_url(base_url):
        lines += ["", f"test.use({{ baseURL: {_ts_str(base_url)} }});"]

    lines += [
        "",
        f"test.describe({describe_title}, () => {{",
        "",
    ]

    for test in plan.get("tests", []):
        lines.append(_render_test(test, flows_meta, scenario_id, test_steps=test_steps, locator_map=locator_map,
                                 oracles=oracles))
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
