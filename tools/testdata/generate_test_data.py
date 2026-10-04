import json
from typing import List

from tools.shared.llm_response_validator import parse_llm_json
from tools.comprehension.models import BusinessScenario
from tools.testdata.models import NegativeVariant, ScenarioTestData, TestDataField


def generate_test_data(
    scenario: BusinessScenario,
    llm_connector,
    prompt_template,
    skill_header: str,
    testdata_index: int,
    max_retries: int = 1,
    fill_fields_hint: str = "",
    existing_format_guide: str = "",
) -> ScenarioTestData:
    """
    Ask the LLM to generate positive + negative test data for one scenario.
    Retries once on JSON parse failure (handles occasional truncated responses).

    Args:
        scenario:               BusinessScenario from comprehension output
        llm_connector:          LLMConnector instance (BedrockConnector, etc.)
        prompt_template:        string.Template — TEST_DATA_GENERATION_PROMPT
        skill_header:           rendered AgentSkill.header() string
        testdata_index:         1-based index used to build TD-XXX id
        max_retries:            number of retries on JSON parse error (default 1)
        fill_fields_hint:       optional hint about exact field_name values to use
        existing_format_guide:  capped content of test_data.md for style consistency
    """
    prompt = prompt_template.safe_substitute(
        skill_header=skill_header,
        fill_fields_hint=fill_fields_hint,
        existing_format_guide=existing_format_guide,
        scenario_id=scenario.scenario_id,
        title=scenario.title,
        actor=scenario.actor,
        business_objective=scenario.business_objective,
        preconditions_json=json.dumps(scenario.preconditions, ensure_ascii=False),
        steps_json=json.dumps(scenario.steps, ensure_ascii=False),
        expected_result=scenario.expected_result,
    )

    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            raw = llm_connector.generate(prompt)
            parsed = parse_llm_json(raw)
            return _build_model(parsed, scenario, testdata_index)
        except ValueError as exc:
            last_exc = exc
            if attempt < max_retries:
                continue  # retry
    raise last_exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_model(
    parsed: dict,
    scenario: BusinessScenario,
    index: int,
) -> ScenarioTestData:
    testdata_id = f"TD-{index:03d}"

    positive_dataset: List[TestDataField] = [
        TestDataField(
            field_name=f.get("field_name", "unknown"),
            field_type=f.get("field_type", "text"),
            value=str(f.get("value", "")),
        )
        for f in parsed.get("positive_dataset", [])
    ]

    negative_variants: List[NegativeVariant] = []
    for i, nv in enumerate(parsed.get("negative_variants", []), start=1):
        fields = [
            TestDataField(
                field_name=f.get("field_name", "unknown"),
                field_type=f.get("field_type", "text"),
                value=str(f.get("value", "")),
            )
            for f in nv.get("fields", [])
        ]
        negative_variants.append(
            NegativeVariant(
                variant_id=f"NEG-{i:03d}",
                variant_type=nv.get("variant_type", "unknown"),
                description=nv.get("description", ""),
                fields=fields,
                expected_error=nv.get("expected_error"),
            )
        )

    return ScenarioTestData(
        testdata_id=testdata_id,
        scenario_id=scenario.scenario_id,
        scenario_title=scenario.title,
        actor=scenario.actor,
        positive_dataset=positive_dataset,
        negative_variants=negative_variants,
    )
