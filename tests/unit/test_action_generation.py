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
    assert fills["Notes"]                                                # a generating form is submitted complete
    dl = next(s for s in p["steps"] if s["action"] == "expect_download")
    assert dl["optional"] is True                    # the test is about the content, not the file: files are evidence
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


def test_a_test_the_model_declined_still_runs_marked_as_an_approximation():
    # every generated test runs: the closest action the app offers, never "not testable"; the proxy note tells the judge
    # and Pass/Fail (a shortfall is then not held against the app)
    prof = _docgen_profile()
    plan = generate_action_plan(classify(prof), prof, [_test()],
                                proposals={"TC-001": {"applicable": False, "reason": "latency claim", "steps": []}})
    p = plan["plans"][0]
    assert p["status"] == "ready" and p["proxy"].startswith("latency claim") and plan["counts"]["proxy"] == 1
    acts = _actions(p)
    assert "fill" in acts and acts.index("click") < acts.index("wait_for")     # the form is filled and submitted


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
    assert filled["Constraints"] == "Must run on the team's existing cloud account."  # a generating form: complete
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
    np_ = neg["plans"][0]
    assert np_["status"] == "ready" and np_["proxy"] and np_["variant"] == "negative"  # runs, as its closest equivalent
    assert not any(s.get("synthetic") for s in np_["steps"])            # still a negative submission


def test_login_failure_is_reported_as_such_not_as_missing_account():
    prof, cls = _brd_agent_like()
    prof.update(needs_credentials=True, login={"attempted": True, "succeeded": False, "error": "no login form found"})
    plan = generate_action_plan(cls, prof, [_test()], has_credentials=True)
    assert plan["status"] == "blocked" and "Login with the test account failed (no login form found)" in plan["reason"]


def test_mta_fills_required_fields_itself_and_demo_data_is_only_a_fallback():
    # BRD_Agent's "Fill Demo Data" project ran past the app's 180 s request timeout every time: MTA's own short values now
    # complete the required fields (an app wanting more names them; the executor fills those), so a feature test is not
    # turned into a timeout
    prof, cls = _brd_agent_like(demo=True)
    p = generate_action_plan(cls, prof, [_test(text="Clinics cannot book online")])["plans"][0]
    acts = [(s["action"], (s.get("target") or {}).get("text") or (s.get("target") or {}).get("label")) for s in p["steps"]]
    assert not any(s.get("purpose") == "prefill demo data" for s in p["steps"])
    filled = {label for act, label in acts if act == "fill"}
    assert {"Problem Statement (required)", "Data Flow Steps (required)", "Constraints"} <= filled
    assert next(s for s in p["steps"] if (s.get("target") or {}).get("label") == "Problem Statement (required)")["value"] ==         "Clinics cannot book online"                                                     # the test's own value
    neg = generate_action_plan(cls, prof, [_test(variant="negative", text="")])["plans"][0]
    assert not any(s.get("purpose") == "prefill demo data" or s.get("synthetic") for s in neg["steps"])  # stays incomplete

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
    assert not any(s.get("purpose") == "prefill demo data" for s in partial["steps"])  # MTA fills required fields itself
    pw = {**prof, "pages": [dict(pg, forms=[dict(f, fields=[dict(x, type="password") if x.get("required") else x
                                                            for x in f["fields"]]) for f in pg.get("forms") or []])
                            for pg in prof["pages"]]}
    fallback = generate_action_plan(cls, pw, [_test()])["plans"][0]   # no required field MTA can fill: the app's demo data
    demo = next(s for s in fallback["steps"] if s.get("purpose") == "prefill demo data")
    assert demo["optional"] is True                                               # skipped, not failed, if absent


def test_steps_on_another_page_run_after_the_result_and_flow_checks_fit_the_form():
    prof = {"login": {"succeeded": True}, "pages": [
        {"path": "/new", "forms": [{"fields": [{"label": "Project", "type": "text", "required": True},
                                               {"label": "Problem", "type": "textarea"}],
                                    "submit_button": "Generate Documents", "buttons": ["Generate Documents"]}],
         "buttons": ["Generate Documents"]},
        {"path": "/history", "forms": [{"fields": [{"label": "Search history...", "type": "text"}],
                                        "submit_button": None, "buttons": []}], "buttons": []}]}
    inv = build_inventory(prof)
    ids = {e.get("label") or e.get("text"): e["id"] for e in inv["elements"].values()}
    test = {"id": "t", "code": "TC-019", "title": "Revision keeps history", "variant_type": "positive", "input": "x",
            "expected_behavior": "Both runs are listed"}
    prop = {"TC-019": {"applicable": True, "steps": [
        {"action": "fill", "element_id": ids["Project"], "value": "Order Tracker"},
        {"action": "fill", "element_id": ids["Problem"], "value": "Slow tracking"},
        {"action": "fill", "element_id": ids["Search history..."], "value": "Order Tracker"},
        {"action": "click", "element_id": ids["Generate Documents"]},
        {"action": "click", "element_id": ids["Generate Documents"]}]}}
    plan = generate_action_plan({"app_type": "Document Generator", "components": []}, prof, [test], proposals=prop,
                                has_credentials=True)
    steps = [(s["action"], s.get("url") or (s.get("target") or {}).get("label") or (s.get("target") or {}).get("text"))
             for s in plan["plans"][0]["steps"]]
    gen = steps.index(("click", "Generate Documents"))
    assert steps.count(("click", "Generate Documents")) == 1                       # the doubled submit is dropped
    assert steps[1] == ("goto", "/new") and steps.index(("fill", "Project")) < gen
    assert steps.index(("wait_for", None)) < steps.index(("goto", "/history")) < steps.index(("fill", "Search history..."))
    flow = next(p for p in plan["plans"] if p["plan_id"].startswith("AP-FLOW") and p["steps"][1].get("url") == "/history")
    assert not any(s["action"] == "expect_download" for s in flow["steps"])   # a search box generates no file


def _with_na_box(prof):
    """Give the BRD_Agent-like form a per-field "Not applicable" box on Constraints (as on the real app)."""
    form = next(p for p in prof["pages"] if p["path"] == "/new")["forms"][0]
    form["fields"].append({"label": "Not applicable — omit this section", "name": "", "tag": "input", "type": "checkbox",
                           "required": False, "readonly": False, "options": None, "group": "Constraints"})
    form["fields"].append({"label": "Not applicable — omit this section", "name": "", "tag": "input", "type": "checkbox",
                           "required": False, "readonly": False, "options": None, "group": "Other"})
    return prof


def test_label_value_input_lines_fill_their_fields_and_an_omitted_field_is_left_alone():
    prof, cls = _brd_agent_like()
    prof = _with_na_box(prof)
    text = ("Scenario: Mark Constraints section as Not Applicable.\nProject Name: BRD Agent Suite\n"
            "Problem Statement: Manual authoring causes misalignment.\nConstraints: [Checked Not applicable — omit this section]\n"
            "Tech Stack Preferences: Python FastAPI, Gemini API.")
    p = generate_action_plan(cls, prof, [_test(text=text)])["plans"][0]
    by = [(s["action"], (s.get("target") or {}).get("label"), (s.get("target") or {}).get("group"), s.get("value")) for s in p["steps"]]
    assert ("fill", "Project Name (required)", None, "BRD Agent Suite") in by
    assert ("fill", "Tech Stack Preferences (required)", None, "Python FastAPI, Gemini API.") in by
    assert ("check", "Not applicable — omit this section", "Constraints", None) in by
    assert not any(a == "fill" and label == "Constraints" for a, label, _, _ in by)      # disabled by its own box: not typed into
    # an LLM proposal that ticks the box AND types into the field (TC-004 hung 15 s on it) loses the fill
    els = build_inventory(prof)["elements"]
    ids = {(e.get("label"), e.get("group")): e["id"] for e in els.values()}
    prop = {"TC-001": {"applicable": True, "steps": [
        {"action": "check", "element_id": ids[("Not applicable — omit this section", "Constraints")]},
        {"action": "fill", "element_id": ids[("Constraints", None)], "value": "N/A"}]}}
    p2 = generate_action_plan(cls, prof, [_test(text=text)], proposals=prop)["plans"][0]
    assert not any(s["action"] == "fill" and (s.get("target") or {}).get("label") == "Constraints" for s in p2["steps"])


def test_a_negative_change_request_test_generates_first_then_submits_it_empty():
    prof, cls = _brd_agent_like()
    t = {"id": "n", "code": "TC-008", "title": "Reject empty change request on run revision", "variant_type": "negative",
         "input": "Scenario: Submit empty free-text change request.\n1. Generate the document suite.\n"
                  "2. Leave change_request field blank and click submit revision.",
         "expected_behavior": "The app refuses an empty change request"}
    prop = {"TC-008": {"applicable": False, "reason": "The UI lacks the run revision view", "steps": []}}
    p = generate_action_plan(cls, prof, [t], proposals=prop)["plans"][0]
    assert p["status"] == "ready" and p["variant"] == "negative"
    acts = [s["action"] for s in p["steps"]]
    assert acts.index("click") < acts.index("wait_for") < acts.index("follow_up")       # generate, then the follow-up
    assert next(s for s in p["steps"] if s["action"] == "follow_up")["value"] == ""
    assert any(s.get("synthetic") for s in p["steps"])                                 # the form is completed to generate


# ── complete submissions, result follow-ups, untestable tests ───────────────

def _lists_profile():
    """A BRD_Agent-like generating form: two list sections behind "+ Add" (one required), per-field "Auto-generate"
    boxes, and a run page (an earlier result) offering a change-request box."""
    prof, cls = _brd_agent_like(demo=False)
    form = next(p for p in prof["pages"] if p["path"] == "/new")["forms"][0]
    form["fields"] += [
        {"label": "Auto-generate / enrich", "name": "", "tag": "input", "type": "checkbox", "required": False,
         "readonly": False, "options": None, "group": "Objectives"},
        {"label": "Auto-generate / enrich", "name": "", "tag": "input", "type": "checkbox", "required": False,
         "readonly": False, "options": None, "group": "Constraints"},
        {"label": "Objective", "name": "", "tag": "input", "type": "text", "required": False, "readonly": False, "options": None,
         "revealed_by": {"text": "+ Add", "nth": 0, "context": "", "required": True, "section": "Objectives"}},
        {"label": "Section Title", "name": "", "tag": "input", "type": "text", "required": False, "readonly": False,
         "options": None, "revealed_by": {"text": "+ Add", "nth": 1, "context": "", "section": "Additional Sections"}},
    ]
    run = _summarise_page(_raw("/runs/20261017-082842-b05a14", buttons=["Download DOCX", "Apply Change"],
                               inputs=[_field("e.g. Add a risk about vendor lock-in", "textarea")],
                               forms=[{"kind": "virtual", "action": "", "method": "", "buttons": ["Apply Change"],
                                       "fields": [_field("e.g. Add a risk about vendor lock-in", "textarea")]}]))
    prof["pages"].append(run)
    return prof, cls


def _by_label(plan):
    return {(s.get("target") or {}).get("label"): s for s in plan["steps"] if s["action"] in ("fill", "select", "check")}


def test_a_positive_test_submits_the_whole_form_but_not_optional_lists():
    prof, cls = _lists_profile()
    p = generate_action_plan(cls, prof, [_test(text="Problem Statement: Clinics cannot book online")])["plans"][0]
    by = _by_label(p)
    assert by["Constraints"]["synthetic"] and by["Constraints"]["value"]          # optional text field: completed
    assert by["Objective"]["value"] == "Cut the time to get a request approved by half."  # row of a REQUIRED list
    assert "Section Title" not in by                                            # optional list stays empty
    assert "Auto-generate / enrich" not in by                                   # never ticks a box on its own
    acts = [(s["action"], (s.get("target") or {}).get("text") or (s.get("target") or {}).get("label")) for s in p["steps"]]
    assert acts.index(("click", "+ Add")) < acts.index(("fill", "Objective"))   # the row is added first
    # a plain search / filter form keeps its optional fields empty (an extra filter would empty the result)
    search = {"login": {"succeeded": True}, "pages": [{"path": "/orders", "forms": [{"fields": [
        {"label": "Customer", "type": "text"}, {"label": "Status", "type": "text"}], "submit_button": "Search",
        "buttons": ["Search"]}], "buttons": ["Search"]}]}
    sp = generate_action_plan({"app_type": "Form Application", "components": []}, search,
                              [{**_test(text="Customer: Alex"), "title": "Orders are found by customer"}])["plans"][0]
    assert "Status" not in _by_label(sp)
    # a data-entry form: required fields completed, optional ones (a promo code!) left as a user would leave them
    signup = {"login": {"succeeded": True}, "pages": [{"path": "/register", "forms": [{"fields": [
        {"label": "Full name", "type": "text", "required": True}, {"label": "Promo code", "type": "text"},
        {"label": "Company", "type": "text"}], "submit_button": "Register", "buttons": ["Register"]}], "buttons": ["Register"]}]}
    rp = generate_action_plan({"app_type": "Form Application", "components": []}, signup,
                              [{**_test(text="Email: a@b.c"), "title": "A user can register"}])["plans"][0]
    assert set(_by_label(rp)) == {"Full name"}
    # even on a generating form a code-like field is never guessed
    prof["pages"][0]["forms"][0]["fields"].append({"label": "Referral code", "type": "text", "required": False})
    gp = generate_action_plan(cls, prof, [_test(text="Problem Statement: Clinics cannot book online")])["plans"][0]
    assert "Referral code" not in _by_label(gp)


def test_a_field_whose_auto_generate_box_the_test_ticks_is_left_to_the_app():
    prof, cls = _lists_profile()
    text = "Project Name: Clinic\nConstraints: Auto-generate / enrich: checked\nObjective: Auto-generate / enrich: checked"
    p = generate_action_plan(cls, prof, [_test(text=text)])["plans"][0]
    checks = [(s["target"]["label"], s["target"].get("group")) for s in p["steps"] if s["action"] == "check"]
    assert ("Auto-generate / enrich", "Constraints") in checks
    assert ("Auto-generate / enrich", "Objectives") in checks                    # "Objective" names the "Objectives" box
    assert not any(s["action"] == "fill" and s["target"].get("label") == "Constraints" for s in p["steps"])


def test_literal_backslash_n_inputs_still_fill_their_fields():
    prof, cls = _brd_agent_like()
    text = "Scenario: generate.\\nProject Name: Clinic Booking\\nTech Stack Preferences: Django"
    p = generate_action_plan(cls, prof, [_test(text=text)])["plans"][0]
    by = _by_label(p)
    assert by["Project Name (required)"]["value"] == "Clinic Booking" and not by["Project Name (required)"].get("synthetic")
    assert by["Tech Stack Preferences (required)"]["value"] == "Django"


def test_revise_test_sends_its_own_change_request_through_the_results_box():
    prof, cls = _lists_profile()
    t = {"id": "r", "code": "TC-006", "title": "Submit free-text change request for iterative document revision",
         "variant_type": "positive", "expected_behavior": "The revision pipeline updates the deliverables",
         "input": "Scenario: Generate, then revise.\nProject Name: Revision Test\nChange Request: Include OAuth2 authentication."}
    # the model mapped the form; the follow-up (on a page it never saw) still comes from the rules
    els = build_inventory(prof)["elements"]
    pid = next(e["id"] for e in els.values() if e.get("label") == "Project Name (required)")
    prop = {"TC-006": {"applicable": True, "steps": [{"action": "fill", "element_id": pid, "value": "Revision Test"}]}}
    p = generate_action_plan(cls, prof, [t], proposals=prop)["plans"][0]
    fu = next(s for s in p["steps"] if s["action"] == "follow_up")
    assert fu["value"] == "Include OAuth2 authentication."                         # not the whole multi-line input
    assert fu["box_label"] == "e.g. Add a risk about vendor lock-in" and fu["submit_text"] == "Apply Change"
    acts = [s["action"] for s in p["steps"]]
    assert acts.index("click") < acts.index("wait_for") < acts.index("follow_up")
    no_request = {**t, "code": "TC-007", "input": "Scenario: Generate, then revise.\nProject Name: Revision Test"}
    fu2 = next(s for s in generate_action_plan(cls, prof, [no_request])["plans"][0]["steps"] if s["action"] == "follow_up")
    assert fu2["value"] == "Add a risk about vendor lock-in to the risks section."  # a small, harmless default


def test_history_test_collects_files_on_the_result_before_leaving_it():
    prof, cls = _lists_profile()
    t = {"id": "h", "code": "TC-017", "title": "Produce new revision without losing original run output",
         "variant_type": "positive", "input": "Project Name: Version Suite",
         "expected_behavior": "A new revision run is created while the original run remains in run history."}
    p = generate_action_plan(cls, prof, [t])["plans"][0]
    acts = [(s["action"], s.get("url")) for s in p["steps"]]
    dl = next(i for i, (a, _) in enumerate(acts) if a == "expect_download")
    assert dl < acts.index(("goto", "/history"))                                  # TC-017 waited for a file on /dashboard
    assert p["steps"][dl]["optional"] is True                                    # history is the point, not the file


def test_a_test_that_needs_a_fault_injected_runs_as_an_ordinary_use_of_the_feature():
    prof, cls = _brd_agent_like()
    t = {**_test(variant="robustness",
                 text="Scenario: Submit document generation request during transient LLM API rate-limit or timeout event."),
         "title": "LLM generation failure capture and retry mechanisms"}
    p = generate_action_plan(cls, prof, [t], proposals={"TC-001": {"applicable": False, "reason": "needs injection",
                                                                    "steps": []}})["plans"][0]
    assert p["status"] == "ready" and "no action through the UI" in p["proxy"]
    assert p["variant"] == "positive" and any(s.get("synthetic") for s in p["steps"])  # a complete, normal submission
    assert "click" in _actions(p) and "wait_for" in _actions(p)
    ok = generate_action_plan(cls, prof, [_test(text="Problem Statement: The form shows an error message when a "
                                                     "required field is empty")])["plans"][0]
    assert ok["status"] == "ready"                                              # an ordinary validation test is not a fault
