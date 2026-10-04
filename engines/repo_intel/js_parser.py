"""
js_parser.py — pattern-based extraction for JavaScript/TypeScript and HTML.

Not a full parser (tree-sitter is the upgrade path); the patterns target what traceability
needs: HTTP routes (Express/Fastify/Hono/Koa routers on server receivers only — `app`, `server`,
`fastify`, `hono`, `*Router`/`*router` — never client calls such as `api.get`; NestJS controllers;
Next.js app & pages API routes), pages (Next.js, React-Router `<Route path>` / createBrowserRouter /
useRoutes objects, Vite/SPA entry points), React components and Vue/Svelte single-file components,
outbound API calls (fetch/axios/ky + template URLs), forms and their fields, buttons, download/export
actions, env vars, LLM SDK calls, prompt strings, and test files (Jest/Vitest/Mocha/Playwright/Cypress)
as `test` nodes with the relative modules they import (linked to those files by the indexer).
Chunks = top-level declarations, falling back to 120-line windows.
"""

import re
from typing import Dict, List, Set, Tuple

from engines.repo_intel.model import Chunk, Graph, Node, normalize_route_path

_ROUTER_CALL = re.compile(r"\b(app|server|fastify|hono|\w*[Rr]outer)\.(get|post|put|patch|delete|all|route)\(\s*[`'\"]([^`'\"]+)[`'\"]")
_NEST_CONTROLLER = re.compile(r"@Controller\(\s*(?:[`'\"]([^`'\"]*)[`'\"]|\{[^}]*?path:\s*[`'\"]([^`'\"]*)[`'\"][^}]*\})?\s*\)")
_NEST_ROUTE = re.compile(r"@(Get|Post|Put|Patch|Delete|All)\(\s*(?:[`'\"]([^`'\"]*)[`'\"])?\s*\)(?:\s*@\w+\([^)]*\))*\s*(?:public\s+|private\s+|protected\s+)?(?:async\s+)?(\w+)\s*\(")
_REACT_ROUTE = re.compile(r"<Route\b([^>]*?)\bpath\s*=\s*\{?\s*[`'\"]([^`'\"]*)[`'\"]([^>]*)>", re.S)
_ROUTE_ELEMENT = re.compile(r"(?:element\s*[=:]\s*\{?\s*<\s*(\w+)|[Cc]omponent\s*[=:]\s*\{?\s*(\w+))")
_ROUTE_OBJECT = re.compile(r"\{\s*path\s*:\s*[`'\"]([^`'\"]*)[`'\"]\s*,([^{}]*(?:<[^{}]*>)?[^{}]*)")
_ROUTER_FACTORY = re.compile(r"\b(?:createBrowserRouter|createHashRouter|createMemoryRouter|useRoutes|createRouter|new\s+VueRouter)\s*\(")
_SPA_ENTRY = re.compile(r"\b(?:createRoot|hydrateRoot|ReactDOM\.render|createApp|new\s+Vue)\b|\bnew\s+\w+\(\s*\{\s*target\s*:")
_MODULE_SCRIPT = re.compile(r"<script\b[^>]*\btype\s*=\s*[\"']module[\"'][^>]*\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.I)
_TEST_FILE = re.compile(r"(\.(test|spec|cy|e2e)\.[cm]?[jt]sx?$)|(^|/)(__tests__|tests?|e2e|cypress|playwright)/", re.I)
_TEST_CASE = re.compile(r"^\s*(?:it|test|specify)(?:\.(?:only|skip|concurrent|each\([^)]*\)))?\s*\(\s*[`'\"]([^`'\"]{1,120})[`'\"]", re.M)
_IMPORT_REL = re.compile(r"(?:\bfrom\s+|\brequire\(\s*|\bimport\s*\(\s*|^\s*import\s+)[`'\"]((?:\.{1,2}|@|~)/[^`'\"]+)[`'\"]", re.M)
_FETCH = re.compile(r"\b(?:fetch|axios(?:\.(get|post|put|patch|delete))?|ky(?:\.(get|post|put|patch|delete))?|\$http\.(get|post))\(\s*[`'\"]([^`'\"]+)[`'\"](?:\s*,\s*\{[^}]*?method:\s*[`'\"](\w+)[`'\"])?", re.S)
_ENV = re.compile(r"\b(?:process\.env|import\.meta\.env)\.([A-Z][A-Z0-9_]+)")
_EXPORT_HTTP = re.compile(r"export\s+(?:async\s+)?(?:function|const)\s+(GET|POST|PUT|PATCH|DELETE)\b")
_COMPONENT = re.compile(r"^\s*export\s+(?:default\s+)?(?:async\s+)?function\s+([A-Z]\w*)|^\s*(?:export\s+)?const\s+([A-Z]\w*)\s*[:=][^=]*=>", re.M)
_JS_SYMBOL = re.compile(r"^\s*export\s+(?:default\s+)?(?:async\s+)?(?:function\s+(\w+)|class\s+(\w+)|(?:const|let)\s+(\w+)\s*=)", re.M)
_DECL = re.compile(r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function\s+\w+|class\s+\w+|const\s+\w+\s*=|let\s+\w+\s*=)", re.M)
_LLM = re.compile(r"\b(chat\.completions\.create|responses\.create|messages\.create|generateContent(?:Stream)?|generateText|streamText|generateObject|new\s+(?:OpenAI|Anthropic|GoogleGenerativeAI|GoogleGenAI|ChatOpenAI|ChatAnthropic))\b")
_MODEL_ID = re.compile(r"model\s*:\s*[`'\"]([\w.\-:/]+)[`'\"]")
_FORM = re.compile(r"<form\b([^>]*)>(.*?)</form>", re.S | re.I)
_FIELD = re.compile(r"<(input|textarea|select)\b([^>]*)/?>", re.I)
_ATTR = lambda name: re.compile(rf"\b{name}\s*=\s*[{{\"']([^\"'}}]+)", re.I)
_BUTTON = re.compile(r"<button\b[^>]*>(.*?)</button>", re.S | re.I)
_DOWNLOAD = re.compile(r"\b(download=|\.download\s*=|saveAs\(|Blob\(|createObjectURL|application/vnd\.openxmlformats|\.docx\b|\.pdf\b)", re.I)
_PROMPT_STR = re.compile(r"(?:const|let|var)\s+(\w*(?:PROMPT|SYSTEM|INSTRUCTION)\w*)\s*=\s*`", re.I)


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _next_route_path(path: str) -> Tuple[str, str]:
    """app/api/users/[id]/route.ts → ('route', '/api/users/[id]'); app/dashboard/page.tsx → ('page', '/dashboard')."""
    parts = path.split("/")
    try:
        i = len(parts) - 1 - parts[::-1].index("app")
    except ValueError:
        i = -1
    if i >= 0:
        segs = [s for s in parts[i + 1:-1] if not (s.startswith("(") and s.endswith(")"))]
        kind = "route" if parts[-1].startswith("route.") else "page"
        return kind, "/" + "/".join(segs)
    if "pages" in parts:  # pages router
        j = parts.index("pages")
        segs = parts[j + 1:]
        segs[-1] = re.sub(r"\.(t|j)sx?$", "", segs[-1])
        if segs[-1] == "index":
            segs = segs[:-1]
        kind = "route" if segs[:1] == ["api"] else "page"
        return kind, "/" + "/".join(segs)
    return "", ""


def parse_js(path: str, source: str, graph: Graph) -> Tuple[List[Chunk], List[Tuple[str, str, str]]]:
    """Returns (chunks, api_calls) where api_calls = [(owner_key, METHOD, url)] for linker.py."""
    lang = "html" if path.lower().endswith((".html", ".htm")) else "js"
    fkey = f"file:{path}"
    graph.add(Node("file", fkey, path, 1, source.count("\n") + 1, path.rsplit("/", 1)[-1], {"lang": lang}))
    owner = fkey
    name = path.rsplit("/", 1)[-1]

    # Next.js / pages-router files
    if re.match(r"(route|page)\.(t|j)sx?$", name) or "/pages/" in f"/{path}":
        kind, url = _next_route_path(path)
        if kind == "route":
            methods = _EXPORT_HTTP.findall(source) or (["GET", "POST"] if "/pages/" in f"/{path}" else [])
            for m in methods:
                rkey = f"route:{m} {normalize_route_path(url)}"
                graph.add(Node("route", rkey, path, 1, None, f"{m} {url}", {"method": m, "path": url, "framework": "nextjs"}))
                graph.link(rkey, "exposes", fkey)
        elif kind == "page":
            pkey = f"page:{normalize_route_path(url)}"
            graph.add(Node("page", pkey, path, 1, None, url or "/", {"path": url or "/"}))
            graph.link(pkey, "renders", fkey)
            owner = pkey

    for m in _ROUTER_CALL.finditer(source):
        method = m.group(2).upper()
        method = "GET" if method in ("ALL", "ROUTE") else method
        url = m.group(3)
        if not url.startswith("/"):
            continue
        rkey = f"route:{method} {normalize_route_path(url)}"
        graph.add(Node("route", rkey, path, _line_of(source, m.start()), None, f"{method} {url}",
                       {"method": method, "path": url, "framework": "js-router"}))
        graph.link(rkey, "exposes", fkey)

    _nest_routes(path, source, graph, fkey)
    owner = _client_pages(path, source, graph, fkey, owner)
    _tests(path, source, graph, fkey)
    if path.lower().endswith((".vue", ".svelte")):  # a single-file component is a component
        cname = re.sub(r"\W", "", name.rsplit(".", 1)[0].title().replace("-", "").replace("_", "")) or "Component"
        ckey = f"component:{path}#{cname}"
        graph.add(Node("component", ckey, path, 1, source.count("\n") + 1, cname, {"sfc": True}))
        graph.link(fkey, "defines", ckey)

    for m in _COMPONENT.finditer(source):
        cname = m.group(1) or m.group(2)
        ckey = f"component:{path}#{cname}"
        graph.add(Node("component", ckey, path, _line_of(source, m.start()), None, cname))
        graph.link(fkey, "defines", ckey)

    for m in _JS_SYMBOL.finditer(source):  # exported functions / classes / consts, for exact lookup
        sname = m.group(1) or m.group(2) or m.group(3)
        line = _line_of(source, m.start())
        skey = f"symbol:{path}#{sname}"
        graph.add(Node("symbol", skey, path, line, line, sname, {"symbol_kind": "class" if m.group(2) else "function"}))
        graph.link(fkey, "defines", skey)

    api_calls: List[Tuple[str, str, str]] = []
    for m in _FETCH.finditer(source):
        method = (m.group(1) or m.group(2) or m.group(3) or m.group(5) or "GET").upper()
        api_calls.append((owner, method, m.group(4)))

    for m in _ENV.finditer(source):
        ckey = f"config:{m.group(1)}"
        graph.add(Node("config", ckey, name=m.group(1)))
        graph.link(fkey, "configured_by", ckey)

    for m in _LLM.finditer(source):
        line = _line_of(source, m.start())
        window = source[m.start(): m.start() + 600]
        mm = _MODEL_ID.search(window)
        mkey = f"model_call:{path}:{line}"
        graph.add(Node("model_call", mkey, path, line, line, m.group(1), {"model": mm.group(1) if mm else None}))
        graph.link(fkey, "uses_model", mkey)

    for m in _PROMPT_STR.finditer(source):
        line = _line_of(source, m.start())
        pkey = f"prompt:{path}#{m.group(1)}"
        graph.add(Node("prompt", pkey, path, line, None, m.group(1)))
        graph.link(fkey, "defines", pkey)

    for i, m in enumerate(_FORM.finditer(source)):
        attrs, body = m.group(1), m.group(2)
        fields = []
        for f in _FIELD.finditer(body):
            fa = f.group(2)
            label = next((a.group(1) for a in (_ATTR("name").search(fa), _ATTR("placeholder").search(fa),
                                               _ATTR("id").search(fa), _ATTR("aria-label").search(fa)) if a), f.group(1))
            fields.append({"tag": f.group(1).lower(), "label": label, "required": "required" in fa.lower()})
        buttons = [re.sub(r"<[^>]+>|\{[^}]*\}", "", b).strip() for b in _BUTTON.findall(body)]
        action = _ATTR("action").search(attrs)
        fkey_form = f"form:{path}#{i}"
        graph.add(Node("form", fkey_form, path, _line_of(source, m.start()), _line_of(source, m.end()),
                       f"form {i + 1} in {name}", {"fields": fields[:40], "buttons": [b for b in buttons if b][:10]}))
        graph.link(owner, "renders", fkey_form)
        if action and action.group(1).startswith("/"):
            api_calls.append((fkey_form, "POST", action.group(1)))

    buttons = [re.sub(r"<[^>]+>|\{[^}]*\}", "", b).strip() for b in _BUTTON.findall(source)]
    if buttons or _DOWNLOAD.search(source):
        graph.nodes[fkey].props["ui_actions"] = [b for b in buttons if b][:30]
        if _DOWNLOAD.search(source):
            graph.nodes[fkey].props["produces_download"] = True

    return _decl_chunks(path, source), api_calls


def _nest_routes(path: str, source: str, graph: Graph, fkey: str) -> None:
    """NestJS: @Controller('prefix') + @Get(':id') handler(...) → route exposing the handler method."""
    ctrl = _NEST_CONTROLLER.search(source)
    if not ctrl and not re.search(r"@(?:Get|Post|Put|Patch|Delete)\(", source):
        return
    prefix = (ctrl.group(1) or ctrl.group(2) or "") if ctrl else ""
    cls = re.search(r"class\s+(\w+)", source[ctrl.end():] if ctrl else source)
    for m in _NEST_ROUTE.finditer(source):
        method = "GET" if m.group(1) == "All" else m.group(1).upper()
        url = "/" + "/".join(p.strip("/") for p in (prefix, m.group(2) or "") if p.strip("/"))
        line = _line_of(source, m.start())
        hname = f"{cls.group(1)}.{m.group(3)}" if cls else m.group(3)
        hline = _line_of(source, m.start(3))
        skey = f"symbol:{path}#{hname}"
        graph.add(Node("symbol", skey, path, hline, _brace_end(source, m.end()) or hline, hname,
                       {"symbol_kind": "function"}))
        graph.link(fkey, "defines", skey)
        rkey = f"route:{method} {normalize_route_path(url)}"
        graph.add(Node("route", rkey, path, line, line, f"{method} {url}",
                       {"method": method, "path": url, "framework": "nestjs", "handler": skey}))
        graph.link(rkey, "exposes", skey)


def _brace_end(source: str, pos: int) -> int:
    """Line of the `}` closing the first `{` at/after pos (0 if none within reach)."""
    i = source.find("{", pos, pos + 2000)
    if i < 0:
        return 0
    depth = 0
    for j in range(i, min(len(source), i + 200_000)):
        ch = source[j]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return _line_of(source, j)
    return 0


def _client_pages(path: str, source: str, graph: Graph, fkey: str, owner: str) -> str:
    """React-Router / Vue-Router route tables and SPA entry points → page nodes. Returns the new owner key."""
    def page(url: str, line: int, component: str = None, framework: str = "react-router") -> str:
        url = url if url.startswith("/") else "/" + url
        pkey = f"page:{normalize_route_path(url)}"
        props = {"path": url, "framework": framework}
        if component:
            props["component"] = component
        graph.add(Node("page", pkey, path, line, None, url, props))
        graph.link(pkey, "renders", fkey)
        return pkey

    for m in _REACT_ROUTE.finditer(source):
        el = _ROUTE_ELEMENT.search(m.group(1) + " " + m.group(3))
        page(m.group(2), _line_of(source, m.start()), (el.group(1) or el.group(2)) if el else None)
    if _ROUTER_FACTORY.search(source):
        for m in _ROUTE_OBJECT.finditer(source):
            el = _ROUTE_ELEMENT.search(m.group(2))
            page(m.group(1), _line_of(source, m.start()), (el.group(1) or el.group(2)) if el else None,
                 "vue-router" if "VueRouter" in source or "vue-router" in source else "react-router")
    name = path.rsplit("/", 1)[-1].lower()
    if _SPA_ENTRY.search(source) and re.match(r"(main|index|app|entry|client)\.[cm]?[jt]sx?$", name):
        return page("/", 1, framework="spa-entry")
    if name in ("index.html", "index.htm"):
        script = _MODULE_SCRIPT.search(source)
        if script:
            pkey = page("/", 1, framework="spa-entry")
            graph.nodes[pkey].props.setdefault("entry_script", script.group(1).lstrip("./"))
            return pkey
    return owner


def _tests(path: str, source: str, graph: Graph, fkey: str) -> None:
    """Jest / Vitest / Mocha / Playwright / Cypress test files → test nodes + the relative modules they import."""
    if not _TEST_FILE.search(path) or path.lower().endswith((".html", ".htm")):
        return
    imports = sorted({m.group(1) for m in _IMPORT_REL.finditer(source)})
    cases = list(_TEST_CASE.finditer(source))
    for m in cases:
        tkey = f"test:{path}#{m.group(1)[:80]}"
        graph.add(Node("test", tkey, path, _line_of(source, m.start()), None, m.group(1)[:80],
                       {"framework": "js", "imports": imports}))
        graph.link(tkey, "tests", fkey)
    if not cases:
        tkey = f"test:{path}"
        graph.add(Node("test", tkey, path, 1, source.count("\n") + 1, path.rsplit("/", 1)[-1],
                       {"framework": "js", "imports": imports}))
        graph.link(tkey, "tests", fkey)


def _decl_chunks(path: str, source: str, max_lines: int = 120) -> List[Chunk]:
    lines = source.splitlines()
    starts = sorted({_line_of(source, m.start()) for m in _DECL.finditer(source)})
    if not starts:
        starts = [1]
    if starts[0] != 1:
        starts = [1] + starts
    bounds = starts + [len(lines) + 1]
    chunks: List[Chunk] = []
    for a, b in zip(bounds, bounds[1:]):
        # split long declarations into windows so one chunk never dwarfs the retrieval budget
        s = a
        while s < b:
            e = min(b - 1, s + max_lines - 1)
            text = "\n".join(lines[s - 1:e])
            if text.strip():
                m = re.search(r"(?:function|class|const|let)\s+(\w+)", lines[s - 1]) if s - 1 < len(lines) else None
                chunks.append(Chunk(path, s, e, text, m.group(1) if m else None))
            s = e + 1
    # merge tiny neighbours (imports, one-line consts) to keep the chunk count sane
    merged: List[Chunk] = []
    for c in chunks:
        if merged and (c.end_line - c.start_line) < 6 and (merged[-1].end_line - merged[-1].start_line) < 60:
            last = merged[-1]
            merged[-1] = Chunk(path, last.start_line, c.end_line, last.content + "\n" + c.content, last.symbol)
        else:
            merged.append(c)
    return merged
