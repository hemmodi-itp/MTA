import json
from typing import List

from tools.shared.llm_response_validator import parse_llm_json
from tools.comprehension.models import BusinessScenario
from tools.test_creation.testdata.models import NegativeVariant, ScenarioTestData, TestDataField, TestDataIteration


def generate_test_data(
    scenario: BusinessScenario,
    llm_connector,
    prompt_template,
    skill_header: str,
    testdata_index: int,
    max_retries: int = 1,
    fill_fields_hint: str = "",
    existing_format_guide: str = "",
    max_negative_cases: int = 1,
    max_boundary_cases: int = 1,
    max_data_iterations: int = 3,
) -> ScenarioTestData:
    """
    Ask the LLM to generate positive + negative/boundary test data for one scenario.
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
        max_negative_cases:     at most this many "negative" variants (see
                                test_generation config in project.yaml)
        max_boundary_cases:     at most this many "boundary" variants
        max_data_iterations:    at most this many alternate bad-value iterations
                                packed into each variant
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
        max_negative_cases=max_negative_cases,
        max_boundary_cases=max_boundary_cases,
        max_data_iterations=max_data_iterations,
    )

    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            raw = llm_connector.generate(prompt)
            parsed = parse_llm_json(raw)
            return _build_model(
                parsed, scenario, testdata_index,
                max_negative_cases=max_negative_cases,
                max_boundary_cases=max_boundary_cases,
                max_data_iterations=max_data_iterations,
            )
        except ValueError as exc:
            last_exc = exc
            if attempt < max_retries:
                continue  # retry
    raise last_exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_fields(raw_fields: list) -> List[TestDataField]:
    return [
        TestDataField(
            field_name=f.get("field_name", "unknown"),
            field_type=f.get("field_type", "text"),
            value=str(f.get("value", "")),
        )
        for f in raw_fields
    ]


def _build_model(
    parsed: dict,
    scenario: BusinessScenario,
    index: int,
    max_negative_cases: int = 1,
    max_boundary_cases: int = 1,
    max_data_iterations: int = 3,
) -> ScenarioTestData:
    testdata_id = f"TD-{index:03d}"

    positive_dataset = _build_fields(parsed.get("positive_dataset", []))

    negative_count = 0
    boundary_count = 0
    negative_variants: List[NegativeVariant] = []

    for i, nv in enumerate(parsed.get("negative_variants", []), start=1):
        variant_type = nv.get("variant_type", "negative")
        is_boundary = variant_type == "boundary"

        # Defensive cap — the LLM is instructed to respect these limits, but
        # don't rely on it: dropping extras here is what actually enforces
        # "max N negative + max M boundary cases per scenario".
        if is_boundary:
            if boundary_count >= max_boundary_cases:
                continue
            boundary_count += 1
        else:
            if negative_count >= max_negative_cases:
                continue
            negative_count += 1

        raw_iterations = nv.get("iterations")
        if not raw_iterations:
            # Back-compat: legacy flat {fields, expected_error} shape.
            raw_iterations = [{"fields": nv.get("fields", []), "expected_error": nv.get("expected_error")}]

        iterations = [
            TestDataIteration(
                fields=_build_fields(it.get("fields", [])),
                expected_error=it.get("expected_error"),
            )
            for it in raw_iterations[:max_data_iterations]
        ]

        negative_variants.append(
            NegativeVariant(
                variant_id=f"NEG-{i:03d}",
                variant_type=variant_type,
                description=nv.get("description", ""),
                iterations=iterations,
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
