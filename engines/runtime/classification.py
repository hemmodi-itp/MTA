"""
classification.py — Application Classification Engine.

    result = classify(runtime_profile, graph, chunks, repo_model)

Classes: Chatbot · Form Application · Dashboard · Document Generator · REST API · Workflow System ·
Static Website · Hybrid Application.

Every signal adds weighted points to one class and is recorded as evidence with its source:
  * runtime — what the live app showed (engines/runtime/discovery.py profile);
  * code    — what the repository implements (knowledge graph, dependencies, code patterns).
Runtime evidence is trusted more (weights ×1.0) than code (×0.7) because it is what users get;
when the live app was not visible (behind login, unreachable, not deployed) code alone decides
and `basis` says so.

Decision: highest score wins. Form Application is the generic class — a Document Generator or
Chatbot also has forms — so it only wins if nothing more specific has real support. A second
specific class within 75% of the winner (and well supported) makes the app a Hybrid Application.
Deterministic and explainable: the same inputs always give the same answer with the same reasons.
"""

import re
from typing import Any, Dict, List, Optional, Sequence

CLASSES = ["Chatbot", "Form Application", "Dashboard", "Document Generator", "REST API", "Workflow System",
           "Static Website", "Hybrid Application"]
_SPECIFIC = ["Chatbot", "Dashboard", "Document Generator", "REST API", "Workflow System"]
RUNTIME_W, CODE_W = 1.0, 0.7
HYBRID_RATIO = 0.75
MIN_SUPPORT = 4.0

# How the next engine (Action Generation) should test each class.
TESTING_STRATEGY = {
    "Chatbot": "Conversation testing: multi-turn prompts, refusals, hallucination and prompt-injection probes, reply judging",
    "Form Application": "Workflow testing: fill and submit forms, required-field and invalid-input validation, success state",
    "Dashboard": "Analytics testing: load views, check figures against known data, filters and drill-downs",
    "Document Generator": "Output testing: fill the input form, generate, download the artifact, inspect its structure and content",
    "REST API": "Endpoint testing: contract/schema checks, status codes, negative inputs, auth enforcement",
    "Workflow System": "Multi-step testing: walk each state transition, approvals and rejections, resume and error paths",
    "Static Website": "Feature verification: required content and links present, navigation works",
}

_DOC_DEPS = {"python-docx", "docx", "docxtpl", "reportlab", "weasyprint", "pdfkit", "fpdf", "fpdf2", "pypandoc", "markdown-pdf",
             "jspdf", "pdfmake", "docxtemplater", "pdf-lib", "html-pdf", "puppeteer", "openpyxl", "xlsxwriter", "python-pptx",
             "pptxgenjs", "exceljs", "file-saver"}
_CHART_DEPS = {"recharts", "chart.js", "react-chartjs-2", "plotly", "plotly.js", "react-plotly.js", "d3", "echarts", "echarts-for-react",
               "apexcharts", "react-apexcharts", "highcharts", "victory", "nivo", "@nivo/core", "matplotlib", "altair", "bokeh", "dash"}
_CHAT_DEPS = {"chainlit", "gradio", "@chatscope/chat-ui-kit-react", "ai", "@ai-sdk/react", "streamlit-chat"}
_QUEUE_DEPS = {"celery", "rq", "dramatiq", "temporalio", "@temporalio/client", "bullmq", "bull", "prefect", "airflow", "apache-airflow"}

_CODE_PATTERNS = [
    # (class, regex, points, description)
    ("Document Generator", r"FileResponse|Content-Disposition|StreamingResponse\(.*(docx|pdf)|send_file\(|pandoc|\.docx\b|application/pdf|"
                           r"wordprocessingml|createObjectURL|saveAs\(|new Blob\(", 3, "file generation / download code"),
    ("Chatbot", r"st\.chat_input|st\.chat_message|gr\.ChatInterface|gr\.Chatbot|useChat\(|cl\.on_message|ChatPromptTemplate|"
                r"messages\s*:\s*\[\s*\{\s*role", 3, "chat UI or chat-history handling"),
    ("Dashboard", r"<(LineChart|BarChart|PieChart|AreaChart|Chart|Plot)\b|st\.(line_chart|bar_chart|metric|dataframe)|plt\.(plot|bar)|"
                  r"GROUP BY|\.groupby\(|aggregate\(", 2, "charting / aggregation code"),
    ("Workflow System", r"\b(approve[ds]?|reject(ed|ion)?|approval|pending_review|awaiting_approval|state_machine|workflow_status|"
                        r"transition_to|allowed_transitions)\b", 2,
                        "approval / state-transition logic"),
]


def classify(profile: Optional[Dict[str, Any]], graph=None, chunks: Sequence = (), repo_model: Optional[Dict] = None) -> Dict[str, Any]:
    scores = {c: 0.0 for c in CLASSES if c != "Hybrid Application"}
    evidence: List[Dict[str, Any]] = []

    def add(cls: str, points: float, signal: str, source: str) -> None:
        w = points * (RUNTIME_W if source == "runtime" else CODE_W)
        scores[cls] += w
        evidence.append({"class": cls, "signal": signal, "source": source, "points": round(w, 2)})

    runtime_visible = bool(profile) and profile.get("app_type") not in ("Behind login", "Unreachable", None) \
        and profile.get("pages_inspected", 0) > 0
    if runtime_visible:
        _runtime_signals(profile, add)
    if graph is not None:
        _code_signals(graph, chunks, repo_model or {}, add)

    if not any(scores.values()):
        return _result("Static Website" if runtime_visible else "Unknown", 0.0, scores, evidence, [], runtime_visible, graph,
                       note="no interactive or application signals found")

    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    specific = [(c, s) for c, s in ranked if c in _SPECIFIC and s >= MIN_SUPPORT]
    winner = ranked[0][0]
    if winner == "Form Application" and specific:  # forms are a means; a specific class with real support wins
        winner = specific[0][0]
    if winner == "Static Website" and specific:
        winner = specific[0][0]
    secondary = [c for c, s in specific if c != winner and s >= HYBRID_RATIO * scores[winner]]
    total = sum(scores.values()) or 1.0
    confidence = round(min(0.98, scores[winner] / total + 0.15 * (1 if runtime_visible and graph is not None else 0)), 2)
    if secondary:
        return _result("Hybrid Application", confidence, scores, evidence, [winner] + secondary, runtime_visible, graph)
    return _result(winner, confidence, scores, evidence, [], runtime_visible, graph)


def _runtime_signals(p: Dict[str, Any], add) -> None:
    pages = p.get("pages") or []
    inputs = sum(f.get("field_count", 0) for pg in pages for f in pg.get("forms", []) if not f.get("is_login"))
    buttons = [b for pg in pages for b in pg.get("buttons", [])]
    gen_buttons = [b for b in buttons if re.search(r"\b(generate|create|build|draft|compose|produce|convert)\b", b, re.I)]
    dl_buttons = [b for pg in pages for b in pg.get("downloads", {}).get("buttons", [])]
    dl_links = [l for pg in pages for l in pg.get("downloads", {}).get("links", [])]
    charts = sum(pg.get("charts", 0) for pg in pages)
    tables = sum(pg.get("tables", 0) for pg in pages)
    wizard = [b for b in buttons if re.search(r"\b(next|back|previous|step \d|continue|finish)\b", b, re.I)]
    approvals = [b for b in buttons if re.search(r"\b(approve|reject|submit for review|assign|escalate)\b", b, re.I)]
    html_pages = [pg for pg in pages if pg.get("title") is not None]

    if p.get("chat_interface"):
        add("Chatbot", 6, "chat box with a send control on the live app", "runtime")
    if dl_buttons or dl_links:
        add("Document Generator", 4, f"download/export controls: {', '.join((dl_buttons + dl_links)[:3])}", "runtime")
    if gen_buttons:
        add("Document Generator", 2, f"generate button(s): {', '.join(gen_buttons[:3])}", "runtime")
    if inputs >= 8 and (gen_buttons or dl_buttons):
        add("Document Generator", 2, f"{inputs} input fields feeding a generate/export action", "runtime")
    if inputs:
        add("Form Application", 2 + min(inputs, 20) / 5, f"{inputs} input field(s) in {p.get('forms', 0)} form(s)", "runtime")
    if charts >= 2:
        add("Dashboard", 3 + min(charts, 10) / 2, f"{charts} chart(s)", "runtime")
    if tables >= 2:
        add("Dashboard", 2, f"{tables} data table(s)", "runtime")
    if wizard:
        add("Workflow System", 2, f"step navigation buttons: {', '.join(sorted(set(wizard))[:3])}", "runtime")
    if approvals:
        add("Workflow System", 3, f"approval/assignment actions: {', '.join(sorted(set(approvals))[:3])}", "runtime")
    if not html_pages and p.get("api_calls"):
        add("REST API", 6, "live URL answers with an API, not web pages", "runtime")
    if html_pages and not inputs and not p.get("chat_interface") and not charts and not dl_buttons:
        add("Static Website", 4, "pages with content and navigation only", "runtime")


def _code_signals(graph, chunks: Sequence, model: Dict, add) -> None:
    deps = {d.lower() for d in (model.get("dependencies") or [])}
    routes = graph.of_kind("route")
    pages = graph.of_kind("page")
    components = graph.of_kind("component")
    forms = graph.of_kind("form")
    agents = graph.of_kind("agent")

    if deps & _DOC_DEPS:
        add("Document Generator", 3, f"document libraries: {', '.join(sorted(deps & _DOC_DEPS)[:4])}", "code")
    if deps & _CHART_DEPS:
        add("Dashboard", 3, f"chart libraries: {', '.join(sorted(deps & _CHART_DEPS)[:4])}", "code")
    if deps & _CHAT_DEPS:
        add("Chatbot", 2, f"chat UI libraries: {', '.join(sorted(deps & _CHAT_DEPS)[:4])}", "code")
    if deps & _QUEUE_DEPS:
        add("Workflow System", 3, f"job/workflow engines: {', '.join(sorted(deps & _QUEUE_DEPS)[:4])}", "code")

    export_routes = [r.name for r in routes if re.search(r"export|download|render|pdf|docx|report", r.name or "", re.I)]
    gen_routes = [r.name for r in routes if re.search(r"generat|create|draft|compose", r.name or "", re.I)]
    chat_routes = [r.name for r in routes if re.search(r"\b(chat|message|ask|conversation|completions?)\b", r.name or "", re.I)]
    stat_routes = [r.name for r in routes if re.search(r"stats|metrics|analytics|dashboard|summary|report", r.name or "", re.I)]
    if export_routes:
        add("Document Generator", 3, f"export/download route(s): {', '.join(export_routes[:3])}", "code")
    if gen_routes:
        add("Document Generator", 2, f"generation route(s): {', '.join(gen_routes[:3])}", "code")
    if chat_routes:
        add("Chatbot", 3, f"chat route(s): {', '.join(chat_routes[:3])}", "code")
    if stat_routes and (deps & _CHART_DEPS):
        add("Dashboard", 2, f"aggregate route(s): {', '.join(stat_routes[:3])}", "code")
    if any(n.props.get("produces_download") for n in graph.of_kind("file")):
        add("Document Generator", 2, "frontend code triggers file downloads", "code")

    fields = sum(len(f.props.get("fields") or []) for f in forms)
    if forms:
        add("Form Application", 2 + min(fields, 20) / 5, f"{len(forms)} form(s) in the frontend code ({fields} fields parsed)", "code")
    if routes and not pages and not components and not forms:
        add("REST API", 5, f"{len(routes)} HTTP route(s) and no UI pages or components", "code")
    if pages and not routes and not forms and not agents:
        add("Static Website", 3, f"{len(pages)} page(s) with no backend routes or forms", "code")
    if len(agents) >= 3:
        add("Workflow System", 1, f"{len(agents)} agents orchestrated internally (a backend pipeline, not a user-facing workflow)", "code")

    code_text = "\n".join(c.content for c in chunks if not c.file_path.lower().endswith((".md", ".txt", ".rst", ".json")))
    for cls, rx, pts, desc in _CODE_PATTERNS:
        hits = len(re.findall(rx, code_text, re.I))
        if hits:
            add(cls, pts + min(hits, 6) / 3, f"{desc} ({hits} occurrence{'s' if hits > 1 else ''})", "code")


def _result(app_type: str, confidence: float, scores: Dict[str, float], evidence: List[Dict], components: List[str],
            runtime_visible: bool, graph, note: Optional[str] = None) -> Dict[str, Any]:
    has_code = graph is not None
    basis = "runtime + code" if runtime_visible and has_code else "runtime" if runtime_visible else "code" if has_code else "none"
    strategy_for = components or [app_type]
    return {
        "app_type": app_type,
        "confidence": confidence,
        "components": components,  # for Hybrid Application: the classes it combines
        "basis": basis,
        "note": note or ("Live app not visible (login wall or not deployed): classified from the repository code only."
                         if basis == "code" else None),
        "scores": {c: round(s, 2) for c, s in sorted(scores.items(), key=lambda kv: -kv[1])},
        "evidence": sorted(evidence, key=lambda e: -e["points"])[:30],
        "testing_strategy": [{"class": c, "strategy": TESTING_STRATEGY[c]} for c in strategy_for if c in TESTING_STRATEGY],
    }
