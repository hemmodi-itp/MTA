from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Any


@dataclass
class ExecutionTraceItem:
    step: str
    start_time: str
    end_time: str
    duration_ms: int
    status: str
    reason: str = ""


@dataclass
class WorkflowState:
    run_id: str = ""
    workflow_id: str = ""
    workflow_name: str = ""
    current_step: str = ""
    completed_steps: List[str] = field(default_factory=list)
    execution_trace: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[Dict[str, str]] = field(default_factory=list)
    outputs: Dict[str, Any] = field(default_factory=dict)

    def update_step(self, step_name: str, result: dict) -> None:
        self.current_step = step_name
        self.outputs[step_name] = result
        if step_name not in self.completed_steps:
            self.completed_steps.append(step_name)

    def start_step(self, step_name: str) -> Dict[str, Any]:
        trace_entry = {
            "step": step_name,
            "start_time": datetime.now(timezone.utc).isoformat(),
            "end_time": "",
            "duration_ms": 0,
            "status": "running",
            "reason": "",
        }
        self.execution_trace.append(trace_entry)
        return trace_entry

    def finish_step(self, step_name: str, status: str = "success", reason: str = "") -> None:
        if not self.execution_trace:
            return
        trace_entry = self.execution_trace[-1]
        if trace_entry.get("step") != step_name:
            trace_entry = next((entry for entry in self.execution_trace if entry["step"] == step_name), None)
            if trace_entry is None:
                return
        trace_entry["end_time"] = datetime.now(timezone.utc).isoformat()
        try:
            start_time = datetime.fromisoformat(trace_entry["start_time"].replace("Z", ""))
            end_time = datetime.fromisoformat(trace_entry["end_time"].replace("Z", ""))
            trace_entry["duration_ms"] = int((end_time - start_time).total_seconds() * 1000)
        except Exception:
            trace_entry["duration_ms"] = 0
        trace_entry["status"] = status
        trace_entry["reason"] = reason

    def record_error(self, step_name: str, reason: str) -> None:
        self.errors.append({"step": step_name, "reason": reason})
        self.finish_step(step_name, status="failed", reason=reason)
