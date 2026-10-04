"""
OutputValidationAgent — compares each evidence bundle's observed output with its BRD expectation.

engines/validation/output.py runs the deterministic checks (flow completed, document produced /
readable / non-empty / right format / reflects the input, reply or 2xx or page change, negative
input visibly rejected, no server errors, stated time limits). Gemini judges each pass criterion
against the actual output in batches (prompt.py); every "met" must quote that output verbatim and
is downgraded when the quote cannot be found. Output: one validation per bundle, for Pass/Fail.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from agents.base_agent import BaseAgent
from agents.evaluation.output_validation.prompt import OUTPUT_JUDGE_PROMPT
from agents.evaluation.output_validation.tools import (
    OUTPUT_JUDGEMENTS,
    assemble,
    deterministic_checks,
    generate_json,
    ground_judgement,
    judge_payload,
    needs_judge,
    run_artifact_dir,
)
from connectors.connector_registry import ConnectorRegistry
from tools.agent_eval.untrusted import neutralise
from tools.shared import get_logger

BATCH = 4          # documents can be long: few tests per call
MAX_WORKERS = 3


class OutputValidationAgent(BaseAgent):
    MODULE_NAME = "output_validation"

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self._registry = ConnectorRegistry(self.settings)
        self.logger = get_logger("agent.output_validation")

    def execute(self, request: dict, state: dict) -> Dict[str, Any]:
        emit = request.get("emit") or (lambda *a, **k: None)
        col = request.get("evidence_collection")
        if request.get("mode") == "brd_only" or not col or not col.get("bundles"):
            return {"module": self.MODULE_NAME, "status": "skipped", "reason": "no runtime evidence to validate",
                    "output_validation": None}
        root = run_artifact_dir(request.get("run_id") or "adhoc")
        bundles: List[dict] = col["bundles"]
        checks = {b["bundle_id"]: deterministic_checks(b, root) for b in bundles}

        to_judge = [b for b in bundles if needs_judge(b)]
        judged, judge_error = {}, None
        if to_judge:
            emit(f"Validating {len(bundles)} test output(s): deterministic checks for all, Gemini judging "
                 f"{len(to_judge)} against their BRD expectations.")
            judged, judge_error = self._judge(to_judge, root, request, emit)

        results = [assemble(b, checks[b["bundle_id"]], judged.get(b["bundle_id"]),
                            judge_error if needs_judge(b) and b["bundle_id"] not in judged else None) for b in bundles]
        validated = [r for r in results if r["status"] == "validated"]
        counts = {
            "bundles": len(results), "validated": len(validated),
            "not_validatable": len(results) - len(validated),
            "checks_passed": sum(1 for r in validated for c in r["checks"] if c["result"] == "pass"),
            "checks_failed": sum(1 for r in validated for c in r["checks"] if c["result"] == "fail"),
            "judged": sum(1 for r in validated if r.get("judge")),
            "meets": sum(1 for r in validated if (r.get("judge") or {}).get("assessment") == "meets"),
            "ungrounded_quotes": sum((r.get("judge") or {}).get("ungrounded_quotes", 0) for r in validated),
        }
        emit(f"Output validation: {counts['validated']} validated ({counts['checks_passed']} checks passed, "
             f"{counts['checks_failed']} failed), {counts['judged']} judged ({counts['meets']} fully meet the expectation), "
             f"{counts['not_validatable']} not validatable.", "success")
        if counts["ungrounded_quotes"]:
            emit(f"{counts['ungrounded_quotes']} judge claim(s) quoted text that is not in the output and were downgraded.", "warning")
        return {"module": self.MODULE_NAME, "status": "partial" if judge_error and not judged else "success",
                **({"error": judge_error} if judge_error and not judged else {}),
                "output_validation": {"counts": counts, "results": results}}

    def _judge(self, bundles: List[dict], root, request, emit):
        try:
            llm = self._registry.get_llm(request.get("connector_mode"))
        except Exception as exc:
            emit(f"No LLM available for output judging ({exc}); deterministic checks only.", "warning")
            return {}, str(exc)
        app_type = ((request.get("app_classification") or {}).get("app_type")
                    or (request.get("runtime_profile") or {}).get("app_type") or "unknown")
        by_id = {b["bundle_id"]: b for b in bundles}

        def ask(batch: List[dict]) -> List[dict]:
            payload = json.dumps([judge_payload(b, root) for b in batch], indent=1, ensure_ascii=False)
            prompt = OUTPUT_JUDGE_PROMPT.substitute(app_type=app_type, tests=neutralise(payload))
            return generate_json(llm, prompt, required_keys=["judgements"], schema=OUTPUT_JUDGEMENTS,
                                 temperature=0.0).get("judgements") or []

        batches = [bundles[i:i + BATCH] for i in range(0, len(bundles), BATCH)]
        out, errors = {}, []
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(batches))) as pool:
            for fut in [pool.submit(ask, b) for b in batches]:
                try:
                    for j in fut.result():
                        b = by_id.get(str(j.get("bundle_id") or ""))
                        if b:
                            out[b["bundle_id"]] = ground_judgement(j, b, root)
                except Exception as exc:
                    errors.append(str(exc)[:200])
                    emit(f"Judging one batch failed ({exc}); those tests keep deterministic checks only.", "warning")
        return out, ("; ".join(errors) or None)
