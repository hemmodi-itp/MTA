import os
from typing import Dict, List

import yaml

from tools.artifact_generator.models import IntentDefinition, TestCase, TestSuiteDefinition


def export_artifacts(
    intents: List[IntentDefinition],
    test_cases: List[TestCase],
    suite: TestSuiteDefinition,
    output_dir: str,
) -> Dict[str, str]:
    os.makedirs(output_dir, exist_ok=True)

    intents_path = os.path.join(output_dir, "intents.yaml")
    test_cases_path = os.path.join(output_dir, "test_cases.yaml")
    suite_path = os.path.join(output_dir, "test_suite.yaml")

    _write_intents(intents, intents_path, suite.project)
    _write_test_cases(test_cases, test_cases_path, suite.project)
    _write_suite(suite, suite_path)

    return {
        "intents": intents_path,
        "test_cases": test_cases_path,
        "test_suite": suite_path,
    }


def export_intents_only(
    intents: List[IntentDefinition],
    output_dir: str,
    project: str,
) -> str:
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "intents.yaml")
    _write_intents(intents, path, project)
    return path


def _write_intents(intents: List[IntentDefinition], path: str, project: str) -> None:
    payload = {
        "project": project,
        "intent_count": len(intents),
        "intents": [_intent_to_dict(i) for i in intents],
    }
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(payload, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _write_test_cases(test_cases: List[TestCase], path: str, project: str) -> None:
    payload = {
        "project": project,
        "test_case_count": len(test_cases),
        "test_cases": [_tc_to_dict(tc) for tc in test_cases],
    }
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(payload, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _write_suite(suite: TestSuiteDefinition, path: str) -> None:
    payload = {
        "suite_name": suite.suite_name,
        "project": suite.project,
        "test_case_count": len(suite.test_cases),
        "test_cases": [tc.test_case_id for tc in suite.test_cases],
    }
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(payload, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _intent_to_dict(i: IntentDefinition) -> dict:
    return {
        "intent_id": i.intent_id,
        "intent_name": i.intent_name,
        "action": i.action,
        "locator_id": i.locator_id,
        "value": i.value,
        "description": i.description,
        "source_scenarios": i.source_scenarios,
    }


def _tc_to_dict(tc: TestCase) -> dict:
    return {
        "test_case_id": tc.test_case_id,
        "test_case_name": tc.test_case_name,
        "business_scenario_id": tc.business_scenario_id,
        "test_case_type": tc.test_case_type,
        "steps": tc.steps,
        "test_data_ref": tc.test_data_ref,
        "expected_result": tc.expected_result,
    }
