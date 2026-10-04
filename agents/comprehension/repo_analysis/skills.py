"""skills.py — AgentSkill entries for RepoAnalysisAgent."""

from tools.shared.skill_model import AgentSkill

SKILLS = {
    "repo_analysis": AgentSkill(
        name="AI agent repository analysis",
        description="Reads an AI agent's source code and infers its purpose, capabilities and invocation interface.",
        strengths=[
            "recognising agent frameworks (LangChain, LangGraph, CrewAI, ADK, OpenAI Agents)",
            "locating HTTP routes and request/response shapes",
            "separating stated purpose from incidental code",
        ],
    ),
}
