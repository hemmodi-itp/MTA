"""skills.py — AgentSkill entries for AgentTestGenerationAgent."""

from tools.shared.skill_model import AgentSkill

SKILLS = {
    "agent_test_design": AgentSkill(
        name="AI agent test design",
        description="Designs black-box prompt/response test cases that verify an AI agent against its BRD.",
        strengths=[
            "requirement-traced positive, negative and edge cases",
            "LLM-specific risks: prompt injection, hallucination, scope creep, unsafe output",
            "observable pass criteria an evaluator model can check",
        ],
    ),
}
