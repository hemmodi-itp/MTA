"""skills.py — AgentSkill entries for TestDesignAgent."""

from tools.shared.skill_model import AgentSkill

SKILLS = {
    "test_design": AgentSkill(
        name="Test Designer",
        description=(
            "Interprets acceptance criteria for deterministic test-design generators: extracts decision-table "
            "conditions and rules, says whether a criterion has a negative path, links generated cases to "
            "criteria, and adds the few business-rule cases generic techniques cannot know."
        ),
        strengths=[
            "decision tables from if / when / unless / only-if wording",
            "recognising negative paths in acceptance criteria",
            "mapping test cases to acceptance criteria",
            "domain-specific business-rule cases (calculations, once-only rules, sequences)",
        ],
    )
}
