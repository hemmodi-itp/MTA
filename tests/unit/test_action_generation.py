"""Unit tests for the Action Generation Engine (engines/runtime/actions.py) — no browser, no LLM."""

from engines.runtime.actions import build_inventory, generate_action_plan, validate_steps
from engines.runtime.classification import classify
from engines.runtime.discovery import _profile, _summarise_page
from tests.unit.test_runtime_discovery import _field, _raw


def _docgen_profile(logged_in=False):
    fields = [_field("Project name", required=True), _field("Problem statement", "textarea", required=True),
              _field("Audience", "select", required=True), _field("Notes", "textarea")]
    fields[2]["options"] = ["Select…", "Executives", "Engineers"]
    form = {"kind": "virtual", "action": "", "method": "", "buttons": ["Generate documents"], "fields": fields}
    page = _summarise_page(_raw("/new", inputs=fields, forms=[form], buttons=["Generate documents", "Download DOCX"]))
    prof = _profile("https://app.example.com/", [page], [], ["POST /api/generate"], 1.0)
    if logged_in:
        prof["login"] = {"attempted": True, "succeeded": True}
    return prof


def _test(code="TC-001", variant="positive", text="A clinic needs online appointment booking"):
    return {"id": f"db-{code}", "code": code, "title": "Generates a BRD from the problem statement", "variant_type": variant,
            "input": text, "expected_behavior": "A BRD document is produced covering the problem",
            "pass_criteria": ["document generated"], "criterion_code": "AC-01.1", "requirement_ref": "REQ-01"}


def _actions(plan):
    return [s["action"] for s in plan["steps"]]


def test_document_generator_rules_plan_is_complete_and_grounded():
    prof = _docgen_profile(logged_in=True)
    plan = generate_action_plan(classify(prof), prof, [_test()])
    p = plan["plans"][0]
    assert plan["status"] == "ready" and p["status"] == "ready" and p["source"] == "rules"
    assert _actions(p)[:2] == ["login", "goto"]
    fills = {s["target"]["label"]: s.get("value") for s in p["steps"] if s["action"] in ("fill", "select")}
    assert fills["Problem statement"] == "A clinic needs online appointment booking"  # test input in the matching field
    assert fills["Project name"] and fills["Audience"] == "Executives"                  # required fields completed
    assert "Notes" not in fills                                                         # optional field left alone
    acts = _actions(p)
    assert acts.index("click") < acts.index("wait_for") < acts.index("expect_download") < acts.index("capture")
    assert p["steps"][-1]["action"] == "assert" and p["steps"][-1]["kind"] == "judge"
    assert p["criterion_code"] == "AC-01.1" and p["test_id"] == "db-TC-001"
    wait = next(s for s in p["steps"] if s["action"] == "wait_for")
    assert wait["timeout_ms"] >= 120_000  # document generation is slow


def test_negative_test_does_not_autofill_required_fields_or_expect_download():
    prof = _docgen_profile()
    p = generate_action_plan(classify(prof), prof, [_test(variant="negative", text="")])["plans"][0]
    assert not any(s.get("synthetic") for s in p["steps"])
    assert "expect_download" not in _actions(p) and "click" in _actions(p)


def test_llm_proposal_validated_against_inventory():
    prof = _docgen_profile()
    inv = build_inventory(prof)
    ids = {e.get("label") or e.get("text"): e["id"] for e in inv["elements"].values()}
    raw = [{"action": "fill", "element_id": ids["Project name"], "value": "Clinic booking"},
           {"action": "fill", "element_id": ids["Problem statement"], "value": "Patients cannot book online"},
           {"action": "select", "element_id": ids["Audience"], "value": "Martians"},   # not an option → dropped
           {"action": "click", "element_id": "P9B9"},                                   # invented id → dropped
           {"action": "fill", "element_id": ids["Generate documents"], "value": "x"}]  # fill on a button → dropped
    steps, dropped = validate_steps(raw, inv)
    assert dropped == 3 and [s["action"] for s in steps] == ["fill", "fill"]
    plan = generate_action_plan(classify(prof), prof, [_test()], proposals={"TC-001": {"applicable": True, "steps": raw}})
    p = plan["plans"][0]
    assert p["source"] == "llm" and plan["counts"]["ungrounded_steps_dropped"] == 3
    audience = next(s for s in p["steps"] if s.get("target", {}).get("label") == "Audience")
    assert audience["value"] == "Executives" and audience["synthetic"]  # the bad select was replaced by valid data


def test_llm_inapplicable_test_is_reported_not_faked():
    prof = _docgen_profile()
    plan = generate_action_plan(classify(prof), prof, [_test()],
                                proposals={"TC-001": {"applicable": False, "reason": "latency claim", "steps": []}})
    assert plan["plans"][0]["status"] == "unmappable" and plan["plans"][0]["reason"] == "latency claim"


def test_chatbot_plan_sends_the_message_and_captures_reply():
    box = _field("Type your message", "textarea")
    page = _summarise_page(_raw("/", inputs=[box], buttons=["Send"], logs=1, text="Chat with the assistant",
                                forms=[{"kind": "virtual", "action": "", "method": "", "buttons": ["Send"], "fields": [box]}]))
    prof = _profile("https://bot.example.com/", [page], [], [], 1.0)
    plan = generate_action_plan(classify(prof), prof, [_test(text="What are your opening hours?")])
    p = plan["plans"][0]
    send = next(s for s in p["steps"] if s["action"] == "send_message")
    assert send["value"] == "What are your opening hours?"
    assert "reply" in next(s for s in p["steps"] if s["action"] == "capture")["what"]
    assert any(f["kind"] == "flow_check" and not f["scored"] for f in plan["plans"])


def test_behind_login_without_account_is_blocked_with_reason():
    fields = [_field("Email", "email"), _field("Password", "password")]
    login = _summarise_page(_raw("/login", inputs=fields, password=1, buttons=["Log in"],
                                 forms=[{"kind": "form", "action": "", "method": "post", "buttons": ["Log in"], "fields": fields}]))
    prof = _profile("https://app.example.com/", [login], [], [], 1.0, gated=["/new"])
    prof["needs_credentials"] = True
    plan = generate_action_plan({"app_type": "Document Generator", "components": []}, prof, [_test()])
    assert plan["status"] == "blocked" and "test account" in plan["reason"] and plan["counts"]["blocked"] == 1


def test_rest_api_uses_documented_endpoint():
    plan = generate_action_plan({"app_type": "REST API", "components": []}, {"pages": []}, [_test(text="hi")],
                                endpoints=[{"method": "POST", "path": "/chat", "input_field": "query"}])
    p = plan["plans"][0]
    assert p["steps"][0] == {"action": "http", "method": "POST", "path": "/chat", "body": {"query": "hi"},
                             "expect_status": "2xx", "n": 1}
    assert "login" not in _actions(p)


def test_login_page_elements_never_enter_the_inventory():
    fields = [_field("Email", "email"), _field("Password", "password")]
    login = _summarise_page(_raw("/login", inputs=fields, password=1, buttons=["Log in"],
                                 forms=[{"kind": "form", "action": "", "method": "post", "buttons": ["Log in"], "fields": fields}]))
    inv = build_inventory(_profile("https://x/", [login], [], [], 1.0))
    assert not inv["elements"]


def test_log_out_and_destructive_controls_never_enter_the_inventory():
    page = _summarise_page(_raw("/new", buttons=["Log out", "Sign out", "Generate", "Delete account"]))
    inv = build_inventory(_profile("https://x/", [page], [], [], 1.0))
    assert sorted(e["text"] for e in inv["elements"].values() if e["kind"] == "button") == ["Generate"]


def _brd_agent_like(demo=True):
    fields = [_field("Project Name (required)"), _field("Problem Statement (required)", "textarea"),
              _field("Doc ID Acronym (required)"), _field("Tech Stack Preferences (required)", "textarea"),
              _field("Data Flow Steps (required)", "textarea"), _field("Constraints", "textarea")]
    form = {"kind": "virtual", "action": "", "method": "", "buttons": ["Generate Documents"], "fields": fields}
    new = _summarise_page(_raw("/new", inputs=fields, forms=[form],
                               buttons=["Log out"] + (["Fill Demo Data"] if demo else []) + ["Generate Documents"]))
    hist = _summarise_page(_raw("/history", buttons=["Log out"]))
    prof = _profile("https://app.example.com/", [new, hist], [], ["POST /api/generate"], 1.0)
    prof["login"] = {"attempted": True, "succeeded": True}
    return prof, {"app_type": "Document Generator", "components": []}


def test_label_only_required_fields_are_completed_with_sensible_data():
    prof, cls = _brd_agent_like(demo=False)
    p = generate_action_plan(cls, prof, [_test(text="Clinics cannot book online")])["plans"][0]
    filled = {s["target"]["label"]: s.get("value") for s in p["steps"] if s["action"] == "fill"}
    assert set(filled) >= {"Project Name (required)", "Problem Statement (required)", "Doc ID Acronym (required)",
                           "Tech Stack Preferences (required)", "Data Flow Steps (required)"}
    assert "Constraints" not in filled                                  # optional stays empty
    assert filled["Doc ID Acronym (required)"] == "MTA" and "Python" in filled["Tech Stack Preferences (required)"]
    assert filled["Data Flow Steps (required)"].startswith("1.")
    assert not any("(required)" in (v or "").lower() for v in filled.values())


def test_generate_then_act_for_export_revise_and_history():
    prof, cls = _brd_agent_like()
    proposals = {c: {"applicable": False, "reason": "No UI elements exist for that", "steps": []} for c in ("TC-008", "TC-010", "TC-016")}
    tests = [
        {"id": "a", "code": "TC-008", "title": "DOCX Export with Embedded Diagram Images", "variant_type": "positive",
         "input": "GET /api/runs/run-101/export/docx?document=tsd", "expected_behavior": "A DOCX with diagrams"},
        {"id": "b", "code": "TC-010", "title": "Non-Destructive Revision via Free-Text Change Request", "variant_type": "positive",
         "input": 'POST /api/runs/run-101/revise {"change_request": "Change the primary database to MySQL"}',
         "expected_behavior": "A new revision; the original is kept"},
        {"id": "c", "code": "TC-016", "title": "Listing Historical Run Versions", "variant_type": "positive",
         "input": "GET /api/runs", "expected_behavior": "Past runs are listed"},
    ]
    plans = {p["test_code"]: p for p in generate_action_plan(cls, prof, tests, proposals=proposals)["plans"]}
    exp = [s["action"] for s in plans["TC-008"]["steps"]]
    assert plans["TC-008"]["status"] == "ready" and exp.index("click") < exp.index("wait_for") < exp.index("expect_download")
    rev = plans["TC-010"]["steps"]
    fu = next(s for s in rev if s["action"] == "follow_up")
    assert fu["value"] == "Change the primary database to MySQL" and "phase" not in fu
    acts = [s["action"] for s in rev]
    assert acts.index("click") < acts.index("follow_up") and acts[acts.index("follow_up") + 1] == "wait_for"
    hist = [s for s in plans["TC-016"]["steps"] if s["action"] == "goto"]
    assert [s["url"] for s in hist] == ["/new", "/history"]
    neg = generate_action_plan(cls, prof, [{**tests[0], "variant_type": "negative"}], proposals={"TC-008": proposals["TC-008"]})
    assert neg["plans"][0]["status"] == "unmappable"                    # negative tests are never re-mapped


def test_login_failure_is_reported_as_such_not_as_missing_account():
    prof, cls = _brd_agent_like()
    prof.update(needs_credentials=True, login={"attempted": True, "succeeded": False, "error": "no login form found"})
    plan = generate_action_plan(cls, prof, [_test()], has_credentials=True)
    assert plan["status"] == "blocked" and "Login with the test account failed (no login form found)" in plan["reason"]


def test_demo_data_button_is_used_first_and_test_values_overwrite_it():
    prof, cls = _brd_agent_like(demo=True)
    p = generate_action_plan(cls, prof, [_test(text="Clinics cannot book online")])["plans"][0]
    acts = [(s["action"], (s.get("target") or {}).get("text") or (s.get("target") or {}).get("label")) for s in p["steps"]]
    assert acts[2] == ("click", "Fill Demo Data")
    assert ("fill", "Problem Statement (required)") in acts                 # the test's own value overwrites demo data
    assert not any(s.get("synthetic") and s["action"] == "fill" for s in p["steps"])   # no filler on top of demo data
    neg = generate_action_plan(cls, prof, [_test(variant="negative", text="")])["plans"][0]
    assert not any(s.get("purpose") == "prefill demo data" for s in neg["steps"])   # negative tests stay incomplete


def test_item_pages_never_supply_targets_and_full_form_plans_skip_demo():
    prof, cls = _brd_agent_like(demo=True)
    old = _summarise_page(_raw("/runs/20261001-153029-6d7697", buttons=["Download DOCX", "Apply Change"],
                               inputs=[_field("e.g. Add a risk", "textarea")],
                               forms=[{"kind": "virtual", "action": "", "method": "", "buttons": ["Apply Change"],
                                       "fields": [_field("e.g. Add a risk", "textarea")]}]))
    prof["pages"].append(old)
    inv = build_inventory(prof)
    assert all(not e["page"].startswith("/runs/") for e in inv["elements"].values())
    ids = {e["label"]: e["id"] for e in inv["elements"].values() if e["kind"] == "field"}
    full = {"TC-001": {"applicable": True, "steps": [{"action": "fill", "element_id": i, "value": f"Clinic {n}"} for n, i in ids.items()]}}
    p = generate_action_plan(cls, prof, [_test()], proposals=full)["plans"][0]
    assert not any(s.get("purpose") == "prefill demo data" for s in p["steps"])   # the whole form tells one story
    partial = generate_action_plan(cls, prof, [_test()])["plans"][0]
    demo = next(s for s in partial["steps"] if s.get("purpose") == "prefill demo data")
    assert demo["optional"] is True                                               # skipped, not failed, if absent
