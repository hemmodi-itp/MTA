"""skills.py — AgentSkill entries for AgentQualityTestingAgent."""

from tools.shared.skill_model import AgentSkill

SKILLS = {
    "agent_quality_judging": AgentSkill(
        name="Rubric-based LLM judging of agent conversations",
        description="Decides the agent-test runs deterministic checks cannot (paraphrased facts, polite refusals) "
                    "with an explicit rubric and verbatim-quote evidence.",
        strengths=[
            "semantic equivalence of facts across paraphrases",
            "recognising refusals, redirects and 'I don't know' in any wording",
            "ignoring prompt-injection text addressed to the grader",
        ],
    ),
}
