"""
validate_business_scenarios — lightweight structural validation for the POC.

Checks for: empty fields, missing actors, missing expected results,
missing traceability, and duplicate scenario titles.

Returns (valid_scenarios, warnings).  Invalid scenarios are excluded from
valid_scenarios but their issues are surfaced as warnings — not hard errors.
"""

from typing import List, Tuple

from tools.comprehension.models import BusinessScenario


def validate_business_scenarios(
    scenarios: List[BusinessScenario],
) -> Tuple[List[BusinessScenario], List[str]]:
    """
    Validate a list of BusinessScenario objects.

    Returns:
        valid_scenarios: Scenarios that pass all required checks.
        warnings:        All issues found (including non-fatal ones like
                         missing traceability from otherwise valid scenarios).
    """
    warnings: List[str] = []
    seen_titles: set = set()
    valid: List[BusinessScenario] = []

    for scenario in scenarios:
        sid = scenario.scenario_id
        blocking_issues: List[str] = []

        if not scenario.title.strip():
            blocking_issues.append(f"{sid}: missing title")

        if not scenario.actor.strip():
            blocking_issues.append(f"{sid}: missing actor")

        if not scenario.steps:
            blocking_issues.append(f"{sid}: no steps defined")

        if not scenario.expected_result.strip():
            blocking_issues.append(f"{sid}: missing expected_result")

        title_key = scenario.title.strip().lower()
        if title_key and title_key in seen_titles:
            blocking_issues.append(
                f"{sid}: duplicate title '{scenario.title}'"
            )

        # Non-blocking warnings
        if not scenario.traceability:
            warnings.append(f"{sid}: no traceability references (non-fatal)")

        if scenario.confidence_score < 0.5:
            warnings.append(
                f"{sid}: low confidence score {scenario.confidence_score:.2f}"
            )

        if blocking_issues:
            warnings.extend(blocking_issues)
        else:
            seen_titles.add(title_key)
            valid.append(scenario)

    return valid, warnings
