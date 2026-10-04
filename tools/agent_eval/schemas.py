"""
schemas.py — JSON Schemas for Gemini structured output in the agent-evaluation agents.

Passed as `schema=` to tools.agent_eval.llm_json.generate_json. With a schema, Gemini's
structured-output mode guarantees syntactically valid JSON of this shape, which plain
JSON mode does not on long answers (e.g. 30+ test cases with nested quoting).

Every free-text string carries maxLength and every array of scalars maxItems (enforced by Gemini's
response_json_schema), so a confused or manipulated model can't produce unbounded output. Arrays of
objects carry no maxItems (see _list) — the API rejects it there — so callers cap those lists after
parsing (GeminiConnector.generate_json also re-sends once without bounds if a schema is ever rejected). Bounds are set above what callers request (e.g. REQUIREMENTS
allows more items than BrdBuilderAgent keeps) so callers can still detect and report overflow.
"""


def _s(n: int = 500) -> dict:
    return {"type": "string", "maxLength": n}


def _list(items: dict, n: int) -> dict:
    """Array of at most n items. The bound is sent to Gemini only for arrays of scalars: on arrays of OBJECTS
    maxItems makes the API reject the schema (bare 400 INVALID_ARGUMENT, verified on gemini-3.6-flash for
    maxItems >= 20 on TEST_CASES / JUDGE_RESULTS — the constrained-decoding grammar grows with maxItems × object
    size). For those n only documents the intended size; callers cap the parsed list."""
    if items.get("type") == "object":
        return {"type": "array", "items": items}
    return {"type": "array", "items": items, "maxItems": n}


def _sl(n: int = 30, length: int = 300) -> dict:
    return _list(_s(length), n)


_STR = _s(500)
_CODE = _s(40)
_QUOTE = _s(400)
_STR_LIST = _sl()
_PRIORITY = {"type": "string", "enum": ["high", "medium", "low"]}
_VERIFIABILITY = {"type": "string", "enum": ["static", "runtime", "both", "non_technical"]}

AGENT_PROFILE = {
    "type": "object",
    "properties": {
        "agent_name": _s(200),
        "purpose": _s(1500),
        "domain": _s(200),
        "target_users": _STR_LIST,
        "capabilities": _sl(40),
        "out_of_scope": _STR_LIST,
        "tools_and_integrations": _STR_LIST,
        "llm_providers": _sl(10, 100),
        "tech_stack": _sl(30, 100),
        "system_prompt_summary": _s(3000),
        "interface": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["http_api", "web_chat_ui", "cli", "library", "unknown"]},
                "framework": _s(100),
                "endpoints": _list({
                    "type": "object",
                    "properties": {
                        "method": _s(10),
                        "path": _s(300),
                        "description": _STR,
                        "input_field": _s(100),
                        # Free-form example body: serialised as a JSON string because
                        # structured output can't express "any object".
                        "request_body_example_json": _s(3000),
                        "output_field": _s(100),
                    },
                    "required": ["method", "path"],
                }, 60),
                "auth_required": {"type": "boolean"},
                "notes": _s(1500),
            },
            "required": ["type", "endpoints"],
        },
        "entry_points": _sl(20),
        "run_command": _s(300),
        "observed_risks": _sl(20),
    },
    "required": ["purpose", "capabilities", "interface"],
}

BRD_DOCUMENT = {
    "type": "object",
    "properties": {"brd_markdown": _s(120_000)},
    "required": ["brd_markdown"],
}

REQUIREMENTS = {
    "type": "object",
    "properties": {
        "requirements": _list({
            "type": "object",
            "properties": {
                "code": _CODE,
                "title": _s(300),
                "description": _s(1500),
                "priority": _PRIORITY,
                "kind": {"type": "string", "enum": ["functional", "non_functional", "security", "performance",
                                                      "compliance", "ux", "data"]},
                "verifiability": _VERIFIABILITY,
                "section": _s(80),
                "source_quote": _QUOTE,
                "acceptance_criteria": _list({
                    "type": "object",
                    "properties": {
                        "statement": _s(1000),
                        "oracle_hint": {"type": "string", "enum": ["deterministic", "semantic", "static"]},
                        # how THIS criterion can be proven; defaults to the requirement's verifiability
                        "verifiability": _VERIFIABILITY,
                    },
                    "required": ["statement", "oracle_hint"],
                }, 12),
            },
            "required": ["title", "description", "priority", "kind", "verifiability", "source_quote",
                         "acceptance_criteria"],
        }, 60),
    },
    "required": ["requirements"],
}

BRD_SELECTION = {
    "type": "object",
    "properties": {"selected_path": {"type": ["string", "null"], "maxLength": 500}, "reason": _s(800)},
    "required": ["selected_path", "reason"],
}

TEST_CASES = {
    "type": "object",
    "properties": {
        "test_cases": _list({
            "type": "object",
            "properties": {
                "title": _s(200),
                "category": {"type": "string", "enum": ["agent_specific", "general"]},
                "variant_type": {"type": "string", "enum": [
                    "positive", "negative", "edge", "security", "robustness",
                    "out_of_scope", "hallucination", "ambiguity"]},
                "priority": _PRIORITY,
                # how the test is run: through the UI, through the app's HTTP API, or not at runtime at all
                "execution": {"type": "string", "enum": ["ui", "api", "static"]},
                "requirement_ref": {"type": ["string", "null"], "maxLength": 40},
                "criterion_code": _CODE,
                "acceptance_criterion": _s(1000),
                "brd_reference": _QUOTE,
                "area": _s(120),
                "input": _s(4000),
                "expected_behavior": _s(1500),
                "pass_criteria": _sl(6, 300),
            },
            "required": ["title", "category", "variant_type", "priority", "execution", "acceptance_criterion",
                         "brd_reference", "input", "expected_behavior", "pass_criteria"],
        }, 60),
    },
    "required": ["test_cases"],
}

STATIC_REVIEW = {
    "type": "object",
    "properties": {
        "requirements": _list({
            "type": "object",
            "properties": {
                "code": _CODE,
                "status": {"type": "string", "enum": ["implemented", "partial", "missing", "unknown"]},
                "evidence": _s(1500),
            },
            "required": ["code", "status", "evidence"],
        }, 80),
        "quality_checks": _list({
            "type": "object",
            "properties": {"name": _s(120), "score": {"type": "number"}, "note": _s(800)},
            "required": ["name", "score", "note"],
        }, 20),
        "summary": _s(3000),
    },
    "required": ["requirements", "quality_checks", "summary"],
}

_CRITERION_RESULT = {
    "type": "object",
    "properties": {
        "criterion": _s(500),
        "result": {"type": "string", "enum": ["met", "not_met", "cannot_tell"]},
        "quote": _QUOTE,
    },
    "required": ["criterion", "result", "quote"],
}

JUDGE_RESULTS = {
    "type": "object",
    "properties": {
        "results": _list({
            "type": "object",
            "properties": {
                "code": _CODE,
                "verdict": {"type": "string", "enum": ["pass", "fail"]},
                "score": {"type": "integer", "minimum": 0, "maximum": 100},
                "reasoning": _s(800),
                # added (backward compatible): per-criterion results, each "met" with a VERBATIM quote from the
                # reply, plus the single most decisive quote. live_agent_execution verifies quotes on passes.
                "criteria_results": _list(_CRITERION_RESULT, 10),
                "quote": _QUOTE,
            },
            "required": ["code", "verdict", "score", "reasoning", "criteria_results", "quote"],
        }, 40),
    },
    "required": ["results"],
}

# ── MTA redesign: traceability ────────────────────────────────────────────────

QUERY_TERMS = {
    "type": "object",
    "properties": {
        "criteria": _list({"type": "object", "properties": {"code": _CODE, "terms": _sl(20, 80)},
                           "required": ["code", "terms"]}, 40),
    },
    "required": ["criteria"],
}

VERIFIER = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["implemented", "partial", "not_implemented", "insufficient_evidence"]},
        "rationale": _s(2000),
        "citations": _list({
            "type": "object",
            "properties": {"file": _s(300), "start_line": {"type": "integer"}, "end_line": {"type": "integer"},
                           "symbol": _s(200), "claim": _s(600)},
            "required": ["file", "start_line", "end_line", "claim"],
        }, 12),
        "looked_for": _sl(12, 200),
        "need_more": _sl(8, 200),
    },
    "required": ["status", "rationale", "citations", "looked_for", "need_more"],
}

REVIEW_FINDINGS = {
    "type": "object",
    "properties": {
        "findings": _list({
            "type": "object",
            "properties": {
                "dimension": {"type": "string", "enum": ["architecture", "security", "agent_design", "workflow",
                                                         "performance", "production_readiness"]},
                "severity": {"type": "string", "enum": ["critical", "high", "medium", "low", "info"]},
                "title": _s(200), "file": _s(300), "start_line": {"type": "integer"}, "end_line": {"type": "integer"},
                "rationale": _s(1500), "fix": _s(1500),
            },
            "required": ["dimension", "severity", "title", "file", "start_line", "rationale", "fix"],
        }, 30),
    },
    "required": ["findings"],
}

ACTION_PROPOSALS = {
    "type": "object",
    "properties": {
        "plans": _list({
            "type": "object",
            "properties": {
                "test_code": _CODE,
                "applicable": {"type": "boolean"},
                "reason": _s(800),
                "steps": _list({
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": [
                            "fill", "select", "check", "upload", "click", "send_message", "expect_download"]},
                        "element_id": _s(80),
                        "value": {"type": ["string", "null"], "maxLength": 6000},
                    },
                    "required": ["action", "element_id"],
                }, 200),
            },
            "required": ["test_code", "applicable", "steps"],
        }, 40),
    },
    "required": ["plans"],
}

OUTPUT_JUDGEMENTS = {
    "type": "object",
    "properties": {
        "judgements": _list({
            "type": "object",
            "properties": {
                "bundle_id": _s(80),
                "criteria_results": _list(_CRITERION_RESULT, 10),
                "assessment": {"type": "string", "enum": ["meets", "partially_meets", "does_not_meet", "cannot_tell"]},
                "score": {"type": "integer", "minimum": 0, "maximum": 100},
                "reasoning": _s(800),
            },
            "required": ["bundle_id", "criteria_results", "assessment", "score", "reasoning"],
        }, 20),
    },
    "required": ["judgements"],
}
