"""
generic_parser.py — pattern-based indexing for every source language without a dedicated parser.

Java, Kotlin, Scala, Groovy, Go, Rust, Ruby, PHP, C#, F#, Swift, Objective-C, Dart, C/C++, Elixir, Lua, R,
shell, CSS/SCSS, SQL, Prisma, GraphQL, Protobuf, Terraform …

Not a parser (tree-sitter is the upgrade path). It gives every fetched source file what traceability and the
review need: line-window chunks aligned to declarations (so BM25 retrieval and the secret scan see the code),
`symbol` nodes with line spans (functions, methods, classes; block ends by brace or `end` matching) and the call
names inside them (linked across files by indexer._link_calls), HTTP routes for the common frameworks (Spring,
ASP.NET, Go net/http + gin/echo/chi/fiber, actix/axum, Rails/Sinatra, Laravel/Symfony, Ktor, Vapor, shelf),
`test` nodes (JUnit/xUnit/NUnit/MSTest annotations, Go/Rust/Swift/PHP test functions, spec DSLs), and ORM/schema
tables (Prisma models, SQL CREATE TABLE).
"""

import re
from typing import Dict, List, Optional, Set, Tuple

from engines.repo_intel.model import Chunk, Graph, Node, normalize_route_path, symbol_key

_MOD = r"(?:(?:public|private|protected|internal|static|final|abstract|sealed|open|override|virtual|async|suspend|" \
       r"synchronized|inline|data|partial|readonly|extern|unsafe|default|external|operator|mutating|fileprivate|" \
       r"export|const|tailrec|lateinit)\s+)"

# (regex, kind) per language family; group 1 = name. Matched per line (re.M).
_JAVA_LIKE = [
    (re.compile(rf"^\s*(?:@\w+(?:\([^)]*\))?\s+)*{_MOD}*(?:class|interface|enum|record|object|struct|trait)\s+(\w+)", re.M), "class"),
    (re.compile(rf"^\s*(?:@\w+(?:\([^)]*\))?\s+)*{_MOD}*fun\s+(?:<[^>]+>\s*)?(?:[\w.]+\.)?(\w+)\s*\(", re.M), "function"),  # Kotlin
    (re.compile(rf"^\s*{_MOD}*def\s+(\w+)", re.M), "function"),  # Scala / Groovy
    (re.compile(rf"^\s*{_MOD}+(?:<[^>]+>\s+)?[\w<>\[\],.?]+(?:\s*<[^>]*>)?\s+(\w+)\s*\([^;{{}}]*\)\s*(?:throws\s+[\w., ]+)?\s*(?:\{{|=>|$)", re.M), "function"),
]
_PATTERNS: Dict[str, List[Tuple[re.Pattern, str]]] = {
    "java": _JAVA_LIKE, "kotlin": _JAVA_LIKE, "scala": _JAVA_LIKE, "groovy": _JAVA_LIKE, "csharp": _JAVA_LIKE,
    "fsharp": [(re.compile(r"^\s*(?:let|member)\s+(?:rec\s+|private\s+)?(?:\w+\.)?(\w+)", re.M), "function"),
               (re.compile(r"^\s*type\s+(\w+)", re.M), "class")],
    "go": [(re.compile(r"^func\s+(?:\([^)]*\)\s*)?(\w+)\s*[(\[]", re.M), "function"),
           (re.compile(r"^type\s+(\w+)\s+(?:struct|interface)\b", re.M), "class")],
    "rust": [(re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:const\s+)?(?:async\s+)?(?:unsafe\s+)?(?:extern\s+\"C\"\s+)?fn\s+(\w+)", re.M), "function"),
             (re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:struct|enum|trait|union)\s+(\w+)", re.M), "class"),
             (re.compile(r"^\s*impl(?:<[^>]*>)?\s+(?:[\w:<>]+\s+for\s+)?(\w+)", re.M), "class")],
    "ruby": [(re.compile(r"^\s*def\s+(?:self\.)?([\w?!=]+)", re.M), "function"),
             (re.compile(r"^\s*(?:class|module)\s+([\w:]+)", re.M), "class")],
    "php": [(re.compile(r"^\s*(?:(?:public|private|protected|static|final|abstract)\s+)*function\s+&?(\w+)", re.M), "function"),
            (re.compile(r"^\s*(?:(?:abstract|final|readonly)\s+)*(?:class|interface|trait|enum)\s+(\w+)", re.M), "class")],
    "swift": [(re.compile(rf"^\s*(?:@\w+\s+)*{_MOD}*(?:class\s+|static\s+)?func\s+(\w+)", re.M), "function"),
              (re.compile(rf"^\s*(?:@\w+\s+)*{_MOD}*(?:final\s+)?(?:class|struct|enum|protocol|extension|actor)\s+(\w+)", re.M), "class")],
    "objc": [(re.compile(r"^\s*[-+]\s*\([^)]*\)\s*(\w+)", re.M), "function"),
             (re.compile(r"^\s*@(?:interface|implementation|protocol)\s+(\w+)", re.M), "class")],
    "dart": [(re.compile(r"^\s*(?:abstract\s+|sealed\s+|base\s+|final\s+)*(?:class|mixin|enum|extension)\s+(\w+)", re.M), "class"),
             (re.compile(r"^\s*(?:static\s+|external\s+)?(?:Future(?:<[^>]*>)?|Stream(?:<[^>]*>)?|void|Widget|[A-Z]\w*(?:<[^>]*>)?\??|int|double|bool|String|dynamic)\s+(\w+)\s*\([^;{]*\)\s*(?:async\*?\s*)?(?:\{|=>)", re.M), "function")],
    "c": [(re.compile(r"^(?!\s*(?:if|for|while|switch|return|else|do|case)\b)(?:[\w:*&<>,]+[ \t]+)+[*&]*(~?\w+(?:::~?\w+)*)[ \t]*\([^;{}()]*\)[ \t]*(?:const[ \t]*)?(?:noexcept[ \t]*)?(?:override[ \t]*)?\{?[ \t]*$", re.M), "function"),
          (re.compile(r"^\s*(?:template\s*<[^>]*>\s*)?(?:class|struct|union|namespace)\s+(\w+)\s*(?:final\s*)?[:{]?", re.M), "class")],
    "elixir": [(re.compile(r"^\s*defp?\s+(\w+[?!]?)", re.M), "function"),
               (re.compile(r"^\s*defmodule\s+([\w.]+)", re.M), "class")],
    "erlang": [(re.compile(r"^(\w+)\s*\([^)]*\)\s*->", re.M), "function")],
    "lua": [(re.compile(r"^\s*(?:local\s+)?function\s+([\w.:]+)", re.M), "function")],
    "r": [(re.compile(r"^\s*([\w.]+)\s*(?:<-|=)\s*function\s*\(", re.M), "function")],
    "shell": [(re.compile(r"^\s*(?:function\s+)?([\w-]+)\s*\(\)\s*\{", re.M), "function"),
              (re.compile(r"^\s*function\s+([\w-]+)\s*\{", re.M), "function")],
    "clojure": [(re.compile(r"^\s*\(defn-?\s+([\w\-?!*]+)", re.M), "function")],
    "graphql": [(re.compile(r"^\s*(?:type|input|interface|enum)\s+(\w+)", re.M), "class")],
    "proto": [(re.compile(r"^\s*(?:message|service|enum)\s+(\w+)", re.M), "class"),
              (re.compile(r"^\s*rpc\s+(\w+)", re.M), "function")],
    "terraform": [(re.compile(r'^\s*(?:resource|data|module)\s+"([\w\-]+)"(?:\s+"([\w\-]+)")?', re.M), "class")],
}
_FAMILY = {
    ".java": "java", ".kt": "kotlin", ".kts": "kotlin", ".scala": "scala", ".groovy": "groovy", ".gradle": "groovy",
    ".cs": "csharp", ".fs": "fsharp", ".go": "go", ".rs": "rust", ".rb": "ruby", ".erb": "ruby", ".php": "php",
    ".swift": "swift", ".m": "objc", ".mm": "objc", ".dart": "dart",
    ".c": "c", ".h": "c", ".cc": "c", ".cpp": "c", ".cxx": "c", ".hpp": "c", ".hh": "c",
    ".ex": "elixir", ".exs": "elixir", ".erl": "erlang", ".lua": "lua", ".r": "r", ".clj": "clojure",
    ".sh": "shell", ".bash": "shell", ".graphql": "graphql", ".gql": "graphql", ".proto": "proto",
    ".tf": "terraform", ".hcl": "terraform",
}
_END_STYLE = {"ruby": "end", "elixir": "end", "lua": "end"}  # everything else: braces (or one line)
_NOT_NAMES = {"if", "for", "while", "switch", "catch", "return", "new", "else", "when", "match", "using", "lock",
              "foreach", "sizeof", "typeof", "defined", "elif", "until", "unless", "do", "try", "throw", "case", "main_"}
_KEYWORD_CALLS = _NOT_NAMES | {"function", "fn", "func", "def", "print", "println", "printf", "require", "include",
                              "super", "this", "self", "assert", "len", "make", "append", "panic", "Some", "Ok", "Err"}
_CALL = re.compile(r"\b([A-Za-z_]\w*)\s*(?:!\s*)?\(")

# ── routes ──
_HTTP = ("get", "post", "put", "patch", "delete")
_SPRING_CLASS = re.compile(r'@RequestMapping\(\s*(?:value\s*=\s*|path\s*=\s*)?\{?\s*"([^"]*)"')
_SPRING = re.compile(r'@(Get|Post|Put|Patch|Delete|Request)Mapping\b(?:\(\s*(?:value\s*=\s*|path\s*=\s*)?\{?\s*"([^"]*)")?([^\n]*)')
_ASPNET_CLASS = re.compile(r'\[Route\(\s*"([^"]*)"\s*\)\]')
_ASPNET = re.compile(r'\[Http(Get|Post|Put|Patch|Delete)(?:\(\s*"([^"]*)"\s*\))?\]')
_MINIMAL_API = re.compile(r'\.Map(Get|Post|Put|Patch|Delete)\(\s*"([^"]+)"\s*,\s*([\w.]+)?')
_GO_HANDLE = re.compile(r'\b(?:http|mux|\w*[Rr]outer|r|e|g|app|api|v1)\.Handle(?:Func)?\(\s*"([^"]+)"\s*,\s*([\w.]+)?')
_GO_FRAMEWORK = re.compile(r'\b(?:\w*[Rr]outer|r|e|g|app|api|v\d|group|grp|engine)\.(GET|POST|PUT|PATCH|DELETE|Get|Post|Put|Patch|Delete)\(\s*"(/[^"]*)"\s*,\s*(?:[\w.]+\s*,\s*)*([\w.]+)?')
_ACTIX = re.compile(r'#\[(get|post|put|patch|delete)\(\s*"([^"]+)"')
_AXUM = re.compile(r'\.route\(\s*"([^"]+)"\s*,\s*(get|post|put|patch|delete)\(\s*([\w:]+)')
_RAILS = re.compile(r'^\s*(get|post|put|patch|delete)\s+[\'"]([^\'"]+)[\'"](?:\s*,\s*to:\s*[\'"]([\w#/]+)[\'"])?', re.M)
_SINATRA = re.compile(r'^\s*(get|post|put|patch|delete)\s+[\'"](/[^\'"]*)[\'"]\s+do\b', re.M)
_LARAVEL = re.compile(r'Route::(get|post|put|patch|delete|any)\(\s*[\'"]([^\'"]+)[\'"](?:\s*,\s*\[?\s*([\w\\:]+)(?:::class)?(?:\s*,\s*[\'"](\w+)[\'"])?)?')
_SYMFONY = re.compile(r'#\[Route\(\s*[\'"]([^\'"]+)[\'"](?:[^\]]*methods:\s*\[\s*[\'"](\w+))?')
_KTOR = re.compile(r'^\s*(get|post|put|patch|delete)\s*\(\s*"(/[^"]*)"\s*\)\s*\{', re.M)
_VAPOR_DART = re.compile(r'\b(?:app|routes|router|api|protected|grouped)\.(get|post|put|patch|delete)\(\s*[\'"]([^\'"]*)[\'"]\s*(?:,\s*([\w.]+))?')

# ── tests ──
_TEST_ANNOTATION = re.compile(r"^\s*(?:@(?:Test|ParameterizedTest|RepeatedTest|TestFactory)\b|\[(?:Fact|Theory|Test|TestMethod|TestCase)\b|#\[(?:tokio::|async_std::)?test\])", re.M)
_TEST_DSL = re.compile(r"^\s*(?:it|test|specify|scenario|TEST|TEST_F|TEST_P)\s*\(?\s*(?:[\w]+\s*,\s*)?[\"']([^\"']{1,120})[\"']", re.M)
_TEST_PATH = re.compile(r"(^|/)(tests?|spec|__tests__|androidTest|testFixtures)(/|$)|(_test|_spec|Test|Tests|Spec)\.\w+$|(^|/)test_[^/]*$")

# ── schema ──
_PRISMA_MODEL = re.compile(r"^\s*model\s+(\w+)\s*\{", re.M)
_SQL_TABLE = re.compile(r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"\[]?(?:\w+[`\"\]]?\.)?[`\"\[]?(\w+)", re.I)


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def family_of(path: str) -> Optional[str]:
    ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
    return _FAMILY.get(ext)


def _block_end(lines: List[str], start: int, style: str) -> int:
    """1-based last line of the block opened at 1-based line `start` (best effort)."""
    n = len(lines)
    if style == "end":
        indent = len(lines[start - 1]) - len(lines[start - 1].lstrip())
        for i in range(start, min(n, start + 2000)):
            s = lines[i]
            if s.strip() and len(s) - len(s.lstrip()) <= indent and re.match(r"\s*end\b", s):
                return i + 1
        return start
    depth, opened = 0, False
    for i in range(start - 1, min(n, start + 3000)):
        line = re.sub(r"//.*$|\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])'", "", lines[i])
        for ch in line:
            if ch == "{":
                depth += 1
                opened = True
            elif ch == "}":
                depth -= 1
                if opened and depth <= 0:
                    return i + 1
        if not opened and (line.rstrip().endswith(";") or (i > start + 3)):
            return i + 1 if line.rstrip().endswith(";") else start  # declaration only / not a block
    return start


def parse_generic(path: str, source: str, graph: Graph) -> Tuple[List[Chunk], Dict[str, Set[str]]]:
    """Returns (chunks, calls-by-symbol) for indexer._link_calls."""
    fam = family_of(path)
    lines = source.splitlines()
    fkey = f"file:{path}"
    graph.add(Node("file", fkey, path, 1, max(1, len(lines)), path.rsplit("/", 1)[-1], {"lang": fam or "text"}))
    calls: Dict[str, Set[str]] = {}

    # ── symbols with spans ──
    found: Dict[int, Tuple[str, str]] = {}  # line → (name, kind)
    for rx, kind in _PATTERNS.get(fam or "", []):
        for m in rx.finditer(source):
            gi = next((i for i, g in enumerate(m.groups(), 1) if g), None)
            name = m.group(gi) if gi else None
            if not name or name in _NOT_NAMES or len(name) < 2:
                continue
            line = _line_of(source, m.start(gi))
            found.setdefault(line, (name, kind))
    style = _END_STYLE.get(fam or "", "brace")
    spans: List[Tuple[int, int, str, str]] = []
    for line in sorted(found):
        name, kind = found[line]
        end = _block_end(lines, line, style) if fam not in ("terraform", "graphql", "proto") else _block_end(lines, line, "brace")
        spans.append((line, max(end, line), name, kind))

    def enclosing_class(line: int, end: int) -> Optional[str]:
        best = None
        for s, e, n, k in spans:
            if k == "class" and s < line and end <= e and (best is None or s > best[0]):
                best = (s, n)
        return best[1] if best else None

    sym_at: List[Tuple[int, int, str]] = []  # (start, end, key) for routes/tests to attach to
    is_test_file = bool(_TEST_PATH.search(path))
    annotated_tests = {_line_of(source, m.start()) for m in _TEST_ANNOTATION.finditer(source)}
    for s, e, name, kind in spans:
        owner = enclosing_class(s, e) if kind == "function" else None
        qual = f"{owner}.{name}" if owner else name
        key = symbol_key(path, qual)
        graph.add(Node("symbol", key, path, s, e, qual, {"symbol_kind": kind, "lang": fam}))
        graph.link(fkey, "defines", key)
        sym_at.append((s, e, key))
        if kind == "function":
            body = "\n".join(lines[s - 1:e])
            calls[key] = {c for c in _CALL.findall(body) if c not in _KEYWORD_CALLS and c != name}
            preceded = any(s - 4 <= a < s for a in annotated_tests)
            if preceded or (is_test_file and re.match(r"(?i)test", name)):
                tkey = f"test:{path}#{qual}"
                graph.add(Node("test", tkey, path, s, e, qual, {"framework": fam}))
                graph.link(tkey, "defines", key)

    def symbol_after(line: int) -> Optional[str]:
        """Handler of an annotation/attribute on `line`: the first function starting within the next 6 lines."""
        for s, e, key in sym_at:
            if line <= s <= line + 6 and graph.nodes[key].props.get("symbol_kind") == "function":
                return key
        return None

    def symbol_containing(line: int) -> Optional[str]:
        best = None
        for s, e, key in sym_at:
            if s <= line <= e and (best is None or s > best[0]):
                best = (s, key)
        return best[1] if best else None

    def route(method: str, url: str, line: int, framework: str, handler_key: Optional[str] = None,
              handler_name: Optional[str] = None) -> None:
        method = method.upper()
        method = "ANY" if method in ("REQUEST", "ANY", "ALL") else method
        if not url.startswith("/"):
            url = "/" + url
        rkey = f"route:{method} {normalize_route_path(url)}"
        props = {"method": method, "path": url, "framework": framework}
        if handler_key:
            props["handler"] = handler_key
        elif handler_name:
            props["handler_name"] = handler_name.split(".")[-1].split("::")[-1].split("#")[-1].split("@")[-1]
        graph.add(Node("route", rkey, path, line, line, f"{method} {url}", props))
        graph.link(rkey, "exposes", handler_key or fkey)

    if fam in ("java", "kotlin", "scala", "groovy"):
        prefix_m = _SPRING_CLASS.search(source)
        class_line = min((s for s, e, n, k in spans if k == "class"), default=0)
        prefix = prefix_m.group(1) if prefix_m and _line_of(source, prefix_m.start()) <= class_line + 1 else ""
        for m in _SPRING.finditer(source):
            line = _line_of(source, m.start())
            if m.group(1) == "Request" and line <= class_line + 1:
                continue  # the class-level prefix
            method = m.group(1)
            if method == "Request":
                mm = re.search(r"RequestMethod\.(\w+)", m.group(3) or "")
                method = mm.group(1) if mm else "ANY"
            route(method, (prefix.rstrip("/") + "/" + (m.group(2) or "").lstrip("/")).rstrip("/") or "/", line,
                  "spring", symbol_after(line))
    if fam == "kotlin":
        for m in _KTOR.finditer(source):
            line = _line_of(source, m.start())
            route(m.group(1), m.group(2), line, "ktor", symbol_containing(line))
    if fam == "csharp":
        prefix_m = _ASPNET_CLASS.search(source)
        prefix = (prefix_m.group(1) if prefix_m else "")
        ctrl = re.search(r"class\s+(\w+?)Controller\b", source)
        if ctrl:
            prefix = prefix.replace("[controller]", ctrl.group(1).lower())
        for m in _ASPNET.finditer(source):
            line = _line_of(source, m.start())
            route(m.group(1), (prefix.rstrip("/") + "/" + (m.group(2) or "").lstrip("/")).rstrip("/") or "/", line,
                  "aspnet", symbol_after(line))
        for m in _MINIMAL_API.finditer(source):
            route(m.group(1), m.group(2), _line_of(source, m.start()), "aspnet-minimal", handler_name=m.group(3))
    if fam == "go":
        for m in _GO_HANDLE.finditer(source):
            pattern = m.group(1)
            method, _, url = pattern.partition(" ") if " " in pattern else ("ANY", "", pattern)
            route(method, url, _line_of(source, m.start()), "net/http", handler_name=m.group(2))
        for m in _GO_FRAMEWORK.finditer(source):
            route(m.group(1), m.group(2), _line_of(source, m.start()), "go-router", handler_name=m.group(3))
    if fam == "rust":
        for m in _ACTIX.finditer(source):
            line = _line_of(source, m.start())
            route(m.group(1), m.group(2), line, "actix", symbol_after(line))
        for m in _AXUM.finditer(source):
            route(m.group(2), m.group(1), _line_of(source, m.start()), "axum", handler_name=m.group(3))
    if fam == "ruby":
        for m in _RAILS.finditer(source):
            if path.endswith("routes.rb"):
                to = m.group(3) or ""
                route(m.group(1), m.group(2), _line_of(source, m.start()), "rails",
                      handler_name=to.split("#")[-1] if "#" in to else None)
        for m in _SINATRA.finditer(source):
            line = _line_of(source, m.start())
            route(m.group(1), m.group(2), line, "sinatra")
    if fam == "php":
        for m in _LARAVEL.finditer(source):
            route(m.group(1), m.group(2), _line_of(source, m.start()), "laravel", handler_name=m.group(4) or None)
        for m in _SYMFONY.finditer(source):
            line = _line_of(source, m.start())
            route(m.group(2) or "ANY", m.group(1), line, "symfony", symbol_after(line))
    if fam in ("swift", "dart"):
        for m in _VAPOR_DART.finditer(source):
            line = _line_of(source, m.start())
            route(m.group(1), m.group(2), line, "vapor" if fam == "swift" else "shelf", handler_name=m.group(3))

    # ── tests written as DSL calls (RSpec, Dart test, gtest, Kotest …) ──
    if is_test_file:
        for m in _TEST_DSL.finditer(source):
            line = _line_of(source, m.start())
            tkey = f"test:{path}#{m.group(1)[:80]}"
            graph.add(Node("test", tkey, path, line, line, m.group(1)[:80], {"framework": fam or "dsl"}))
            graph.link(tkey, "tests", fkey)
        if not any(n.kind == "test" for n in graph.in_file(path)):
            tkey = f"test:{path}"
            graph.add(Node("test", tkey, path, 1, len(lines), path.rsplit("/", 1)[-1], {"framework": fam or "file"}))
            graph.link(tkey, "tests", fkey)

    # ── tables ──
    for rx in (_PRISMA_MODEL, _SQL_TABLE):
        for m in rx.finditer(source):
            line = _line_of(source, m.start())
            tkey = f"table:{m.group(1)}"
            graph.add(Node("table", tkey, path, line, _block_end(lines, line, "brace"), m.group(1)))
            graph.link(fkey, "defines", tkey)

    return span_chunks(path, lines, [s for s, e, n, k in spans if enclosing_class(s, e) is None],
                       {s: n for s, e, n, k in spans}), calls


def span_chunks(path: str, lines: List[str], starts: List[int], names: Dict[int, str],
                max_lines: int = 100) -> List[Chunk]:
    """Chunks aligned to top-level declarations (annotations / comments right above stay with them), long ones split
    into windows, tiny neighbours merged. Each chunk is labelled with the declaration it starts at (or is inside)."""
    n = len(lines)
    if n == 0:
        return []
    bounds = set()
    for s in starts:
        b = s
        while b > 1 and re.match(r"\s*(@|\[|#\[|//|/\*|\*|#(?!include))", lines[b - 2]) and s - b < 8:
            b -= 1
        bounds.add(b)
    bounds = sorted(bounds | {1})
    edges = bounds + [n + 1]
    out: List[Chunk] = []
    label_lines = sorted(names)

    def label(a: int, b: int) -> Optional[str]:
        inside = [ln for ln in label_lines if a <= ln <= b]
        if inside:
            return names[inside[0]]
        before = [ln for ln in label_lines if ln < a]
        return names[before[-1]] if before else None

    for a, b in zip(edges, edges[1:]):
        s = a
        while s < b:
            e = min(b - 1, s + max_lines - 1)
            text = "\n".join(lines[s - 1:e])
            if text.strip():
                out.append(Chunk(path, s, e, text, label(s, e)))
            s = e + 1
    merged: List[Chunk] = []
    for c in out:
        if merged and (c.end_line - c.start_line) < 6 and (merged[-1].end_line - merged[-1].start_line) < 60 \
                and merged[-1].end_line + 1 == c.start_line:
            last = merged[-1]
            merged[-1] = Chunk(path, last.start_line, c.end_line, last.content + "\n" + c.content, last.symbol or c.symbol)
        else:
            merged.append(c)
    return merged
