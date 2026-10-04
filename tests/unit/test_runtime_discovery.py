"""Unit tests for the Runtime Discovery Engine's page summary, classification and flow logic (no browser)."""

from engines.runtime.discovery import _profile, _summarise_page


def _raw(path="/", inputs=(), forms=(), buttons=(), links=(), password=0, logs=0, text="", charts=0, tables=0,
         redirected=False, frameworks=None):
    return {
        "url": f"https://app.example.com{path}", "requested_url": f"https://app.example.com{path}", "status": 200,
        "title": "App", "headings": [], "forms": list(forms), "inputs": list(inputs),
        "buttons": [{"text": b, "type": "", "disabled": False} for b in buttons], "links": list(links),
        "file_inputs": 0, "password_inputs": password, "tables": tables, "charts": charts, "iframes": 0,
        "log_regions": logs, "frameworks": frameworks or {}, "text_sample": text, "redirected_to_auth": redirected,
    }


def _field(label, type_="text", required=False):
    return {"label": label, "name": label.lower(), "tag": "input", "type": type_, "required": required, "readonly": False}


def test_document_generator_with_form_and_export():
    form = {"kind": "virtual", "action": "", "method": "", "buttons": ["Generate documents"],
            "fields": [_field("Project name", required=True), _field("Problem", "textarea"), _field("Scope", "textarea")]}
    page = _summarise_page(_raw("/new", inputs=form["fields"], forms=[form], buttons=["Generate documents", "Export DOCX"]))
    prof = _profile("https://app.example.com/", [page], [], ["POST /api/generate"], 1.0)
    assert prof["app_type"] == "Document Generator"
    assert prof["forms"] == 1 and prof["downloads"] is True and prof["chat_interface"] is False
    assert prof["user_flows"][0]["steps"][-1] == "Expect download / export"


def test_chat_interface_detected():
    box = _field("Type your message", "textarea")
    page = _summarise_page(_raw("/", inputs=[box], buttons=["Send"], logs=1, text="Chat with the assistant"))
    prof = _profile("https://app.example.com/", [page], [], [], 1.0)
    assert prof["chat_interface"] and prof["app_type"] == "Chatbot"


def test_login_page_is_never_a_chat():
    fields = [_field("Username"), _field("Password", "password")]
    form = {"kind": "form", "action": "", "method": "post", "buttons": ["Login"], "fields": fields}
    page = _summarise_page(_raw("/", inputs=fields[:1], forms=[form], buttons=["Login"], password=1, logs=1,
                                text="error message"))
    assert page["chat_interface"] is False and page["forms"][0]["is_login"]


def test_login_wall_is_not_guessed_as_a_type():
    fields = [_field("Email", "email"), _field("Password", "password")]
    login = _summarise_page(_raw("/login", inputs=fields, password=1, buttons=["Log in"],
                                 forms=[{"kind": "form", "action": "", "method": "post", "buttons": ["Log in"], "fields": fields}]))
    prof = _profile("https://app.example.com/", [login], [{"method": "GET", "path": "/api/auth/me", "status": 401}], [], 1.0,
                    gated=["/dashboard", "/new"])
    assert prof["app_type"] == "Behind login" and prof["authentication"] is True
    assert prof["gated_pages"] == ["/dashboard", "/new"]
    assert prof["user_flows"][0]["name"] == "Log in"


def test_dashboard_and_hybrid():
    dash = _summarise_page(_raw("/stats", charts=3, tables=1, buttons=["Refresh"]))
    assert _profile("https://x/", [dash], [], [], 1.0)["app_type"] == "Dashboard"
    box = _field("Ask anything", "textarea")
    chat = _summarise_page(_raw("/chat", inputs=[box], buttons=["Send"], logs=1, text="chat"))
    assert _profile("https://x/", [dash, chat], [], [], 1.0)["app_type"] == "Hybrid Application"
