from typing import List, Tuple

from tools.test_creation.testdata.models import ScenarioTestData

_VALID_VARIANT_TYPES = {"negative", "boundary"}


def validate_test_data(
    datasets: List[ScenarioTestData],
) -> Tuple[List[ScenarioTestData], List[str]]:
    """
    Validate generated test datasets and return (valid_datasets, warnings).

    Coverage is intentionally minimal by design (see test_generation config in
    project.yaml: default max 1 negative + 1 boundary variant) — this only
    hard-fails on structurally broken data, not on "too few" variants.

    A dataset is valid when:
    - positive_dataset has at least one field (unless the scenario is read-only)
    - every negative_variant has at least one iteration with at least one field
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

        for v in ds.negative_variants:
            if not v.iterations or not any(it.fields for it in v.iterations):
                hard_issues.append(
                    f"{ds.testdata_id} ({ds.scenario_id}): variant '{v.variant_id}' "
                    f"({v.variant_type}) has no usable iterations"
                )

        # Unrecognized variant_type values are a soft warning — dataset is still usable
        unexpected_types = {v.variant_type for v in ds.negative_variants} - _VALID_VARIANT_TYPES
        if unexpected_types:
            warnings.append(
                f"{ds.testdata_id} ({ds.scenario_id}): unexpected variant type(s): "
                f"{', '.join(sorted(unexpected_types))} (warning only)"
            )

        if hard_issues:
            warnings.extend(hard_issues)
        else:
            valid.append(ds)

    return valid, warnings
