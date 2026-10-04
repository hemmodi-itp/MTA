from typing import List, Tuple

from tools.artifact_generator.models import IntentDefinition, TestCase


def validate_artifacts(
    intents: List[IntentDefinition],
    test_cases: List[TestCase],
) -> Tuple[List[TestCase], List[str]]:
    """
    Validate test case integrity against the intent list.

    Checks:
    - Each TC step references a valid INT-XXX id
    - No test cases with zero steps

    Returns (valid_test_cases, warnings).
    """
    valid_ids = {i.intent_id for i in intents}
    valid: List[TestCase] = []
    warnings: List[str] = []

    for tc in test_cases:
        if not tc.steps:
            warnings.append(f"{tc.test_case_id} ({tc.business_scenario_id}): no steps — dropped")
            continue

        bad_steps = [s for s in tc.steps if s not in valid_ids]
        if bad_steps:
            warnings.append(
                f"{tc.test_case_id} ({tc.business_scenario_id}): "
                f"references unknown intent IDs {bad_steps} — dropped"
            )
            continue

        valid.append(tc)

    # Warn about intents never used in any valid TC
    used_ids = {step for tc in valid for step in tc.steps}
    orphaned = [i.intent_id for i in intents if i.intent_id not in used_ids]
    if orphaned:
        warnings.append(f"Orphaned intents (not referenced by any test case): {orphaned}")

    return valid, warnings
