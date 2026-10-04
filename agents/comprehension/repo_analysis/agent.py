"""
RepoAnalysisAgent — builds an application profile ("agent_profile", kept for compatibility) from the repository.

One Gemini call over the file tree plus a prioritised digest of the most informative files (README, dependency
manifests, entry points, prompts), all fenced as untrusted content. The application may be an AI agent, a chatbot,
a form app, a document generator, a dashboard, an API, a CLI or a library. The profile says what it is for (drives
BRD generation and test design) and how to reach it once deployed (drives the live execution fallback).

If the LLM call fails the run continues: the step returns `partial` with a minimal profile built deterministically
from the repository (name, README first paragraph, detected frameworks, routes) and the `error`.
`observed_risks` are passed on to RepositoryReviewAgent as hints to verify in the code.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.base_agent import BaseAgent
from agents.comprehension.repo_analysis.prompt import APP_PROFILE_SCHEMA, INTERFACE_TYPES, REPO_ANALYSIS_PROMPT
from agents.comprehension.repo_analysis.skills import SKILLS
from agents.comprehension.repo_analysis.tools import (
    UNTRUSTED_RULE,
    build_code_digest,
    fence_untrusted,
    find_brd_candidates,
    generate_json,
    scan_repo,
)
from connectors.connector_registry import ConnectorRegistry
from tools.shared import get_logger

_PROFILE_DEFAULTS: Dict[str, Any] = {
    "agent_name": None, "purpose": "", "domain": None, "target_users": [], "capabilities": [],
    "out_of_scope": [], "tools_and_integrations": [], "llm_providers": [], "tech_stack": [],
    "system_prompt_summary": None, "interface": {"type": "unknown", "endpoints": []},
    "entry_points": [], "run_command": None, "observed_risks": [],
}

# dependency name → (framework label, interface type it suggests)
_FRAMEWORKS = {
    "fastapi": ("fastapi", "http_api"), "flask": ("flask", "http_api"), "django": ("django", "web_form_app"),
    "streamlit": ("streamlit", "web_chat_ui"), "gradio": ("gradio", "web_chat_ui"), "chainlit": ("chainlit", "web_chat_ui"),
    "express": ("express", "http_api"), "@nestjs/core": ("nestjs", "http_api"), "next": ("nextjs", "unknown"),
    "react": ("react", "unknown"), "vue": ("vue", "unknown"), "svelte": ("svelte", "unknown"),
    "langchain": ("langchain", None), "openai": ("openai", None), "anthropic": ("anthropic", None),
    "google-generativeai": ("gemini", None), "google-genai": ("gemini", None), "@google/generative-ai": ("gemini", None),
    "python-docx": ("python-docx", "document_generator"), "docx": ("docx", "document_generator"),
    "reportlab": ("reportlab", "document_generator"), "pdfkit": ("pdfkit", "document_generator"),
    "plotly": ("plotly", "dashboard"), "dash": ("dash", "dashboard"), "chart.js": ("chart.js", "dashboard"),
    "recharts": ("recharts", "dashboard"), "click": ("click", "cli"), "typer": ("typer", "cli"),
}
_ROUTE_PATTERNS = [
    re.compile(r"@\w+\.(get|post|put|patch|delete)\(\s*[\"']([^\"']+)[\"']"),
    re.compile(r"\b(?:app|server|fastify|\w*[Rr]outer)\.(get|post|put|patch|delete)\(\s*[`\"']([^`\"']+)[`\"']"),
    re.compile(r"@\w+\.route\(\s*[\"']([^\"']+)[\"']"),
]


class RepoAnalysisAgent(BaseAgent):
    MODULE_NAME = "repo_analysis"

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self._registry = ConnectorRegistry(self.settings)
        self.logger = get_logger("agent.repo_analysis")

    def execute(self, request: dict, state: dict) -> Dict[str, Any]:
        emit = request.get("emit") or (lambda *a, **k: None)
        # repo_tree = full file list when RepoFetchAgent fetched only a subset of a large repo
        scan = scan_repo(Path(request["repo_dir"]), all_paths=request.get("repo_tree"))
        if scan.total_files == 0:
            return {"module": self.MODULE_NAME, "status": "failed", "blocking": True,
                    "error": "The repository is empty — there is no code to evaluate."}

        languages = ", ".join(
            f"{k} ({v})" for k, v in sorted(scan.languages.items(), key=lambda kv: -kv[1])
        ) or "unknown"
        brd_candidates = find_brd_candidates(scan)
        digest = build_code_digest(scan, exclude=brd_candidates)
        emit(f"Scanned {scan.total_files} files ({languages}); sending {len(digest) // 1000}k chars of code to Gemini.")
        if brd_candidates:
            emit(f"Possible requirement documents: {', '.join(brd_candidates[:5])}")

        meta = request.get("repo_metadata") or {}
        prompt = REPO_ANALYSIS_PROMPT.substitute(
            skill_header=SKILLS["repo_analysis"].header(),
            untrusted_rule=UNTRUSTED_RULE,
            languages=languages,
            live_url=request.get("live_url") or "(not deployed)",
            repo_info=fence_untrusted("repository", f"{request.get('repo_full_name', '')}\n"
                                                    f"{meta.get('description') or '(no description)'}"),
            file_tree=fence_untrusted("repository", scan.tree()),
            code_digest=fence_untrusted("repository", digest or "(no readable text files)"),
        )
        base = {"module": self.MODULE_NAME, "code_digest": digest, "file_tree": scan.tree(), "brd_candidates": brd_candidates}
        try:
            llm = self._registry.get_llm(request.get("connector_mode"))
            profile = generate_json(llm, prompt, expected_type=dict, schema=APP_PROFILE_SCHEMA)
        except Exception as exc:
            error = f"Gemini could not analyse the repository: {exc}"
            profile = _fallback_profile(request, scan, digest)
            emit(f"{error}. Continuing with a minimal profile built from the code "
                 f"({profile['interface']['type']}, {len(profile['interface']['endpoints'])} route(s)).", "warning")
            return {**base, "status": "partial", "error": error, "agent_profile": profile}

        profile = _normalise(profile, scan)
        iface = profile["interface"]
        endpoints = iface["endpoints"]
        emit(f"App purpose: {str(profile.get('purpose') or 'unclear')[:300]}", "success")
        main_ep = f" — {len(endpoints)} endpoint(s), main {endpoints[0].get('method', 'POST')} {endpoints[0].get('path')}" if endpoints else ""
        emit(f"Interface: {iface.get('type', 'unknown')} via {iface.get('framework', 'unknown')}{main_ep}")
        return {**base, "status": "success", "agent_profile": profile}


def _normalise(profile: Dict, scan) -> Dict:
    profile = {**_PROFILE_DEFAULTS, **(profile if isinstance(profile, dict) else {})}
    if not isinstance(profile.get("interface"), dict):
        profile["interface"] = dict(_PROFILE_DEFAULTS["interface"])
    iface = profile["interface"]
    if iface.get("type") not in INTERFACE_TYPES:
        iface["type"] = "unknown"
    endpoints = [e for e in iface.get("endpoints") or [] if isinstance(e, dict)]
    for ep in endpoints:  # structured output carries the example body as a JSON string
        raw = ep.pop("request_body_example_json", None)
        try:
            example = json.loads(raw) if raw else None
        except (TypeError, ValueError):
            example = None
        ep["request_body_example"] = example if isinstance(example, dict) else {}
    iface["endpoints"] = endpoints
    profile["languages"] = scan.languages
    profile["file_count"] = scan.total_files
    return profile


def _fallback_profile(request: dict, scan, digest: str) -> Dict:
    """A minimal, honest profile from the repository alone (no LLM): name, README first paragraph, frameworks, routes."""
    root = Path(request["repo_dir"])
    name = (request.get("repo_full_name") or root.name).rsplit("/", 1)[-1]
    readme = next((f for f in scan.files if f.lower().rsplit("/", 1)[-1] in ("readme.md", "readme.rst", "readme.txt", "readme")
                   and "/" not in f), None)
    purpose = (request.get("repo_metadata") or {}).get("description") or ""
    if readme:
        purpose = _first_paragraph(_read(root / readme)) or purpose
    deps = set(_dependencies(root, scan.files))
    frameworks = [label for dep, (label, _) in _FRAMEWORKS.items() if dep in deps]
    kinds = [kind for dep, (_, kind) in _FRAMEWORKS.items() if dep in deps and kind]
    routes = _routes(digest)
    iface_type = next((k for k in ("document_generator", "web_chat_ui", "dashboard", "web_form_app", "http_api", "cli")
                       if k in kinds), "http_api" if routes else "unknown")
    llms = [label for label in frameworks if label in ("openai", "anthropic", "gemini", "langchain")]
    profile = {**_PROFILE_DEFAULTS,
               "agent_name": name, "purpose": purpose[:800], "tech_stack": frameworks, "llm_providers": llms,
               "interface": {"type": iface_type,
                             "framework": next((f for f in frameworks if f not in ("openai", "anthropic", "gemini",
                                                                                  "langchain")), "unknown"),
                             "endpoints": [{"method": m.upper(), "path": p, "description": "", "request_body_example": {}}
                                           for m, p in routes[:20]],
                             "notes": "Built without the LLM (analysis failed): from manifests, README and route patterns."},
               "degraded": True}
    profile["languages"] = scan.languages
    profile["file_count"] = scan.total_files
    return profile


def _read(path: Path, limit: int = 20_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def _first_paragraph(text: str) -> str:
    for block in re.split(r"\n\s*\n", text):
        b = block.strip()
        if not b or b.startswith(("#", "!", "<", "[!", "```", "|", "---")) or len(b) < 30:
            continue
        return re.sub(r"\s+", " ", re.sub(r"[*_`]|\[([^\]]*)\]\([^)]*\)", r"\1", b))[:600]
    return ""


def _dependencies(root: Path, files: List[str]) -> List[str]:
    out: List[str] = []
    for f in files:
        name = f.rsplit("/", 1)[-1].lower()
        if name == "package.json":
            try:
                data = json.loads(_read(root / f, 200_000) or "{}")
                out += list((data.get("dependencies") or {}).keys()) + list((data.get("devDependencies") or {}).keys())
            except ValueError:
                pass
        elif name in ("requirements.txt", "pyproject.toml"):
            out += [m.group(1).lower() for m in re.finditer(r"(?m)^\s*\"?([A-Za-z0-9_.\-]+)", _read(root / f))]
    return out


def _routes(digest: str) -> List[tuple]:
    seen, out = set(), []
    for rx in _ROUTE_PATTERNS:
        for m in rx.finditer(digest or ""):
            method, path = (m.group(1), m.group(2)) if m.lastindex == 2 else ("GET", m.group(1))
            if path.startswith("/") and (method, path) not in seen:
                seen.add((method, path))
                out.append((method, path))
    return out
