import json
import string
from typing import List

from tools.shared.llm_response_validator import parse_llm_json
from tools.comprehension.models import BusinessScenario
from tools.artifact_generator.models import IntentDefinition


def generate_intents(
    scenarios: List[BusinessScenario],
    llm_connector,
    prompt_template: string.Template,
    skill_header: str,
    extra_subs: dict = None,
) -> List[IntentDefinition]:
    scenarios_payload = [
        {
            "scenario_id": s.scenario_id,
            "title": s.title,
            "actor": s.actor,
            "steps": s.steps,
        }
        for s in scenarios
    ]
    subs = {
        "skill_header": skill_header,
        "scenarios_json": json.dumps(scenarios_payload, ensure_ascii=False, indent=2),
        "md_context": "",
        "existing_intents_summary": "",
    }
    if extra_subs:
        subs.update(extra_subs)
    prompt = prompt_template.safe_substitute(**subs)
    raw = llm_connector.generate(prompt)
    parsed = parse_llm_json(raw)
    return _build_intents(parsed)



def _build_intents(parsed: dict) -> List[IntentDefinition]:
    raw_intents = parsed.get("intents", [])
    intents = []
    for i, item in enumerate(raw_intents, start=1):
        action = item.get("action", "click").lower().strip()
        if action not in {"fill", "click", "select", "navigate", "verify"}:
            action = "click"
        intents.append(
            IntentDefinition(
                intent_id=f"INT-{i:03d}",
                intent_name=item.get("intent_name", f"action_{i}"),
                action=action,
                description=item.get("description"),
                source_scenarios=item.get("source_scenarios", []),
            )
        )
    return intents
