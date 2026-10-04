"""
AppClassificationAgent — decides what kind of application the submission is.

Deterministic (engines/runtime/classification.py): weighs runtime signals from the Runtime
Discovery profile (inputs, generate/download buttons, chat box, charts, step/approval actions)
and code signals from the repository knowledge graph (routes, forms, dependencies, file-generation
and chat code) into one of: Chatbot, Form Application, Dashboard, Document Generator, REST API,
Workflow System, Static Website, Hybrid Application. Outputs the class, confidence, per-class
scores, the evidence behind them, and the testing strategy Action Generation should follow.
"""

from typing import Any, Dict, Optional

from agents.base_agent import BaseAgent
from agents.comprehension.app_classification.tools import classify
from tools.shared import get_logger


class AppClassificationAgent(BaseAgent):
    MODULE_NAME = "app_classification"

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self.logger = get_logger("agent.app_classification")

    def execute(self, request: dict, state: dict) -> Dict[str, Any]:
        emit = request.get("emit") or (lambda *a, **k: None)
        profile = request.get("runtime_profile")
        graph = request.get("repo_graph")
        if not profile and graph is None:
            return {"module": self.MODULE_NAME, "status": "skipped", "reason": "no runtime profile or code graph",
                    "app_classification": None}

        result = classify(profile, graph, request.get("code_chunks") or (), request.get("repo_model") or {})
        top = [e["signal"] for e in result["evidence"] if e["class"] in (result["components"] or [result["app_type"]])][:3]
        label = result["app_type"] + (f" ({' + '.join(result['components'])})" if result["components"] else "")
        emit(f"Found: {'; '.join(top) or 'no strong signals'} → {label} "
             f"(confidence {result['confidence']:.0%}, from {result['basis']})",
             "success" if result["app_type"] != "Unknown" else "warning")
        if result.get("note"):
            emit(result["note"], "warning")
        for s in result["testing_strategy"]:
            emit(f"Testing strategy · {s['class']}: {s['strategy']}")
        return {"module": self.MODULE_NAME, "status": "success", "app_classification": result}
