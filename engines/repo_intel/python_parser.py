"""
python_parser.py — exact extraction from Python sources with the stdlib `ast`.

Per file: symbols (functions, classes, methods), HTTP routes (FastAPI, Flask, Starlette-style
decorators, router prefixes, `add_url_rule`, `add_api_route`, Django `urls.py` path()/re_path()/url()),
Streamlit and Gradio apps as page + form entry points (so code they call is provably wired), LLM SDK
calls, prompt constants, agent-framework constructs (LangGraph, CrewAI, ADK, OpenAI Agents), env-var
config, ORM tables, tests, and the call names each function (and the module body) uses, resolved to
edges later by indexer._link_calls. Chunks = one per function or class (classes over 150 lines are
chunked per method).
"""

import ast
from typing import Dict, List, Optional, Set, Tuple

from engines.repo_intel.model import Chunk, Graph, Node, normalize_route_path, symbol_key

_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "websocket", "api_route"}
_LLM_ATTRS = {
    "generate_content", "generate_content_stream", "generate_json", "create", "acreate", "invoke", "ainvoke",
    "stream", "astream", "completion", "acompletion", "chat", "predict", "run", "kickoff",
}
_LLM_HINTS = ("openai", "anthropic", "genai", "gemini", "claude", "gpt", "llm", "chat", "completions", "messages",
              "litellm", "ollama", "bedrock", "langchain", "model")
_LLM_CTORS = {
    "ChatOpenAI", "ChatAnthropic", "ChatGoogleGenerativeAI", "ChatVertexAI", "AzureChatOpenAI", "OpenAI", "AsyncOpenAI",
    "Anthropic", "AsyncAnthropic", "GenerativeModel", "Client", "ChatOllama", "ChatGroq", "Groq",
}
_AGENT_CTORS = {"Agent", "LlmAgent", "SequentialAgent", "ParallelAgent", "LoopAgent", "Crew", "Task", "StateGraph",
                "AgentExecutor", "ReActAgent", "Swarm"}
_ORM_BASES = {"Base", "Model", "SQLModel", "DeclarativeBase", "Document"}  # not pydantic BaseModel
_PROMPT_NAME_HINTS = ("PROMPT", "SYSTEM", "INSTRUCTION", "TEMPLATE")


def _const_str(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):  # f-string: keep the literal parts
        return "".join(v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
    return None


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        return _dotted(node.func)
    return ""


def _looks_like_prompt(text: str) -> bool:
    t = text.strip()
    return len(t) >= 160 and ("\n" in t or len(t) > 300) and any(
        w in t.lower() for w in ("you are", "your task", "respond", "return", "instructions", "assistant", "json"))


_STREAMLIT_INPUTS = {"text_input", "text_area", "number_input", "selectbox", "multiselect", "radio", "checkbox",
                     "slider", "select_slider", "date_input", "time_input", "file_uploader", "camera_input",
                     "color_picker", "chat_input", "toggle", "data_editor"}
_STREAMLIT_BUTTONS = {"button", "form_submit_button", "download_button", "link_button"}
_GRADIO_APPS = {"Interface", "ChatInterface", "TabbedInterface"}
_GRADIO_EVENTS = {"click", "submit", "change", "upload"}
_DJANGO_ROUTES = {"path", "re_path", "url"}


class _FileVisitor(ast.NodeVisitor):
    def __init__(self, path: str, graph: Graph, lines: List[str], imports: Optional[Dict[str, str]] = None):
        self.path, self.g, self.lines = path, graph, lines
        self.imports = imports or {}
        self.st_alias = {a for a, m in self.imports.items() if m.split(".")[0] == "streamlit"}
        self.gr_alias = {a for a, m in self.imports.items() if m.split(".")[0] == "gradio"}
        self.is_urls = path.rsplit("/", 1)[-1] == "urls.py"
        self.ui_fields: List[Dict] = []
        self.ui_buttons: List[str] = []
        self.ui_lines: List[int] = []
        self.gradio_handlers: List[Tuple[int, str]] = []
        self.stack: List[str] = []           # qualname parts
        self.func_keys: List[str] = []       # enclosing function symbol keys
        self.router_prefix: Dict[str, str] = {}
        self.calls: Dict[str, Set[str]] = {}  # symbol key → called simple names
        self.name_refs: Dict[str, Set[str]] = {}
        self.is_test_file = path.rsplit("/", 1)[-1].startswith("test_") or path.endswith("_test.py") or "/tests/" in f"/{path}"

    # ── helpers ──
    def _owner(self) -> str:
        return self.func_keys[-1] if self.func_keys else f"file:{self.path}"

    def _route(self, method: str, full: str, line: int, handler_key: Optional[str], handler_name: Optional[str],
               framework: str = "python") -> None:
        full = full if full.startswith("/") else "/" + full
        rkey = f"route:{method} {normalize_route_path(full)}"
        props = {"method": method, "path": full, "framework": framework}
        if handler_key:
            props["handler"] = handler_key
        elif handler_name:
            props["handler_name"] = handler_name
        self.g.add(Node("route", rkey, self.path, line, line, f"{method} {full}", props))
        self.g.link(rkey, "exposes", handler_key or f"file:{self.path}")

    def _local_symbol(self, expr: Optional[ast.AST]) -> Tuple[Optional[str], Optional[str]]:
        """(symbol key if `expr` names a function defined in this file, else None; its simple name)."""
        if expr is None or isinstance(expr, ast.Constant):
            return None, None
        name = _dotted(expr).split(".")[-1]
        if not name:
            return None, None
        key = symbol_key(self.path, name)
        return (key if key in self.g.nodes else None), name

    def _add_symbol(self, node, kind: str) -> str:
        qual = ".".join(self.stack + [node.name])
        key = symbol_key(self.path, qual)
        self.g.add(Node("symbol", key, self.path, node.lineno, getattr(node, "end_lineno", node.lineno), qual,
                        {"symbol_kind": kind, "async": isinstance(node, ast.AsyncFunctionDef)}))
        self.g.link(f"file:{self.path}", "defines", key)
        if self.is_test_file and kind == "function" and node.name.startswith("test"):
            tkey = f"test:{self.path}#{qual}"
            self.g.add(Node("test", tkey, self.path, node.lineno, getattr(node, "end_lineno", node.lineno), qual))
            self.g.link(tkey, "defines", key)
        return key

    # ── module-level: routers with prefixes, prompt constants ──
    def visit_Assign(self, node: ast.Assign):
        value = node.value
        if isinstance(value, ast.Call) and _dotted(value.func).split(".")[-1] in ("APIRouter", "Blueprint"):
            prefix = ""
            for kw in value.keywords:
                if kw.arg in ("prefix", "url_prefix") and _const_str(kw.value):
                    prefix = _const_str(kw.value)
            for t in node.targets:
                if isinstance(t, ast.Name):
                    self.router_prefix[t.id] = prefix
        text = _const_str(value)
        for t in node.targets:
            if isinstance(t, ast.Name) and text is not None and (
                    any(h in t.id.upper() for h in _PROMPT_NAME_HINTS) or _looks_like_prompt(text)):
                key = f"prompt:{self.path}#{t.id}"
                self.g.add(Node("prompt", key, self.path, node.lineno, getattr(node, "end_lineno", node.lineno), t.id,
                                {"chars": len(text), "preview": text.strip()[:300]}))
                self.g.link(self._owner(), "defines", key)
        self.generic_visit(node)  # visit_Call handles any call on the right-hand side

    def visit_ClassDef(self, node: ast.ClassDef):
        key = self._add_symbol(node, "class")
        bases = {_dotted(b).split(".")[-1] for b in node.bases}
        sqlmodel_table = "SQLModel" in bases and any(kw.arg == "table" for kw in node.keywords)
        if (bases & _ORM_BASES - {"SQLModel"} or sqlmodel_table) and any(
                isinstance(s, (ast.AnnAssign, ast.Assign)) for s in node.body):
            tkey = f"table:{node.name}"
            self.g.add(Node("table", tkey, self.path, node.lineno, node.end_lineno, node.name))
            self.g.link(key, "defines", tkey)
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def _visit_func(self, node):
        key = self._add_symbol(node, "function")
        for dec in node.decorator_list:
            self._route_from_decorator(dec, key)
        self.stack.append(node.name)
        self.func_keys.append(key)
        self.calls.setdefault(key, set())
        self.name_refs.setdefault(key, set())
        self.generic_visit(node)
        self.func_keys.pop()
        self.stack.pop()

    visit_FunctionDef = _visit_func
    visit_AsyncFunctionDef = _visit_func

    def _route_from_decorator(self, dec: ast.AST, handler_key: str) -> None:
        if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
            return
        method = dec.func.attr.lower()
        owner = _dotted(dec.func.value)
        if method not in _HTTP_METHODS and method != "route":
            return
        path = _const_str(dec.args[0]) if dec.args else None
        for kw in dec.keywords:
            if kw.arg in ("path", "rule") and _const_str(kw.value):
                path = _const_str(kw.value)
        if path is None:
            return
        methods = [method.upper()]
        if method in ("route", "api_route"):
            methods = ["GET"]
            for kw in dec.keywords:
                if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
                    methods = [str(_const_str(e) or "").upper() for e in kw.value.elts if _const_str(e)] or ["GET"]
        full = (self.router_prefix.get(owner, "") + path) or "/"
        for m in methods:
            rkey = f"route:{m} {normalize_route_path(full)}"
            self.g.add(Node("route", rkey, self.path, dec.lineno, dec.lineno, f"{m} {full}",
                            {"method": m, "path": full, "framework": "python", "handler": handler_key}))
            self.g.link(rkey, "exposes", handler_key)

    def visit_Call(self, node: ast.Call):
        self._scan_call_expr(node)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript):
        if _dotted(node.value) in ("os.environ", "environ") and _const_str(node.slice):
            ckey = f"config:{_const_str(node.slice)}"
            self.g.add(Node("config", ckey, name=_const_str(node.slice)))
            self.g.link(self._owner(), "configured_by", ckey)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        if self.func_keys:
            self.name_refs[self.func_keys[-1]].add(node.id)

    def _scan_call_expr(self, node: ast.AST) -> None:
        if not isinstance(node, ast.Call):
            return
        dotted = _dotted(node.func)
        last = dotted.split(".")[-1]
        owner = self._owner()
        self.calls.setdefault(owner, set()).add(last)  # module-level calls are recorded under the file
        self._web_call(node, dotted, last)
        # env config
        if dotted in ("os.environ.get", "os.getenv", "environ.get", "getenv") and node.args and _const_str(node.args[0]):
            ckey = f"config:{_const_str(node.args[0])}"
            self.g.add(Node("config", ckey, name=_const_str(node.args[0])))
            self.g.link(owner, "configured_by", ckey)
        # LLM SDK calls / clients
        lower = dotted.lower()
        if (last in _LLM_ATTRS and any(h in lower for h in _LLM_HINTS)) or last in _LLM_CTORS:
            model = None
            for kw in node.keywords:
                if kw.arg in ("model", "model_name") and _const_str(kw.value):
                    model = _const_str(kw.value)
            mkey = f"model_call:{self.path}:{node.lineno}"
            self.g.add(Node("model_call", mkey, self.path, node.lineno, node.lineno, dotted, {"model": model}))
            self.g.link(owner, "uses_model", mkey)
        # agent frameworks
        if last in _AGENT_CTORS:
            name, model = None, None
            for kw in node.keywords:
                if kw.arg in ("name", "role") and _const_str(kw.value):
                    name = _const_str(kw.value)
                if kw.arg in ("model", "llm"):
                    model = _const_str(kw.value) or _dotted(kw.value) or None
            akey = f"agent:{self.path}:{node.lineno}"
            self.g.add(Node("agent", akey, self.path, node.lineno, getattr(node, "end_lineno", node.lineno),
                            name or last, {"framework_ctor": last, "model": model}))
            self.g.link(owner, "defines", akey)
        if last == "add_node" and len(node.args) >= 1 and _const_str(node.args[0]):
            akey = f"agent:{self.path}:{_const_str(node.args[0])}"
            self.g.add(Node("agent", akey, self.path, node.lineno, node.lineno, _const_str(node.args[0]),
                            {"framework_ctor": "StateGraph.add_node"}))
            self.g.link(owner, "defines", akey)


    # ── add_url_rule / add_api_route / Django urls / Streamlit / Gradio ──
    def _web_call(self, node: ast.Call, dotted: str, last: str) -> None:
        args, kw = node.args, {k.arg: k.value for k in node.keywords if k.arg}
        if last in ("add_url_rule", "add_api_route") and isinstance(node.func, ast.Attribute):
            path = _const_str(args[0]) if args else _const_str(kw.get("rule") or kw.get("path"))
            if path is None:
                return
            view = kw.get("view_func") or kw.get("endpoint")
            if view is None and len(args) >= (3 if last == "add_url_rule" else 2):
                view = args[2] if last == "add_url_rule" else args[1]
            methods = ["GET"]
            mexpr = kw.get("methods")
            if isinstance(mexpr, (ast.List, ast.Tuple, ast.Set)):
                methods = [str(_const_str(e)).upper() for e in mexpr.elts if _const_str(e)] or ["GET"]
            key, name = self._local_symbol(view)
            prefix = self.router_prefix.get(_dotted(node.func.value), "")
            for m in methods:
                self._route(m, (prefix + path) or "/", node.lineno, key, None if key else name)
        elif (self.is_urls and last in _DJANGO_ROUTES and len(args) >= 2 and _const_str(args[0]) is not None
              and dotted in (_DJANGO_ROUTES | {"django.urls.path", "django.urls.re_path", "urls.path"})):
            url = "/" + (_const_str(args[0]) or "").lstrip("^").rstrip("$")
            view = args[1]
            if isinstance(view, ast.Call) and _dotted(view.func) == "include":
                return
            if isinstance(view, ast.Call) and isinstance(view.func, ast.Attribute) and view.func.attr == "as_view":
                view = view.func.value
            key, name = self._local_symbol(view)
            self._route("ANY", url, node.lineno, key, None if key else name, "django")
        elif self.st_alias and dotted.split(".")[0] in self.st_alias:
            label = _const_str(args[0]) if args else _const_str(kw.get("label"))
            if last in _STREAMLIT_INPUTS:
                self.ui_fields.append({"tag": last, "label": label or last, "required": False})
                self.ui_lines.append(node.lineno)
            elif last in _STREAMLIT_BUTTONS:
                self.ui_buttons.append(label or last)
                self.ui_lines.append(node.lineno)
        elif self.gr_alias and ((dotted.split(".")[0] in self.gr_alias and last in _GRADIO_APPS)
                                or (last in _GRADIO_EVENTS and isinstance(node.func, ast.Attribute))):
            fn = kw.get("fn") or (args[0] if args else None)
            if not isinstance(fn, (ast.Name, ast.Attribute)):
                return
            _, name = self._local_symbol(fn)
            if name:
                self.gradio_handlers.append((node.lineno, name))
            self.ui_lines.append(node.lineno)
            inputs = kw.get("inputs")
            for e in (inputs.elts if isinstance(inputs, (ast.List, ast.Tuple)) else [inputs] if inputs is not None else []):
                tag = _const_str(e) or _dotted(e).split(".")[-1]
                if tag:
                    self.ui_fields.append({"tag": tag.lower(), "label": tag, "required": False})

    def finish_ui(self) -> None:
        """Streamlit / Gradio script → page (entry) + form whose submit reaches the script body and handlers."""
        if not (self.ui_lines and (self.st_alias or self.gr_alias)):
            return
        framework = "streamlit" if self.st_alias else "gradio"
        parts = self.path.split("/")
        url = "/"
        if framework == "streamlit" and len(parts) >= 2 and parts[-2] == "pages":  # multipage app
            stem = parts[-1].rsplit(".", 1)[0]
            head, _, tail = stem.partition("_")
            url = "/" + (tail if head.isdigit() and tail else stem)
        fkey = f"file:{self.path}"
        pkey = f"page:{normalize_route_path(url)}"
        self.g.add(Node("page", pkey, self.path, 1, None, url, {"path": url, "framework": framework}))
        self.g.link(pkey, "renders", fkey)
        form = f"form:{self.path}#{framework}"
        self.g.add(Node("form", form, self.path, min(self.ui_lines), max(self.ui_lines), f"{framework} app {parts[-1]}",
                        {"fields": self.ui_fields[:40], "buttons": [b for b in self.ui_buttons if b][:10],
                         "framework": framework}))
        self.g.link(pkey, "renders", form)
        self.g.link(form, "submits_to", fkey)  # the script body is what runs on submit
        for _, name in self.gradio_handlers:
            key = symbol_key(self.path, name)
            if key in self.g.nodes:
                self.g.link(form, "submits_to", key)
            else:
                self.g.nodes[form].props.setdefault("handler_names", []).append(name)


def parse_python(path: str, source: str, graph: Graph) -> Tuple[List[Chunk], Dict[str, Set[str]], Dict[str, Set[str]], Dict[str, str]]:
    """Returns (chunks, calls-by-symbol, name-refs-by-symbol, imports alias→module.name)."""
    graph.add(Node("file", f"file:{path}", path, 1, source.count("\n") + 1, path.rsplit("/", 1)[-1], {"lang": "python"}))
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return _window_chunks(path, source), {}, {}, {}
    lines = source.splitlines()
    imports: Dict[str, str] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            for a in n.names:
                imports[a.asname or a.name] = f"{n.module}.{a.name}"
        elif isinstance(n, ast.Import):
            for a in n.names:
                imports[a.asname or a.name.split(".")[0]] = a.name
    v = _FileVisitor(path, graph, lines, imports)
    v.visit(tree)
    v.finish_ui()

    chunks: List[Chunk] = []
    covered = set()
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = min([d.lineno for d in getattr(n, "decorator_list", [])] + [n.lineno])
            end = n.end_lineno or n.lineno
            if isinstance(n, ast.ClassDef) and end - start > 150:
                for m in n.body:
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        ms = min([d.lineno for d in m.decorator_list] + [m.lineno])
                        chunks.append(Chunk(path, ms, m.end_lineno, "\n".join(lines[ms - 1:m.end_lineno]), f"{n.name}.{m.name}"))
                        covered.update(range(ms, m.end_lineno + 1))
                continue
            chunks.append(Chunk(path, start, end, "\n".join(lines[start - 1:end]), n.name))
            covered.update(range(start, end + 1))
    # module-level code outside functions/classes (routes via add_url_rule, prompts, config)
    loose = [i for i in range(1, len(lines) + 1) if i not in covered and lines[i - 1].strip()]
    if loose:
        for c in _window_chunks(path, source, only_lines=set(loose)):
            chunks.append(c)
    return chunks, v.calls, v.name_refs, imports


def _window_chunks(path: str, source: str, size: int = 80, overlap: int = 10, only_lines: Optional[set] = None) -> List[Chunk]:
    lines = source.splitlines()
    out: List[Chunk] = []
    i = 0
    while i < len(lines):
        j = min(len(lines), i + size)
        if only_lines is None or any((k + 1) in only_lines for k in range(i, j)):
            text = "\n".join(lines[i:j])
            if text.strip():
                out.append(Chunk(path, i + 1, j, text))
        if j == len(lines):
            break
        i = j - overlap
    return out
