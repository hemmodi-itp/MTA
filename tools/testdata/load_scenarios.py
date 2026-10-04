import json
import os
from typing import List

from tools.comprehension.models import BusinessScenario


def load_scenarios(comprehension_output_dir: str) -> List[BusinessScenario]:
    """
    Read business_scenarios.json produced by ComprehensionAgent and
    return a list of BusinessScenario objects.

    Args:
        comprehension_output_dir: path to the project's comprehension output folder,
            e.g. application_assets/comprehension_output/alterdomus
    """
    json_path = os.path.join(comprehension_output_dir, "business_scenarios.json")
    if not os.path.exists(json_path):
        raise FileNotFoundError(
            f"Comprehension output not found at '{json_path}'. "
            "Run the comprehension agent first."
        )

    with open(json_path, encoding="utf-8") as f:
        raw = json.load(f)

    # Export format is {"project": "...", "scenarios": [...]}
    scenarios_list = raw.get("scenarios", raw) if isinstance(raw, dict) else raw
    return [BusinessScenario(**item) for item in scenarios_list]
