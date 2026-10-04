"""
LiveAgentExecutionAgent — fallback runner for chat / API apps.

1. Connect: auto-detect a JSON endpoint (repo-declared routes first, then common
   routes), falling back to driving a web chat UI with Playwright.
2. Send each test's input and capture the reply + latency (HTTP: 4 in parallel;
   browser: sequential, fresh page per test).
3. Judge replies with Gemini in batches against expected behaviour / pass criteria. A "pass" must quote the reply:
   quotes are checked against the actual reply text, and a pass with no verified quote is inconclusive.

Fallback role — it never overrides the browser workflow (Runtime Discovery → … → Pass/Fail):
  * it only takes tests the workflow did not execute for a reason a chat/API call can fix (no UI mapping, no element
    found) — never tests blocked by login, budget or cancellation — and only for apps reachable that way
    (Chatbot, REST API, Hybrid with a chat component, unknown);
  * when it cannot connect, the tests keep the precise reason the workflow recorded; nothing is overwritten;
  * when the workflow produced no verdicts at all (e.g. runtime discovery failed) and the app is not a chat/API app,
    each still-pending test is marked not executed with the reason the chain broke, instead of a generic message.
Results are appended to the Pass/Fail results, so no test is sent twice.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

from agents.base_agent import BaseAgent
from agents.test_execution.live_agent_execution.prompt import JUDGE_PROMPT
from agents.test_execution.live_agent_execution.skills import SKILLS
from agents.test_execution.live_agent_execution.tools import (
    JUDGE_RESULTS,
    AgentResponse,
    NoAgentInterface,
    connect_live_agent,
    generate_json,
)
from connectors.connector_registry import ConnectorRegistry
from tools.agent_eval.net_guard import BlockedTarget
from tools.agent_eval.untrusted import neutralise
from tools.shared import get_logger

JUDGE_BATCH = 6
HTTP_WORKERS = 4
PASS_THRESHOLD = 70
FALLBACK_APP_TYPES = {"Chatbot", "REST API", "Hybrid Application", "Unknown", None}
# reasons a chat/API call cannot fix: retrying them through the fallback would only repeat the failure
_NOT_RETRYABLE = re.compile(r"login|test account|budget|cancel|not deployed|private or internal|behind a login", re.I)


class LiveAgentExecutionAgent(BaseAgent):
    MODULE_NAME = "live_agent_execution"

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self._registry = ConnectorRegistry(self.settings)
        self.logger = get_logger("agent.live_agent_execution")

    def execute(self, request: dict, state: dict) -> Dict[str, Any]:
        emit = request.get("emit") or (lambda *a, **k: None)
        update: Callable[[str, Dict[str, Any]], None] = request.get("on_test_update") or (lambda *a, **k: None)
        tests: List[dict] = [t for t in request.get("test_cases") or [] if t.get("id")]
        prior: List[dict] = request.get("execution_results") or []
        if not tests:
            return {"module": self.MODULE_NAME, "status": "skipped", "reason": "no runtime tests", "execution_results": prior}
        if request.get("mode") == "brd_only" or not (request.get("live_url") or "").strip():
            for t in tests:
                update(t["id"], {"status": "not_executed", "errorSummary": "Not executed: the app is not deployed."})
            return {"module": self.MODULE_NAME, "status": "skipped", "reason": "not deployed",
                    "live_reachable": False, "execution_results": prior}

        reachable = _fallback_capable(request)
        if request.get("pass_fail") is None:
            # the browser workflow produced no verdicts: say why, per test, unless a chat/API call can still run them
            if not reachable:
                why = _chain_break_reason(request)
                for t in tests:
                    update(t["id"], {"status": "not_executed", "errorSummary": f"Not executed: {why}"[:1000]})
                emit(f"{len(tests)} runtime test(s) could not run: {why}", "warning")
                return {"module": self.MODULE_NAME, "status": "skipped", "reason": why, "execution_results": prior}
            remaining = tests
        else:
            retry = {r["id"] for r in prior if r.get("status") == "not_executed"
                     and not _NOT_RETRYABLE.search(str(r.get("error_summary") or r.get("judge_reasoning") or ""))}
            remaining = [t for t in tests if t["id"] in retry] if reachable else []
            if not remaining:
                reason = ("superseded by the browser workflow (Pass/Fail Engine)" if not retry else
                          f"the {len(retry)} test(s) the browser workflow could not run are not reachable through a chat "
                          "or API interface either")
                return {"module": self.MODULE_NAME, "status": "skipped", "reason": reason, "execution_results": prior}
        emit(f"Fallback: trying {len(remaining)} test(s) through the app's chat/API interface.")
        result = self._run(request, remaining, mark_unrun=request.get("pass_fail") is None)
        ids = {r["id"] for r in result.get("execution_results") or []}
        result["execution_results"] = [r for r in prior if r["id"] not in ids] + (result.get("execution_results") or [])
        if any(r.get("status") in ("passed", "failed") for r in prior):
            result.update(live_reachable=True, live_status="connected")
        return result

    def _run(self, request: dict, tests: List[dict], mark_unrun: bool = True) -> Dict[str, Any]:
        emit = request.get("emit") or (lambda *a, **k: None)
        update: Callable[[str, Dict[str, Any]], None] = request.get("on_test_update") or (lambda *a, **k: None)
        live_url = (request.get("live_url") or "").strip()
        interface = (request.get("agent_profile") or {}).get("interface") or {}
        emit(f"Connecting to {live_url} …")
        try:
            client = connect_live_agent(live_url, interface, log=emit)
        except (NoAgentInterface, BlockedTarget) as exc:
            # the site is up but offers no message interface (or is not allowed): the tests keep the reasons the
            # browser workflow recorded — nothing is overwritten
            error = str(exc)
            emit(error, "warning")
            if mark_unrun:
                self._mark_unrun(tests, update, f"no chat box or message API to send it through ({error[:200]})")
            return {"module": self.MODULE_NAME, "status": "partial", "error": error, "live_status": "no_interface",
                    "live_error": error, "execution_results": []}
        except Exception as exc:  # LiveAgentUnreachable, browser failures, …
            error = str(exc)
            emit(error, "error")
            if mark_unrun:
                self._mark_unrun(tests, update, f"the live app did not respond ({error[:200]})")
            return {"module": self.MODULE_NAME, "status": "partial", "error": error, "live_status": "unreachable",
                    "live_error": error, "execution_results": []}

        emit(f"Connected via {client.describe()}. Running {len(tests)} tests.", "success")
        try:
            responses = self._collect(client, tests, emit, update)
        finally:
            client.close()

        results = self._judge(tests, responses, request.get("agent_profile") or {}, request.get("connector_mode"), emit, update)
        passed = sum(1 for r in results if r["status"] == "passed")
        emit(f"Fallback finished: {passed}/{len(results)} tests passed.", "success" if passed == len(results) else "warning")
        return {
            "module": self.MODULE_NAME,
            "status": "success",
            "live_reachable": True,
            "live_status": "connected",
            "transport": client.kind,
            "connection_detail": client.describe(),
            "execution_results": results,
        }

    @staticmethod
    def _mark_unrun(tests: List[dict], update, why: str) -> None:
        """Only tests nobody has run yet get a reason; tests the workflow already explained keep theirs."""
        for t in tests:
            if t.get("status") in (None, "pending"):
                update(t["id"], {"status": "not_executed", "errorSummary": f"Not executed: {why}"[:1000]})

    # ── 1. send prompts ──────────────────────────────────────────────────────

    def _collect(self, client, tests: List[dict], emit, update) -> Dict[str, AgentResponse]:
        responses: Dict[str, AgentResponse] = {}

        def record(t: dict, resp: AgentResponse) -> None:
            responses[t["id"]] = resp
            update(t["id"], {
                "actualOutput": (resp.text or "")[:20_000] or None,
                "durationMs": resp.latency_ms,
                "errorSummary": resp.error,
            })
            if resp.ok:
                emit(f"{t['code']} answered in {resp.latency_ms / 1000:.1f}s")
            else:
                emit(f"{t['code']} got no usable reply: {resp.error}", "warning")

        if client.kind == "http":
            with ThreadPoolExecutor(max_workers=HTTP_WORKERS) as pool:
                futures = {pool.submit(client.send, t["input"]): t for t in tests}
                for fut in as_completed(futures):
                    t = futures[fut]
                    try:
                        record(t, fut.result())
                    except Exception as exc:
                        record(t, AgentResponse(ok=False, error=f"{type(exc).__name__}: {exc}"))
        else:  # Playwright objects are bound to the thread that created them
            for t in tests:
                record(t, client.send(t["input"]))
        return responses

    # ── 2. judge replies ─────────────────────────────────────────────────────

    def _judge(self, tests, responses, profile, connector_mode, emit, update) -> List[Dict[str, Any]]:
        llm = self._registry.get_llm(connector_mode)
        agent_summary = json.dumps({k: profile.get(k) for k in ("agent_name", "purpose", "capabilities", "out_of_scope")},
                                   ensure_ascii=False)
        results: Dict[str, Dict[str, Any]] = {}

        answered = [t for t in tests if responses.get(t["id"]) and responses[t["id"]].ok]
        for t in tests:
            resp = responses.get(t["id"])
            if not resp or not resp.ok:
                results[t["id"]] = self._finish(t, resp, "failed", 0,
                                                f"No usable reply from the app: {resp.error if resp else 'not sent'}",
                                                transport_error=True, update=update)

        for start in range(0, len(answered), JUDGE_BATCH):
            batch = answered[start:start + JUDGE_BATCH]
            payload = [{
                "code": t["code"], "category": t["category"], "variant_type": t["variant_type"],
                "brd_reference": t.get("brd_reference"), "acceptance_criterion": t.get("acceptance_criterion"),
                "input": t["input"], "expected_behavior": t["expected_behavior"],
                "pass_criteria": t.get("pass_criteria") or [],
                "actual_reply": responses[t["id"]].text[:6000],
            } for t in batch]
            prompt = JUDGE_PROMPT.substitute(
                skill_header=SKILLS["response_judging"].header(),
                agent_summary=neutralise(agent_summary),
                tests=neutralise(json.dumps(payload, indent=2, ensure_ascii=False)),
            )
            try:
                verdicts = {str(v.get("code")).upper(): v for v in
                            generate_json(llm, prompt, required_keys=["results"], schema=JUDGE_RESULTS).get("results") or []
                            if isinstance(v, dict)}
            except Exception as exc:
                emit(f"Judge call failed for {', '.join(t['code'] for t in batch)}: {exc}", "warning")
                verdicts = {}

            for t in batch:
                v = verdicts.get(t["code"])
                reply = responses[t["id"]].text or ""
                if not v:
                    results[t["id"]] = self._finish(t, responses[t["id"]], "inconclusive", None,
                                                    "The reply could not be judged (the judge was unavailable).", update=update)
                    continue
                try:
                    score = max(0, min(100, int(round(float(v.get("score", 0))))))
                except (TypeError, ValueError):
                    score = 0
                verdict = str(v.get("verdict") or "").lower()
                reasoning = str(v.get("reasoning") or "").strip()
                status = "passed" if verdict == "pass" and score >= PASS_THRESHOLD else "failed"
                if status == "passed":
                    quotes = _quotes(v)
                    verified = [q for q in quotes if _in_reply(q, reply)]
                    if not verified:  # a pass must point at the reply; the app's own text cannot vouch for itself
                        status, score = "inconclusive", None
                        reasoning = ("The judge said pass but quoted nothing that appears in the reply, so the result "
                                     "is not counted. " + reasoning)
                results[t["id"]] = self._finish(t, responses[t["id"]], status, score, reasoning, update=update)
            emit(f"Judged {min(start + JUDGE_BATCH, len(answered))}/{len(answered)} replies.")

        return [results[t["id"]] for t in tests if t["id"] in results]

    @staticmethod
    def _finish(t, resp: Optional[AgentResponse], status: str, score: Optional[int], reasoning: str,
                transport_error: bool = False, update=None) -> Dict[str, Any]:
        fields = {"status": status, "judgeScore": score, "judgeReasoning": reasoning[:4000] or None}
        if status == "inconclusive":
            fields["errorSummary"] = f"Inconclusive: {reasoning}"[:1000]
        if update:
            update(t["id"], fields)
        return {
            "id": t["id"], "code": t["code"], "status": status, "judge_score": score,
            "judge_reasoning": reasoning, "duration_ms": resp.latency_ms if resp else 0,
            "actual_output": resp.text if resp else None, "error_summary": resp.error if resp else None,
            "transport_error": transport_error, "source": "live_fallback",
        }


def _fallback_capable(request: dict) -> bool:
    c = request.get("app_classification") or {}
    if c.get("app_type") in FALLBACK_APP_TYPES:
        return True
    return "Chatbot" in (c.get("components") or []) or "REST API" in (c.get("components") or [])


def _chain_break_reason(request: dict) -> str:
    failures = {f["step"]: f["error"] for f in request.get("step_failures") or []}
    for step, label in (("runtime_discovery", "inspecting the live app failed"),
                        ("action_generation", "browser actions could not be generated"),
                        ("playwright_executor", "the browser run failed"),
                        ("evidence_collection", "collecting the evidence failed"),
                        ("output_validation", "validating the outputs failed"),
                        ("pass_fail", "deciding the verdicts failed")):
        if step in failures:
            return f"{label} ({failures[step][:200]})"
    if not request.get("runtime_profile"):
        return "the live app could not be inspected in a browser (see Runtime discovery)"
    if request.get("execution_error"):
        return request["execution_error"]
    plan = request.get("action_plan") or {}
    if plan.get("status") == "blocked":
        return plan.get("reason") or "the action plan was blocked"
    return "the browser workflow produced no verdicts for this test"


def _quotes(v: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for key in ("quote", "quotes", "evidence_quote"):
        val = v.get(key)
        if isinstance(val, str):
            out.append(val)
        elif isinstance(val, list):
            out += [q for q in val if isinstance(q, str)]
    for c in v.get("criteria_results") or []:
        if isinstance(c, dict) and isinstance(c.get("quote"), str):
            out.append(c["quote"])
    return [q.strip() for q in out if q and len(q.strip()) >= 4]


def _in_reply(quote: str, reply: str) -> bool:
    norm = lambda x: re.sub(r"\s+", " ", x).strip().lower()  # noqa: E731
    return norm(quote)[:300] in norm(reply)
