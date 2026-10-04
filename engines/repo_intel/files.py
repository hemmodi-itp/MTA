"""
files.py — the one definition of which repository files the evaluation fetches, indexes and skips.

Shared by tools/agent_eval/repo_scan.py (what RepoFetchAgent downloads, what RepoAnalysisAgent reads) and
engines/repo_intel/indexer.py (what Repository Intelligence parses), so the fetcher never downloads a file the
indexer would silently ignore, and coverage numbers from both sides add up.
"""

from pathlib import PurePosixPath
from typing import Optional

# Directories never fetched or indexed (vendored code, build output, caches). Hidden directories are skipped too.
SKIP_DIRS = frozenset({
    ".git", "node_modules", ".venv", "venv", "env", "__pycache__", ".mypy_cache", ".pytest_cache",
    "dist", "build", ".next", ".nuxt", ".svelte-kit", "out", "coverage", ".idea", ".vscode", "site-packages", ".tox",
    "target", "bin", "obj", ".gradle", ".terraform", "vendor", ".cache", "htmlcov", ".ipynb_checkpoints", "Pods",
    ".dart_tool", "DerivedData", "bower_components", "jspm_packages",
})

MAX_FILE_BYTES = 400_000          # a single file above this is not fetched / indexed (generated or data)
MAX_FILES = 1200                  # files fetched per repository (and the indexer's cap on parsed files)
MAX_FETCH_BYTES = 10 * 1024 * 1024
MAX_ZIP_MEMBERS = 200_000         # zip fallback: refuse archives listing more entries than this
MAX_ZIP_BYTES = 500 * 1024 * 1024  # zip fallback: refuse archives that decompress to more than this

# Language of every source extension the indexer parses (BM25, secret scan and graph see all of them).
LANG_BY_EXT = {
    ".py": "Python", ".pyi": "Python",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".mts": "TypeScript", ".cts": "TypeScript",
    ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".vue": "Vue", ".svelte": "Svelte", ".astro": "Astro",
    ".html": "HTML", ".htm": "HTML",
    ".css": "CSS", ".scss": "SCSS", ".sass": "Sass", ".less": "Less",
    ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin", ".scala": "Scala", ".groovy": "Groovy", ".gradle": "Gradle",
    ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".erb": "Ruby", ".php": "PHP", ".cs": "C#", ".fs": "F#",
    ".swift": "Swift", ".m": "Objective-C", ".mm": "Objective-C", ".dart": "Dart",
    ".c": "C", ".h": "C", ".cc": "C++", ".cpp": "C++", ".cxx": "C++", ".hpp": "C++", ".hh": "C++",
    ".ex": "Elixir", ".exs": "Elixir", ".erl": "Erlang", ".clj": "Clojure", ".lua": "Lua", ".r": "R",
    ".sh": "Shell", ".bash": "Shell", ".ps1": "PowerShell",
    ".sql": "SQL", ".prisma": "Prisma", ".graphql": "GraphQL", ".gql": "GraphQL", ".proto": "Protobuf",
    ".tf": "Terraform", ".hcl": "Terraform",
}
SOURCE_EXT = frozenset(LANG_BY_EXT)

DOC_EXT = frozenset({".md", ".mdx", ".rst", ".txt"})
CONFIG_EXT = frozenset({".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".properties", ".xml", ".env.example",
                        ".prompt", ".j2", ".jinja", ".ipynb", ".csproj", ".sln"})
TEXT_EXT = SOURCE_EXT | DOC_EXT | CONFIG_EXT

# Recognised by name (no useful extension).
KEY_FILE_NAMES = frozenset({
    "readme.md", "readme.rst", "readme.txt", "readme", "requirements.txt", "pyproject.toml", "package.json",
    "setup.py", "dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yaml", "procfile", "app.json",
    "langgraph.json", "vercel.json", "render.yaml", "fly.toml", ".env.example", ".env.sample", ".env.template",
    "agents.md", "claude.md", "makefile", "gemfile", "go.mod", "cargo.toml", "pom.xml", "build.gradle",
    "build.gradle.kts", "settings.gradle", "composer.json", "pubspec.yaml", "package.swift",
})
NAMED_TEXT_FILES = frozenset({"dockerfile", "procfile", "makefile", "gemfile", "requirements.txt"})
LOCK_OR_MINIFIED = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "cargo.lock", "gemfile.lock",
                    "composer.lock", "go.sum", ".min.js", ".min.css", ".map")


def ext_of(rel: str) -> str:
    """Extension used for selection: `.env.example` (and .sample/.template) counts as one extension."""
    name = rel.rsplit("/", 1)[-1].lower()
    if name.startswith(".env.") and name.split(".")[-1] in ("example", "sample", "template", "dist"):
        return ".env.example"
    return PurePosixPath(name).suffix


def language_of(rel: str) -> Optional[str]:
    return LANG_BY_EXT.get(ext_of(rel))


def is_skipped(rel: str) -> bool:
    """True if any directory in the path is vendored/build/hidden."""
    return any(part in SKIP_DIRS or part.startswith(".") for part in rel.split("/")[:-1])


def is_lock_or_minified(rel: str) -> bool:
    return rel.lower().endswith(LOCK_OR_MINIFIED)


def is_text_candidate(rel: str) -> bool:
    """A file the evaluation can read: known text/code extension or a key file by name."""
    name = rel.rsplit("/", 1)[-1].lower()
    return ext_of(rel) in TEXT_EXT or name in KEY_FILE_NAMES or name in NAMED_TEXT_FILES


def skip_reason(rel: str, size: Optional[int] = None) -> Optional[str]:
    """Why a file is never fetched or indexed, or None if it is eligible. Reasons are coverage-report keys."""
    if is_skipped(rel):
        return "vendored_or_hidden"
    if is_lock_or_minified(rel):
        return "lockfile_or_minified"
    if not is_text_candidate(rel):
        return "unsupported_type"
    if size is not None and size > MAX_FILE_BYTES:
        return "too_large"
    if size is not None and size <= 0:
        return "empty"
    return None
