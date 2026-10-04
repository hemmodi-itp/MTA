from typing import List
from pydantic import BaseModel


class AgentSkill(BaseModel):
    name: str
    description: str
    strengths: List[str]

    def header(self) -> str:
        """Compact block injected at the top of every LLM prompt for this agent."""
        return (
            f"[Skill: {self.name}]\n"
            f"{self.description}\n"
            f"Strengths: {', '.join(self.strengths)}\n"
        )
