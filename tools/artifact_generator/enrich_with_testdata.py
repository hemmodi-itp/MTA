import json
import os
from typing import Dict, List, Optional, Tuple

from tools.artifact_generator.models import IntentDefinition, TestCase


# Action prefixes stripped during normalized field-name matching
_ACTION_PREFIXES = ("fill_", "select_", "enter_", "type_", "click_")

# Maps test_case_type → ordered list of negative_variant types to try
_TYPE_TO_VARIANT: Dict[str, List[str]] = {
    "positive":   [],                              # use positive_dataset
    "negative":   ["wrong_format", "special_chars"],
    "boundary":   ["boundary"],
    "out_of_box": ["random"],
}


def load_test_data(project_assets_dir: str) -> List[dict]:
    """
    Read test_data.json from application_assets/projects/{project}/test_data/.
    Returns a list of raw dicts (ScenarioTestData model dumps).
    Returns empty list if file is not found.
    """
    path = os.path.join(project_assets_dir, "test_creation", "test_data", "test_data.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _normalize(name: str) -> str:
    """Strip action prefix and underscores for fuzzy field-name comparison."""
    n = name.lower()
    for pfx in _ACTION_PREFIXES:
        if n.startswith(pfx):
            n = n[len(pfx):]
            break
    return n.replace("_", "")


def _build_positive_lookup(td_records: List[dict]) -> Dict[str, Tuple[str, str]]:
    """
    Build {key: (value, td_id)} from all positive_datasets.
    Each field contributes two keys: exact field_name and normalized field_name.
    First match wins per key.
    """
    lookup: Dict[str, Tuple[str, str]] = {}
    for td in td_records:
        td_id = td.get("testdata_id", "")
        for field in td.get("positive_dataset", []):
            fname = field.get("field_name", "")
            val = field.get("value", "")
            if not fname:
                continue
            if fname not in lookup:
                lookup[fname] = (val, td_id)
            norm = _normalize(fname)
            if norm and norm not in lookup:
                lookup[norm] = (val, td_id)
    return lookup


def _match_field_value(intent_name: str, lookup: Dict[str, Tuple[str, str]]) -> Optional[str]:
    """
    Three-layer lookup: exact → normalized → substring of normalized.
    Returns the matched value string, or None if no match.
    """
    # 1. Exact
    if intent_name in lookup:
        return lookup[intent_name][0]
    # 2. Normalized exact
    norm = _normalize(intent_name)
    if norm in lookup:
        return lookup[norm][0]
    # 3. Substring: normalized fragment of one is contained in the other (min 3 chars)
    if len(norm) >= 3:
        for key, (val, _) in lookup.items():
            knorm = _normalize(key)
            if len(knorm) >= 3 and (knorm in norm or norm in knorm):
                return val
    return None


def enrich_with_testdata(
    intents: List[IntentDefinition],
    test_data_records: List[dict],
) -> List[IntentDefinition]:
    """
    Populate the `value` field of fill/select intents using positive_dataset from test data.

    Three-layer matching (exact → normalized → substring) so that field_name "email"
    matches intent_name "fill_email" and vice versa.
    """
    lookup = _build_positive_lookup(test_data_records)
    enriched = []
    for intent in intents:
        if intent.action in {"fill", "select"}:
            val = _match_field_value(intent.intent_name, lookup)
            if val is not None:
                enriched.append(intent.model_copy(update={"value": val}))
                continue
        enriched.append(intent)
    return enriched


def build_test_data_ref_map(
    test_data_records: List[dict],
) -> Dict[str, str]:
    """Return BS scenario_id → TD-XXX id mapping."""
    return {
        td.get("scenario_id", ""): td.get("testdata_id", "")
        for td in test_data_records
        if td.get("scenario_id") and td.get("testdata_id")
    }


def build_type_enriched_steps(
    test_case: "TestCase",
    intents_by_id: Dict[str, "IntentDefinition"],
    test_data_records: List[dict],
) -> List[dict]:
    """
    Build the steps payload for script generation with type-correct field values.

    - positive  → values from positive_dataset
    - negative  → values from wrong_format or special_chars variant
    - boundary  → values from boundary variant
    - out_of_box → values from random variant

    Falls back to the intent's already-enriched value when no variant match is found.
    Returns a list of step dicts ready to pass to the LLM script prompt.
    """
    tc_type = test_case.test_case_type
    preferred_variants = _TYPE_TO_VARIANT.get(tc_type, [])

    # Find the test data record for this scenario
    td = next(
        (r for r in test_data_records if r.get("scenario_id") == test_case.business_scenario_id),
        None,
    )

    # Build per-type lookup for this specific scenario
    positive_lookup: Dict[str, str] = {}
    variant_lookup: Dict[str, str] = {}

    if td:
        for field in td.get("positive_dataset", []):
            fname = field.get("field_name", "")
            if fname:
                positive_lookup[fname] = field.get("value", "")
                norm = _normalize(fname)
                if norm:
                    positive_lookup[norm] = field.get("value", "")

        if preferred_variants:
            neg_variants = td.get("negative_variants", [])
            for want_type in preferred_variants:
                matched = next(
                    (v for v in neg_variants if v.get("variant_type") == want_type),
                    None,
                )
                if matched:
                    for field in matched.get("fields", []):
                        fname = field.get("field_name", "")
                        if fname:
                            variant_lookup[fname] = field.get("value", "")
                            norm = _normalize(fname)
                            if norm:
                                variant_lookup[norm] = field.get("value", "")
                    break  # use first found preferred variant

    def _resolve_value(intent: IntentDefinition) -> Optional[str]:
        if intent.action not in {"fill", "select"}:
            return intent.value
        name = intent.intent_name
        norm = _normalize(name)
        if tc_type == "positive":
            return (
                positive_lookup.get(name)
                or positive_lookup.get(norm)
                or intent.value
            )
        else:
            return (
                variant_lookup.get(name)
                or variant_lookup.get(norm)
                or positive_lookup.get(name)
                or positive_lookup.get(norm)
                or intent.value
            )

    steps = []
    for step_id in test_case.steps:
        intent = intents_by_id.get(step_id)
        if intent is None:
            continue
        steps.append({
            "intent_id": intent.intent_id,
            "intent_name": intent.intent_name,
            "action": intent.action,
            "selector": intent.locator_id,
            "value": _resolve_value(intent),
            "description": intent.description,
        })
    return steps
