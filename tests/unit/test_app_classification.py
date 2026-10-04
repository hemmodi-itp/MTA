"""Unit tests for the Application Classification Engine (engines/runtime/classification.py)."""

from engines.repo_intel.model import Chunk, Graph, Node
from engines.runtime.classification import classify
from engines.runtime.discovery import _profile, _summarise_page
from tests.unit.test_runtime_discovery import _field, _raw


def _prof(*pages, api=()):
    return _profile("https://app.example.com/", [_summarise_page(p) for p in pages], [], list(api), 1.0)


def _graph(routes=(), pages=(), forms=(), components=(), agents=()):
    g = Graph()
    for r in routes:
        g.add(Node(kind="route", key=f"route:{r}", name=r))
    for p in pages:
        g.add(Node(kind="page", key=f"page:{p}", name=p, props={"path": p}))
    for i, n in enumerate(forms):
        g.add(Node(kind="form", key=f"form:{i}", name=f"Form{i}", props={"fields": [f"f{j}" for j in range(n)]}))
    for c in components:
        g.add(Node(kind="component", key=f"component:{c}", name=c))
    for a in agents:
        g.add(Node(kind="agent", key=f"agent:{a}", name=a))
    return g


def test_spec_example_25_inputs_generate_download_is_document_generator():
    fields = [_field(f"Field {i}") for i in range(25)]
    form = {"kind": "virtual", "action": "", "method": "", "buttons": ["Generate"], "fields": fields}
    prof = _prof(_raw("/new", inputs=fields, forms=[form], buttons=["Generate", "Download PDF", "Download DOCX"]))
    r = classify(prof)
    assert r["app_type"] == "Document Generator" and r["basis"] == "runtime"
    signals = " ".join(e["signal"] for e in r["evidence"])
    assert "25 input" in signals and "Generate" in signals and "Download" in signals
    assert r["scores"]["Document Generator"] > r["scores"]["Form Application"]
    assert r["testing_strategy"][0]["class"] == "Document Generator"


def test_plain_form_is_form_application():
    fields = [_field("Name", required=True), _field("Email", "email"), _field("Message", "textarea")]
    form = {"kind": "form", "action": "/contact", "method": "post", "buttons": ["Submit"], "fields": fields}
    r = classify(_prof(_raw("/contact", inputs=fields, forms=[form], buttons=["Submit"])))
    assert r["app_type"] == "Form Application"


def test_chatbot():
    box = _field("Type your message", "textarea")
    r = classify(_prof(_raw("/", inputs=[box], buttons=["Send"], logs=1, text="Chat with the assistant")))
    assert r["app_type"] == "Chatbot"


def test_dashboard_and_hybrid_with_chat():
    dash = _raw("/stats", charts=4, tables=2, buttons=["Refresh"])
    assert classify(_prof(dash))["app_type"] == "Dashboard"
    chat = _raw("/chat", inputs=[_field("Ask anything", "textarea")], buttons=["Send"], logs=1, text="chat")
    r = classify(_prof(dash, chat))
    assert r["app_type"] == "Hybrid Application" and set(r["components"]) == {"Dashboard", "Chatbot"}
    assert len(r["testing_strategy"]) == 2


def test_rest_api_from_code_only():
    g = _graph(routes=["GET /api/items", "POST /api/items", "DELETE /api/items/{id}"])
    r = classify(None, g, [], {"dependencies": ["fastapi"]})
    assert r["app_type"] == "REST API" and r["basis"] == "code"


def test_workflow_system_from_runtime_actions():
    page = _raw("/requests/7", buttons=["Approve", "Reject", "Next", "Back"], text="Request awaiting approval")
    r = classify(_prof(page))
    assert r["app_type"] == "Workflow System"


def test_static_website():
    links = [{"href": f"https://app.example.com{p}", "text": p.strip("/"), "download": False}
             for p in ("/about", "/pricing", "/contact", "/blog")]
    r = classify(_prof(_raw("/", links=links, buttons=["Menu"])))
    assert r["app_type"] == "Static Website"


def test_login_wall_falls_back_to_code_and_says_so():
    fields = [_field("Email", "email"), _field("Password", "password")]
    login = _raw("/login", inputs=fields, password=1, buttons=["Log in"],
                 forms=[{"kind": "form", "action": "", "method": "post", "buttons": ["Log in"], "fields": fields}])
    prof = _profile("https://app.example.com/", [_summarise_page(login)], [], [], 1.0, gated=["/new"])
    assert prof["app_type"] == "Behind login"
    g = _graph(routes=["POST /api/generate", "POST /api/runs/{id}/export/{doc}"], pages=["/new"], forms=[5])
    chunks = [Chunk("src/api.py", 1, 3, "return FileResponse(path, media_type='application/pdf')")]
    r = classify(prof, g, chunks, {"dependencies": ["python-docx", "next"]})
    assert r["app_type"] == "Document Generator" and r["basis"] == "code" and "code only" in r["note"]
    assert all(e["source"] == "code" for e in r["evidence"])


def test_css_transitions_are_not_workflow_evidence():
    chunks = [Chunk("src/ui.tsx", 1, 1, '<div className="transition-all duration-200 transition-colors" />')]
    r = classify(None, _graph(pages=["/"], components=["Card"]), chunks, {})
    assert r["scores"]["Workflow System"] == 0


def test_no_signals_is_unknown():
    assert classify(None, Graph(), [], {})["app_type"] == "Unknown"
