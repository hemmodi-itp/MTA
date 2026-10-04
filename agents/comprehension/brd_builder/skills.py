"""skills.py — AgentSkill entries for BrdBuilderAgent."""

from tools.shared.skill_model import AgentSkill

SKILLS = {
    "brd_generation": AgentSkill(
        name="BRD reverse-engineering",
        description="Writes a Business Requirements Document for an AI agent from its source code and prompts.",
        strengths=[
            "turning code intent into testable functional requirements",
            "adding safety, robustness and latency non-functional requirements",
            "flagging inferred vs. evidenced behaviour",
        ],
    ),
    "requirement_extraction": AgentSkill(
        name="Requirement extraction",
        description="Extracts a prioritised, numbered list of testable requirements from a BRD/PRD/spec.",
        strengths=[
            "acceptance-criteria extraction",
            "priority assignment by business impact",
            "merging duplicated requirements",
        ],
    ),
}
