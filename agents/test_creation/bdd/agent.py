from typing import Dict, Optional

from agents.base_agent import BaseAgent
from tools.logger_config import get_logger


class BDDAgent(BaseAgent):
    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self.logger = get_logger("agent.bdd")

    def execute(self, request: dict, state: dict) -> Dict[str, str]:
        project_name = request.get("project_name", "unknown")
        self.logger.info(f"[BDDAgent] Starting — project='{project_name}'")
        try:
            result = {"module": "bdd", "status": "stub"}
            self.logger.info("[BDDAgent] Done")
            return result
        except Exception as exc:
            self.logger.error(f"[BDDAgent] Failed — {exc}")
            raise
