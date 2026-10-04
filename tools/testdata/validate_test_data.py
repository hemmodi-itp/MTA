from typing import List, Tuple

from tools.testdata.models import ScenarioTestData

_REQUIRED_VARIANT_TYPES = {"empty", "special_chars", "wrong_format", "boundary", "random"}
_MIN_VARIANTS = 3


def validate_test_data(
    datasets: List[ScenarioTestData],
) -> Tuple[List[ScenarioTestData], List[str]]:
    """
    Validate generated test datasets and return (valid_datasets, warnings).

    A dataset is valid when:
    - positive_dataset has at least one field
    - at least MIN_VARIANTS negative variants are present
    """
    valid: List[ScenarioTestData] = []
    warnings: List[str] = []

    for ds in datasets:
        # Read-only scenarios (no input fields) are valid as-is — nothing to test
        if not ds.positive_dataset and not ds.negative_variants:
            valid.append(ds)
            continue

        hard_issues = []

        if not ds.positive_dataset:
            hard_issues.append(
                f"{ds.testdata_id} ({ds.scenario_id}): no positive dataset fields"
            )

        if len(ds.negative_variants) < _MIN_VARIANTS:
            hard_issues.append(
                f"{ds.testdata_id} ({ds.scenario_id}): only "
                f"{len(ds.negative_variants)} negative variant(s) — expected ≥{_MIN_VARIANTS}"
            )

        # Missing variant types are a soft warning — dataset is still usable
        present_types = {v.variant_type for v in ds.negative_variants}
        missing_types = _REQUIRED_VARIANT_TYPES - present_types
        if missing_types:
            warnings.append(
                f"{ds.testdata_id} ({ds.scenario_id}): missing variant types: "
                f"{', '.join(sorted(missing_types))} (warning only)"
            )

        if hard_issues:
            warnings.extend(hard_issues)
        else:
            valid.append(ds)

    return valid, warnings
