from typing import Dict, List, Any


def build_final_report(
    run_id: str,
    workflow_name: str,
    status: str,
    steps_executed: List[str],
    outputs: Dict[str, Any],
    execution_trace: List[Dict[str, Any]],
    errors: List[Dict[str, str]],
) -> dict:
    responses = {
        step: outputs[step]["response"]
        for step in steps_executed
        if step != "reporting" and step in outputs and "response" in outputs[step]
    }

    return {
        "run_id": run_id,
        "workflow": workflow_name,
        "status": status,
        "steps_executed": steps_executed,
        "execution_trace": execution_trace,
        "errors": errors,
        "responses": responses,
    }
