import json
import logging
import string
from typing import Dict, List

from tools.shared.llm_response_validator import parse_llm_json
from tools.comprehension.models import BusinessScenario
from tools.artifact_generator.models import IntentDefinition, TestCase

_logger = logging.getLogger("workflow.generate_test_cases")
_VALID_TYPES = frozenset({"positive", "negative", "boundary", "out_of_box"})


# ---------------------------------------------------------------------------
# Priority ordering rules for generated test cases.
#
# To adjust WHAT counts as a "nav bar" test or a "fill" test, update the
# keyword sets below. To change the SCORING WEIGHTS, edit _nav_score /
# _fill_score inside _prioritize_test_cases. To change the ORDER itself,
# edit the ordered-list construction at the bottom of _prioritize_test_cases.
# ---------------------------------------------------------------------------

# Words in an intent_name that indicate it targets nav bar / menu links
_NAV_KEYWORDS = frozenset({
    "nav", "navbar", "navigation", "menu", "header",
    "home", "product", "resource", "about", "contact", "link",
})

# Words in an intent_name that indicate a search/query fill field (higher priority)
_SEARCH_KEYWORDS = frozenset({"search", "query", "find", "lookup"})


def generate_test_cases(
    scenarios: List[BusinessScenario],
    intents: List[IntentDefinition],
    llm_connector,
    prompt_template: string.Template,
    skill_header: str,
    td_ref_map: Dict[str, str],
    extra_subs: dict = None,
) -> List[TestCase]:
    """
    Ask the LLM to map each BusinessScenario to an ordered sequence of intent IDs.

    td_ref_map: BS scenario_id → TD-XXX id (for test_data_ref annotation)
    extra_subs: optional dict of additional template variable substitutions
    """
    scenarios_payload = [
        {
            "scenario_id": s.scenario_id,
            "title": s.title,
            "actor": s.actor,
            "steps": s.steps,
            "expected_result": s.expected_result,
        }
        for s in scenarios
    ]
    intents_payload = [
        {
            "intent_id": i.intent_id,
            "intent_name": i.intent_name,
            "action": i.action,
            "description": i.description,
        }
        for i in intents
    ]
    subs = {
        "skill_header": skill_header,
        "scenarios_json": json.dumps(scenarios_payload, ensure_ascii=False, indent=2),
        "intents_json": json.dumps(intents_payload, ensure_ascii=False, indent=2),
        "md_context": "",
        "existing_tc_summary": "",
    }
    if extra_subs:
        subs.update(extra_subs)
    prompt = prompt_template.safe_substitute(**subs)
    raw = llm_connector.generate(prompt)
    parsed = parse_llm_json(raw)
    test_cases = _build_test_cases(parsed, td_ref_map)
    return _prioritize_test_cases(test_cases, intents)



def _build_test_cases(
    parsed: dict,
    td_ref_map: Dict[str, str],
) -> List[TestCase]:
    raw_cases = parsed.get("test_cases", [])
    test_cases = []
    for i, item in enumerate(raw_cases, start=1):
        bs_id = item.get("business_scenario_id", f"BS-{i:03d}")
        tc_type = item.get("test_case_type", "positive")
        if tc_type not in _VALID_TYPES:
            _logger.warning(f"Unknown test_case_type '{tc_type}' on TC-{i:03d} — defaulting to 'positive'")
            tc_type = "positive"
        test_cases.append(
            TestCase(
                test_case_id=f"TC-{i:03d}",
                test_case_name=item.get("test_case_name", f"Test Case {i}"),
                business_scenario_id=bs_id,
                steps=item.get("steps", []),
                test_data_ref=td_ref_map.get(bs_id),
                expected_result=item.get("expected_result"),
                test_case_type=tc_type,
            )
        )
    return test_cases


def _prioritize_test_cases(
    test_cases: List[TestCase],
    intents: List[IntentDefinition],
) -> List[TestCase]:
    """
    Reorder generated test cases by canonical priority:

      1. Nav bar exploration — the test case whose steps contain the most
         click-actions on nav/menu/link elements (home, products, resources…).
      2. Input fill — the test case with the highest fill score, preferring
         search/query fields over generic fill fields.
      3. All remaining test cases in their original LLM-generated order.

    If no test case qualifies for slot 1 or 2 (score == 0), that slot is
    skipped and the original order is preserved.

    To update priority rules for future use:
      - Add/remove nav keywords  → edit _NAV_KEYWORDS at the top of this file
      - Add/remove search keywords → edit _SEARCH_KEYWORDS
      - Change scoring weights   → edit _nav_score / _fill_score below
      - Change slot order        → edit the `ordered` list construction below
    """
    if not test_cases:
        return test_cases

    intents_by_id = {i.intent_id: i for i in intents}

    def _nav_score(tc: TestCase) -> int:
        score = 0
        for step_id in tc.steps:
            intent = intents_by_id.get(step_id)
            if not intent:
                continue
            name = intent.intent_name.lower()
            if intent.action == "click" and any(kw in name for kw in _NAV_KEYWORDS):
                score += 2  # click on a nav element is a strong signal
            elif any(kw in name for kw in _NAV_KEYWORDS):
                score += 1  # nav keyword without click still counts
        return score

    def _fill_score(tc: TestCase) -> int:
        score = 0
        for step_id in tc.steps:
            intent = intents_by_id.get(step_id)
            if not intent:
                continue
            if intent.action == "fill":
                name = intent.intent_name.lower()
                # Search/query fields are preferred over generic fill fields
                score += 3 if any(kw in name for kw in _SEARCH_KEYWORDS) else 1
        return score

    # Slot 1: best nav bar test case
    nav_tc = max(test_cases, key=_nav_score)
    nav_tc = nav_tc if _nav_score(nav_tc) > 0 else None

    # Slot 2: best fill test case (excluding the nav slot winner)
    fill_candidates = [tc for tc in test_cases if tc is not nav_tc]
    fill_tc = max(fill_candidates, key=_fill_score) if fill_candidates else None
    fill_tc = fill_tc if (fill_tc and _fill_score(fill_tc) > 0) else None

    used = {tc.test_case_id for tc in [nav_tc, fill_tc] if tc}
    ordered = [tc for tc in [nav_tc, fill_tc] if tc]
    ordered += [tc for tc in test_cases if tc.test_case_id not in used]

    # Guard: drop any test case with no interactive steps (fill/click/select)
    interactive = []
    for tc in ordered:
        if _has_interactive_step(tc, intents_by_id):
            interactive.append(tc)
        else:
            _logger.warning(
                f"Dropping {tc.test_case_id} '{tc.test_case_name}' — no fill/click/select steps"
            )
    ordered = interactive

    # Soft check: warn if any type is missing from the final set
    present_types = {tc.test_case_type for tc in ordered}
    for required in ("positive", "negative", "boundary", "out_of_box"):
        if required not in present_types:
            _logger.warning(f"Test suite has no '{required}' test cases — consider adding one")

    # Re-number TC IDs to maintain the TC-001, TC-002, … sequence
    return [
        tc.model_copy(update={"test_case_id": f"TC-{i:03d}"})
        for i, tc in enumerate(ordered, start=1)
    ]


def generate_test_cases_from_flows(
    user_flows: List[dict],
    intents: List[IntentDefinition],
    td_ref_map: Dict[str, str] = None,
) -> List[TestCase]:
    """
    Directly convert user flows to TestCase objects without LLM.

    Each flow step's locator_id is matched to an intent by locator_id.
    Only flows with can_generate_test_case_directly=True are converted.
    Returns test cases with IDs TC-FLOW-001, TC-FLOW-002, etc.
    """
    td_ref_map = td_ref_map or {}

    # Build locator_id → intent_id lookup
    loc_to_intent: Dict[str, str] = {
        i.locator_id: i.intent_id
        for i in intents
        if i.locator_id
    }

    test_cases: List[TestCase] = []
    counter = 1

    for flow in user_flows:
        if not flow.get("can_generate_test_case_directly", False):
            continue

        flow_id = flow.get("flow_id", f"FLOW-{counter:03d}")
        flow_name = flow.get("inferred_name", f"User Flow {counter}")
        scenario_id = f"SC-FLOW-{counter:03d}"

        # Map flow steps to intent IDs
        step_intent_ids: List[str] = []
        for step in flow.get("steps", []):
            loc_id = step.get("locator_id")
            if not loc_id:
                continue
            intent_id = loc_to_intent.get(loc_id)
            if intent_id and intent_id not in step_intent_ids:
                step_intent_ids.append(intent_id)

        if not step_intent_ids:
            _logger.debug(f"Flow {flow_id} has no matching intents — skipping test case")
            continue

        test_cases.append(TestCase(
            test_case_id=f"TC-FLOW-{counter:03d}",
            test_case_name=f"Flow: {flow_name}",
            business_scenario_id=scenario_id,
            steps=step_intent_ids,
            test_data_ref=td_ref_map.get(scenario_id),
            expected_result=flow.get("steps", [{}])[-1].get("display_text", "Flow completes"),
            test_case_type="positive",
        ))
        counter += 1

    _logger.info(f"Generated {len(test_cases)} test case(s) from {len(user_flows)} user flow(s)")
    return test_cases


def _has_interactive_step(tc: TestCase, intents_by_id: dict) -> bool:
    """Return True if the test case contains at least one fill, click, or select step."""
    return any(
        intents_by_id.get(step_id) and intents_by_id[step_id].action in {"fill", "click", "select"}
        for step_id in tc.steps
    )
