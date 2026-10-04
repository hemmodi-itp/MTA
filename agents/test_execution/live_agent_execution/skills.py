"""skills.py — AgentSkill entries for LiveAgentExecutionAgent."""

from tools.shared.skill_model import AgentSkill

SKILLS = {
    "response_judging": AgentSkill(
        name="LLM-as-judge response grading",
        description="Grades a deployed AI agent's replies against expected behaviour and pass criteria.",
        strengths=[
            "semantic (not string) matching of expected behaviour",
            "detecting prompt-injection compliance and system-prompt leaks",
            "spotting hallucinated facts and unhelpful refusals",
        ],
    ),
}
