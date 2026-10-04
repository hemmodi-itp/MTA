"""
synthesize_scenarios.py — pure-Python fallback for business scenario generation.

Converts DOM intents (from dom_intents.json) into BusinessScenario objects
WITHOUT calling any LLM. Used when ComprehensionAgent fails (expired AWS token,
missing credentials, network error).

If the LLM is available and ComprehensionAgent succeeds, this module is never called.
It is strictly a fallback so discovery does not block the entire workflow.

Synthetic scenarios are marked with confidence_score=0.75 to distinguish them
from LLM-generated ones (which have model-assigned scores).
"""

import os
from typing import Any, Dict, List, Tuple

from tools.comprehension.export_scenarios import export_scenarios
from tools.comprehension.models import BusinessScenario

_SYNTHETIC_CONFIDENCE = 0.75

# Click names that signal the end of a form-submission scenario
_SUBMIT_KW = {
    "submit", "login", "sign", "register", "search", "proceed",
    "continue", "add", "buy", "checkout", "confirm", "apply",
    "send", "save", "create", "update", "delete",
}

# Click names that belong in a browsing/navigation scenario
_NAV_KW = {
    "menu", "nav", "link", "home", "about", "contact", "category",
    "shop", "collection", "page", "next", "previous", "back",
    "filter", "sort", "browse", "view", "open",
}

# Keyword → human-readable scenario title
_TITLE_MAP: List[Tuple[str, str]] = [
    ("login",       "User Login"),
    ("sign_in",     "User Login"),
    ("sign",        "User Sign In"),
    ("register",    "User Registration"),
    ("sign_up",     "User Registration"),
    ("search",      "Search Products"),
    ("add_to_cart", "Add to Cart"),
    ("add",         "Add Item"),
    ("checkout",    "Complete Checkout"),
    ("buy",         "Complete Purchase"),
    ("purchase",    "Complete Purchase"),
    ("submit",      "Submit Form"),
    ("confirm",     "Confirm Action"),
    ("save",        "Save Changes"),
    ("send",        "Send Message"),
    ("create",      "Create Account"),
    ("update",      "Update Information"),
    ("delete",      "Delete Item"),
    ("apply",       "Apply Filter"),
]


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def synthesize_scenarios_from_flows(
    user_flows: List[Dict[str, Any]],
    project_name: str,
    application_name: str,
    output_dir: str,
) -> Dict[str, str]:
    """
    Convert user_flows.json flows into BusinessScenario objects (confidence=0.95).

    Each flow becomes one scenario; steps are human-readable action descriptions.
    Returns {"json": path, "markdown": path} — same shape as export_scenarios().

    Called by DiscoveryAgent after interactive scan when user_flows.json exists.
    Does NOT overwrite existing scenarios — merges by appending.
    """
    if not user_flows:
        raise ValueError("synthesize_scenarios_from_flows: user_flows is empty")

    scenarios: List[BusinessScenario] = []
    counter = 1

    for flow in user_flows:
        flow_id = flow.get("flow_id", f"FLOW-{counter:03d}")
        name = flow.get("inferred_name", f"User Flow {counter}")
        stype = flow.get("inferred_scenario_type", "general")
        steps_raw = flow.get("steps", [])
        api_calls = flow.get("api_calls_observed", [])
        pages_involved = flow.get("pages_involved", [])

        steps_text = [_flow_step_to_text(s) for s in steps_raw]

        # Preconditions: first page involved, or generic
        precond = f"Application page '{pages_involved[0]}' is loaded" if pages_involved else f"{application_name} is loaded"

        # Expected result: last action or last page
        last_step = steps_raw[-1] if steps_raw else {}
        if last_step.get("page_path"):
            expected = f"User arrives at {last_step['page_path']}"
        else:
            last_text = last_step.get("display_text") or "the action"
            expected = f"{last_text} completes successfully"

        # API calls as business rules
        rules = [f"API: {c.get('method', 'GET')} {c.get('url', '')}" for c in api_calls if c.get("url")]

        scenarios.append(BusinessScenario(
            scenario_id=f"SC-FLOW-{counter:03d}",
            title=name,
            business_objective=f"Allow user to {name.lower()} on {application_name}",
            actor="User",
            preconditions=[precond],
            steps=steps_text if steps_text else ["Interact with the application"],
            expected_result=expected,
            business_rules=rules,
            traceability=[{"source": "user_flow", "flow_id": flow_id}],
            confidence_score=0.95,
        ))
        counter += 1

    os.makedirs(output_dir, exist_ok=True)
    return export_scenarios(scenarios, output_dir, project_name)


def _flow_step_to_text(step: Dict[str, Any]) -> str:
    """Convert a user flow step dict to a human-readable scenario step string."""
    # Page transition step
    if "page_transition" in step:
        pt = step["page_transition"]
        return f"Navigate from {pt.get('from', '?')} to {pt.get('to', '?')}"

    action = step.get("action", "click")
    text = step.get("display_text", "") or step.get("locator_id", "element")
    path = step.get("page_path", "")
    label = f"'{text}'" if text else "the element"
    suffix = f" on {path}" if path else ""

    if action == "fill":
        return f"Enter value in {label}{suffix}"
    if action == "select":
        return f"Select option from {label}{suffix}"
    if action == "click":
        return f"Click {label}{suffix}"
    return f"{action.capitalize()} {label}{suffix}"


def synthesize_scenarios_from_dom(
    dom_intents: List[Dict[str, Any]],
    url: str,
    application_name: str,
    output_dir: str,
    project_name: str,
) -> Dict[str, str]:
    """
    Convert *dom_intents* to BusinessScenario objects and write
    business_scenarios.json + business_scenarios.md to *output_dir*.

    Returns {"json": path, "markdown": path} — same shape as export_scenarios().
    Raises ValueError if dom_intents is empty.
    """
    if not dom_intents:
        raise ValueError(
            "synthesize_scenarios_from_dom: dom_intents is empty — "
            "cannot produce scenarios without DOM data"
        )

    groups = _group_intents(dom_intents, application_name)
    scenarios = _build_scenarios(groups, application_name)

    os.makedirs(output_dir, exist_ok=True)
    return export_scenarios(scenarios, output_dir, project_name)


# ──────────────────────────────────────────────────────────────────────────────
# Grouping
# ──────────────────────────────────────────────────────────────────────────────

def _group_intents(
    intents: List[Dict],
    app_name: str,
) -> List[Tuple[str, List[Dict]]]:
    """
    Partition intents into labelled groups: ("form", [...]), ("nav", [...]), ("misc", [...]).

    Form groups: fill/select intents that end at a submit-like click.
    Nav group:   click intents whose name matches navigation keywords.
    Misc group:  any click intents not matched by the above.
    """
    form_groups: List[List[Dict]] = []
    nav_intents: List[Dict] = []
    misc_intents: List[Dict] = []

    current_form: List[Dict] = []

    for intent in intents:
        action = intent.get("action", "")
        name = intent.get("intent_name", "").lower()

        if action in ("fill", "select"):
            current_form.append(intent)

        elif action == "click":
            if _matches(name, _SUBMIT_KW):
                # Close the current form group with this submit click
                current_form.append(intent)
                form_groups.append(list(current_form))
                current_form = []
            elif _matches(name, _NAV_KW):
                nav_intents.append(intent)
            else:
                misc_intents.append(intent)

        # hover, press, verify, navigate, wait — treat as misc
        else:
            misc_intents.append(intent)

    # Leftover fills (no matching submit click found)
    if current_form:
        form_groups.append(list(current_form))

    groups: List[Tuple[str, List[Dict]]] = []

    for fg in form_groups:
        groups.append(("form", fg))

    if nav_intents:
        groups.append(("nav", nav_intents))

    if misc_intents:
        groups.append(("misc", misc_intents))

    return groups


# ──────────────────────────────────────────────────────────────────────────────
# Scenario building
# ──────────────────────────────────────────────────────────────────────────────

def _build_scenarios(
    groups: List[Tuple[str, List[Dict]]],
    application_name: str,
) -> List[BusinessScenario]:
    scenarios = []
    counter = 1

    for kind, intents in groups:
        if kind == "form":
            scenario = _form_scenario(intents, application_name, counter)
        elif kind == "nav":
            scenario = _nav_scenario(intents, application_name, counter)
        else:
            scenario = _misc_scenario(intents, application_name, counter)

        scenarios.append(scenario)
        counter += 1

    return scenarios


def _form_scenario(
    intents: List[Dict], app_name: str, n: int
) -> BusinessScenario:
    # Find the submit click (last click in the group, if any)
    clicks = [i for i in intents if i.get("action") == "click"]
    last_click = clicks[-1] if clicks else None

    title = _infer_title(last_click["intent_name"] if last_click else "", app_name)
    expected = (last_click or {}).get("expected_result") or "Action completes successfully"

    return BusinessScenario(
        scenario_id=f"SC-{n:03d}",
        title=title,
        business_objective=f"Allow user to {title.lower()} on {app_name}",
        actor="User",
        preconditions=[f"{app_name} page is loaded"],
        steps=[_intent_to_step(i) for i in intents],
        expected_result=expected,
        business_rules=[],
        traceability=[],
        confidence_score=_SYNTHETIC_CONFIDENCE,
    )


def _nav_scenario(
    intents: List[Dict], app_name: str, n: int
) -> BusinessScenario:
    title = f"Browse {app_name}"
    steps = [_intent_to_step(i) for i in intents]
    return BusinessScenario(
        scenario_id=f"SC-{n:03d}",
        title=title,
        business_objective=f"Allow user to navigate the {app_name} interface",
        actor="User",
        preconditions=[f"{app_name} page is loaded"],
        steps=steps,
        expected_result="User reaches the intended section",
        business_rules=[],
        traceability=[],
        confidence_score=_SYNTHETIC_CONFIDENCE,
    )


def _misc_scenario(
    intents: List[Dict], app_name: str, n: int
) -> BusinessScenario:
    title = f"Interact with {app_name}"
    steps = [_intent_to_step(i) for i in intents]
    return BusinessScenario(
        scenario_id=f"SC-{n:03d}",
        title=title,
        business_objective=f"Allow user to interact with elements on {app_name}",
        actor="User",
        preconditions=[f"{app_name} page is loaded"],
        steps=steps,
        expected_result="Interaction completes as expected",
        business_rules=[],
        traceability=[],
        confidence_score=_SYNTHETIC_CONFIDENCE,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _intent_to_step(intent: Dict) -> str:
    """Convert a single DOM intent into a readable test step string."""
    action = intent.get("action", "")
    raw_name = intent.get("intent_name", "")

    # Strip leading action prefix to get the element name
    for prefix in (f"{action}_", "enter_", "click_", "select_", "verify_",
                   "navigate_", "hover_", "press_"):
        if raw_name.startswith(prefix):
            raw_name = raw_name[len(prefix):]
            break

    element = raw_name.replace("_", " ").strip() or "element"

    if action == "fill":
        return f"Enter {element} in the input field"
    elif action == "click":
        return f"Click the {element}"
    elif action == "select":
        return f"Select {element} from the dropdown"
    elif action == "hover":
        return f"Hover over {element}"
    elif action == "verify":
        return f"Verify {element} is visible"
    elif action == "navigate":
        return f"Navigate to {element}"
    else:
        return f"{action.capitalize()} {element}"


def _infer_title(click_name: str, app_name: str) -> str:
    """Derive a human-readable scenario title from the submit click intent name."""
    name_lower = click_name.lower()
    for keyword, title in _TITLE_MAP:
        if keyword in name_lower:
            return title
    # Fallback: prettify the click name itself
    clean = click_name.replace("click_", "").replace("_", " ").strip()
    if clean:
        return clean.title()
    return f"Use {app_name}"


def _matches(name: str, keywords: set) -> bool:
    return any(kw in name for kw in keywords)
