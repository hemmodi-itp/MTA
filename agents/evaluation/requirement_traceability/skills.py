"""skills.py — AgentSkill entries for RequirementTraceabilityAgent."""

from tools.shared.skill_model import AgentSkill

SKILLS = {
    "evidence_verification": AgentSkill(
        name="Requirement-to-code evidence verification",
        description="Decides whether retrieved code implements one acceptance criterion, with line-exact citations.",
        strengths=[
            "separating enforced behaviour from prompt-only instructions",
            "refusing to prove numeric/runtime claims from static code",
            "honest insufficient-evidence verdicts instead of guesses",
        ],
    ),
}
