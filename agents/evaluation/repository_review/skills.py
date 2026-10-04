"""skills.py — AgentSkill entries for RepositoryReviewAgent."""

from tools.shared.skill_model import AgentSkill

SKILLS = {
    "ai_app_review": AgentSkill(
        name="AI application design review",
        description="Reviews agent design, architecture, workflow and security of an LLM application from its code.",
        strengths=["prompt-injection exposure", "tool least-privilege", "failure-path handling"],
    ),
}
