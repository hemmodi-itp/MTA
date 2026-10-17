"""
OutputValidationAgent — compares each evidence bundle's observed output with its BRD expectation.

engines/validation/output.py runs the deterministic checks (flow completed, document produced /
readable / non-empty / right format / reflects the input, reply or 2xx or page change, negative
input visibly rejected, no server errors, stated time limits). Gemini judges each pass criterion
against the actual output in batches (prompt.py); every "met" must quote that output verbatim and
is downgraded when the quote cannot be found. Output: one validation per bundle, for Pass/Fail.

Every test that needs a judgement gets one unless the LLM is down for good: a batch call that fails (timeout,
dropped connection) or whose reply leaves a test out is followed by one call per missing test, each retried once
after a pause. A test is "judge unavailable" only after all of that failed.
"""

import json
import time
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

BATCH = 3          # documents can be long: few tests per call
MAX_WORKERS = 3
SOLO_ATTEMPTS = 2  # a test the batch lost is judged on its own, with one retry
SOLO_PAUSE_S = 10


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

        def take(batch: List[dict], replies: List[dict]) -> None:
            want = {b["bundle_id"] for b in batch}
            for j in replies:
                b = by_id.get(str(j.get("bundle_id") or "").strip())
                if b and b["bundle_id"] in want:
                    out[b["bundle_id"]] = ground_judgement(j, b, root)

        batches = [bundles[i:i + BATCH] for i in range(0, len(bundles), BATCH)]
        out: Dict[str, Any] = {}
        errors: Dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(batches))) as pool:
            futures = [(b, pool.submit(ask, b)) for b in batches]
            for batch, fut in futures:
                try:
                    take(batch, fut.result())
                except Exception as exc:
                    for b in batch:
                        errors[b["bundle_id"]] = str(exc)[:200]
        # every test the batches lost — the call failed, or the reply skipped it — is judged on its own
        missing = [b for b in bundles if b["bundle_id"] not in out]
        if missing:
            emit(f"Judging {len(missing)} test(s) one at a time ({'a batch call failed' if errors else 'the judge skipped them'}).",
                 "warning" if errors else "info")

            def solo(b: dict) -> None:
                for attempt in range(SOLO_ATTEMPTS):
                    try:
                        take([b], ask([b]))
                        if b["bundle_id"] in out:
                            errors.pop(b["bundle_id"], None)
                            return
                        errors[b["bundle_id"]] = "the judge returned no judgement for this test"
                    except Exception as exc:
                        errors[b["bundle_id"]] = str(exc)[:200]
                    if attempt + 1 < SOLO_ATTEMPTS:
                        time.sleep(SOLO_PAUSE_S)

            with ThreadPoolExecutor(max_workers=min(2, len(missing))) as pool:
                list(pool.map(solo, missing))
        lost = [b["test_code"] or b["bundle_id"] for b in bundles if b["bundle_id"] not in out]
        if lost:
            emit(f"The judge could not be reached for {len(lost)} test(s) ({', '.join(lost[:8])}); they keep "
                 "deterministic checks only.", "warning")
        reasons = sorted({errors[b["bundle_id"]] for b in bundles if b["bundle_id"] not in out and b["bundle_id"] in errors})
        return out, ("; ".join(reasons) or ("the judge returned no judgement" if lost else None))
