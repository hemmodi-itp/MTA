"""Repository Intelligence: every source language indexed, new route/page/test forms, coverage, graph indexes, store."""

from pathlib import Path

from engines.repo_intel import INDEXER_VERSION
from engines.repo_intel.indexer import index_repository
from engines.repo_intel.js_parser import parse_js
from engines.repo_intel.model import Graph, Node
from engines.repo_intel.store import SnapshotStore
from engines.trace.citations import is_wired, nodes_at
from engines.trace.retrieve import CodeIndex

FILES = {
    "api/src/main/java/com/acme/ItemController.java": '''package com.acme;

@RestController
@RequestMapping("/api/items")
public class ItemController {
    @PostMapping("/{id}/archive")
    public ResponseEntity<Item> archiveItem(@PathVariable String id) {
        return service.archive(id);
    }
}
''',
    "svc/main.go": '''package main

func main() {
    http.HandleFunc("/healthz", healthHandler)
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
    w.Write([]byte("ok"))
}
''',
    "svc/main_test.go": '''package main

func TestHealth(t *testing.T) {
    healthHandler(nil, nil)
}
''',
    "lib/billing.rb": '''class Invoice
  def total_with_tax(rate)
    subtotal * (1 + rate)
  end
end
''',
    "web/src/main.tsx": '''import { createRoot } from "react-dom/client";
import App from "./App";
createRoot(document.getElementById("root")!).render(<App />);
''',
    "web/src/App.tsx": '''export default function App() {
  const load = () => api.get("/api/items");
  return <Routes><Route path="/reports" element={<Reports />} /></Routes>;
}
''',
    "web/src/Reports.tsx": '''export function Reports() { return <div>reports</div>; }
''',
    "web/src/App.test.tsx": '''import App from "./App";
test("renders", () => { App(); });
''',
    "py/urls.py": '''from django.urls import path
from . import views

urlpatterns = [path("orders/", views.create_order)]
''',
    "py/views.py": '''def create_order(request):
    return save(request)
''',
    "py/flask_app.py": '''from flask import Flask
app = Flask(__name__)

def upload():
    return "ok"

app.add_url_rule("/upload", view_func=upload, methods=["POST"])
''',
    "py/ui.py": '''import streamlit as st
from helpers import summarise

text = st.text_area("Paste text")
if st.button("Summarise"):
    st.write(summarise(text))
''',
    "py/helpers.py": '''def summarise(text):
    return text[:10]
''',
    ".env.example": "OPENAI_API_KEY=\nDATABASE_URL=postgres://\n",
    "styles/site.scss": ".btn { color: red; }\n",
}


def _repo(tmp_path: Path) -> Path:
    for rel, text in FILES.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return tmp_path


def test_every_language_is_indexed_and_wired(tmp_path):
    idx = index_repository(_repo(tmp_path), all_paths=list(FILES) + ["svc/big_mailer.go"])
    g = idx.graph
    files_with_chunks = {c.file_path for c in idx.chunks}
    assert {"api/src/main/java/com/acme/ItemController.java", "svc/main.go", "lib/billing.rb",
            "styles/site.scss"} <= files_with_chunks
    # Spring route with class prefix → handler method
    route = g.nodes["route:POST /api/items/*/archive"]
    assert route.props["handler"].endswith("#ItemController.archiveItem")
    # Go route resolved to its handler by name, Go test node
    assert ("route:ANY /healthz", "exposes", "symbol:svc/main.go#healthHandler") in g.edges
    assert any(n.key.startswith("test:svc/main_test.go") for n in g.of_kind("test"))
    # Ruby symbol with qualname and span
    sym = g.nodes["symbol:lib/billing.rb#Invoice.total_with_tax"]
    assert (sym.start_line, sym.end_line) == (2, 4)
    # .env.example keys are config
    assert "config:OPENAI_API_KEY" in g.nodes and "config:DATABASE_URL" in g.nodes


def test_js_pages_tests_and_client_calls(tmp_path):
    idx = index_repository(_repo(tmp_path))
    g = idx.graph
    assert not any(k.startswith("route:GET /api/items") for k in g.nodes)  # api.get is a client call, not a route
    assert ("page:/", "renders", "file:web/src/main.tsx") in g.edges  # SPA entry point
    assert ("page:/reports", "renders", "component:web/src/Reports.tsx#Reports") in g.edges
    t = next(n for n in g.of_kind("test") if n.file_path == "web/src/App.test.tsx")
    assert (t.key, "tests", "file:web/src/App.tsx") in g.edges
    assert "No automated tests found" not in idx.repo_model["risk_signals"]


def test_python_web_entry_points_prove_wiring(tmp_path):
    idx = index_repository(_repo(tmp_path))
    g = idx.graph
    assert ("route:ANY /orders", "exposes", "symbol:py/views.py#create_order") in g.edges
    assert ("route:POST /upload", "exposes", "symbol:py/flask_app.py#upload") in g.edges
    assert "form:py/ui.py#streamlit" in g.nodes
    # code called from the Streamlit script is reachable from an entry point
    assert is_wired(g, nodes_at(g, "py/helpers.py", 1, 2))


def test_coverage_reports_unfetched_and_by_language(tmp_path):
    idx = index_repository(_repo(tmp_path), all_paths=list(FILES) + ["svc/big_mailer.go", "assets/logo.png"])
    cov = idx.repo_model["coverage"]
    assert cov["unfetched_source"] == ["svc/big_mailer.go"] and cov["unfetched_source_count"] == 1
    assert cov["by_language"]["Go"] == 2 and cov["by_language"]["Java"] == 1
    assert cov["skipped"]["not_fetched"] == 2 and cov["complete"] is False
    assert INDEXER_VERSION == "ri-2.0"


def test_file_cap_is_respected(tmp_path):
    idx = index_repository(_repo(tmp_path), max_files=3)
    assert idx.repo_model["coverage"]["files_indexed"] == 3
    assert idx.repo_model["coverage"]["skipped"]["file_cap"] > 0


def test_graph_indexes_stay_correct_after_direct_edge_mutation():
    g = Graph()
    g.add(Node("symbol", "a", "x.py", 1, 2, "a"))
    g.link("a", "calls", "b")
    assert g.out("a") == [("calls", "b")] and g.inbound("b") == [("calls", "a")]
    g.edges.add(("c", "calls", "b"))  # older callers mutate the set directly
    assert sorted(g.inbound("b")) == [("calls", "a"), ("calls", "c")]
    assert g.in_file("x.py")[0].key == "a" and g.of_kind("symbol")[0].key == "a"


def test_graph_seed_tokens_are_precomputed():
    g = Graph()
    parse_js("src/routes.ts", 'router.post("/api/invoices", createInvoice);\n', g)
    index = CodeIndex(g, [])
    assert index.graph_seeds(["invoices"])[0][0] == "route:POST /api/invoices"


class _FakeDB:
    def __init__(self):
        self.queries = []

    def query(self, sql, params=None):
        self.queries.append(sql)
        return []


def test_store_skips_caching_without_a_commit_sha():
    db = _FakeDB()
    store = SnapshotStore(db)
    assert store.find("o/r", None) is None and store.find("o/r", "0" * 40) is None
    assert store.save("o/r", None, None) is None and store.save("o/r", "0" * 40, None) is None
    assert db.queries == []
