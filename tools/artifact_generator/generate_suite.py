from typing import List

from tools.artifact_generator.models import TestCase, TestSuiteDefinition


def generate_suite(
    test_cases: List[TestCase],
    suite_name: str,
    project: str,
) -> TestSuiteDefinition:
    return TestSuiteDefinition(
        suite_name=suite_name,
        project=project,
        test_cases=test_cases,
    )
