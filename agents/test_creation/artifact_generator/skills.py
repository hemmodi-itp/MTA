from tools.shared.skill_model import AgentSkill

SKILLS = {
    "artifact_generator": AgentSkill(
        name="UI Test Artifact Generator",
        description=(
            "Translates structured business scenarios into atomic UI test intents "
            "and ordered test cases ready for Playwright execution."
        ),
        strengths=[
            "action classification (fill, click, select, navigate, verify)",
            "intent deduplication across scenarios",
            "step sequencing from business process flows",
            "test case construction with explicit intent ordering",
        ],
    )
}
