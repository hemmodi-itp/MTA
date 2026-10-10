"""
BrdBuilderAgent — decides which BRD a run is judged against, then extracts its requirements.

  * User gave a BRD path (repo-relative or a full GitHub blob/raw URL): that document and only
    that document is used. If it's missing or unreadable, the run stops with a clear error —
    it never silently switches to a different file.
  * No path, BRD modes (brd_and_live, brd_only): the OPENING of each auto-detected candidate is read
    and Gemini picks the one that is actually this agent's BRD (repos often also carry TSDs, one-pagers
    or other products' BRDs); only the chosen document is then read in full. None matches → a BRD is
    generated (from the live app if there is one).
  * live_only: the BRD is generated from evidence about the live app. RuntimeDiscoveryAgent runs first
    (authenticated, with the project's test account), so its `runtime_profile` (pages, forms and field
    labels, buttons, downloads, chat box, API calls) is the evidence; the app is crawled here only when
    that profile is absent or shows nothing usable. The agent's answers about itself are claims, never
    requirement evidence on their own. The README is only supporting context.

Documents without a usable text layer (scanned / outlined-font PDFs) are read visually by Gemini.
Requirements must carry a verbatim source_quote that is machine-checked against the BRD text;
untraceable ones are dropped. Each acceptance criterion is checked for token overlap with the BRD
(`grounded`); ungrounded ones stay, with lower confidence, and are reported. Requirements from a BRD
MTA generated itself are `self_generated` (their quotes only prove MTA quoted MTA) and capped at
confidence 0.6. Every cap (requirements, criteria, BRD length, evidence size) is reported in
`limitations`, never applied silently.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agents.base_agent import BaseAgent
from agents.comprehension.brd_builder.prompt import (
    BRD_FROM_CODE_PROMPT,
    BRD_FROM_LIVE_PROMPT,
    BRD_RELEVANCE_PROMPT,
    REQUIREMENT_EXTRACTION_PROMPT,
)
from agents.comprehension.brd_builder.skills import SKILLS
from agents.comprehension.brd_builder.tools import (
    BRD_DOCUMENT,
    BRD_SELECTION,
    REQUIREMENTS,
    BrdIndex,
    collect_live_evidence,
    connect_live_agent,
    evidence_from_runtime_profile,
    generate_json,
    normalize_brd_path,
    read_brd,
    read_brd_preview,
    render_evidence,
)
from connectors.connector_registry import ConnectorRegistry
from tools.requirements.normalize import (  # noqa: F401  (moved to the shared core, Phase 1.4; re-exported)
    _KINDS,
    _ORACLES,
    _PRIORITIES,
    _VERIFIABILITY,
    MAX_CRITERIA,
    MAX_REQUIREMENTS,
    SELF_GENERATED_MAX_CONFIDENCE,
    UNGROUNDED_FACTOR,
    _criterion,
    _origin,
    normalize_requirements,
)
from tools.shared import get_logger

MAX_CANDIDATES = 4
MAX_EVIDENCE_CHARS = 90_000
MAX_CODE_DIGEST_CHARS = 120_000


class BrdError(Exception):
    """A user-facing reason the BRD step can't continue."""


class BrdBuilderAgent(BaseAgent):
    MODULE_NAME = "brd_builder"

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self._registry = ConnectorRegistry(self.settings)
        self.logger = get_logger("agent.brd_builder")

    def execute(self, request: dict, state: dict) -> Dict[str, Any]:
        emit = request.get("emit") or (lambda *a, **k: None)
        mode = request.get("mode", "brd_and_live")
        repo_dir = Path(request["repo_dir"]).resolve()
        profile = request.get("agent_profile") or {}
        live_url = (request.get("live_url") or "").strip() or None
        llm = self._registry.get_llm(request.get("connector_mode"))
        limitations: List[str] = []

        def limit(msg: str) -> None:
            emit(msg, "warning")
            limitations.append(msg)

        brd_path: Optional[str] = None
        try:
            user_path = normalize_brd_path(request.get("brd_path"), request.get("repo_full_name"))
            if mode == "live_only":
                brd_text, source = self._generate(llm, profile, request, live_url, emit, limit)
            elif user_path:
                brd_path = user_path
                brd_text = self._read_user_brd(repo_dir, user_path, request.get("brd_candidates") or [], llm, emit,
                                               limitations)
                source = "repository"
            else:
                found = self._auto_detect(repo_dir, request.get("brd_candidates") or [], profile, llm, emit, limit,
                                          limitations)
                if found:
                    (brd_path, brd_text), source = found, "repository"
                else:
                    emit("No BRD for this agent was found in the repository — generating one with Gemini. "
                         "Tip: enter the BRD's path to use your own document.", "warning")
                    brd_text, source = self._generate(llm, profile, request, live_url, emit, limit)
        except (BrdError, ValueError) as exc:
            return {"module": self.MODULE_NAME, "status": "failed", "blocking": True, "error": str(exc),
                    "limitations": limitations}
        except Exception as exc:
            return {"module": self.MODULE_NAME, "status": "failed", "blocking": True,
                    "error": f"BRD step failed: {type(exc).__name__}: {exc}", "limitations": limitations}

        before = len(limitations)
        try:
            requirements, dropped = self._extract_requirements(llm, brd_text, source, brd_path, limitations)
        except Exception as exc:
            return {"module": self.MODULE_NAME, "status": "failed", "blocking": True,
                    "error": f"Could not extract requirements from the BRD: {exc}", "limitations": limitations}
        if dropped:
            emit(f"Discarded {dropped} extracted requirement(s) whose quote could not be found in the BRD.", "warning")
        if not requirements:
            return {"module": self.MODULE_NAME, "status": "failed", "blocking": True,
                    "error": "No requirement could be traced to the BRD text — check that the document is a BRD.",
                    "limitations": limitations}

        for msg in limitations[before:]:  # caps recorded during extraction
            emit(msg, "warning")
        ungrounded = [c["code"] for r in requirements for c in r["criteria"] if not c["grounded"]]
        if ungrounded:
            emit(f"{len(ungrounded)} acceptance criteria could not be traced to the BRD wording "
                 f"({', '.join(ungrounded[:8])}{'…' if len(ungrounded) > 8 else ''}); kept with lower confidence.",
                 "warning")
        if source != "repository":
            limitations.append("The BRD was generated by MTA (no BRD was supplied), so requirement quotes only show that "
                               "MTA's requirements match MTA's own document; results are inferred conformance, "
                               "not BRD compliance.")
        high = sum(1 for r in requirements if r["priority"] == "high")
        emit(f"Extracted {len(requirements)} requirements, each traced to a quote in the BRD ({high} high priority).", "success")
        return {
            "module": self.MODULE_NAME,
            "status": "success",
            "brd_source": source,
            "brd_path": brd_path,
            "brd_markdown": brd_text,
            "requirements": requirements,
            "ungrounded_criteria": ungrounded,
            "limitations": limitations,
        }

    # ── explicit BRD path ────────────────────────────────────────────────────

    def _read_user_brd(self, root: Path, rel: str, candidates: List[str], llm, emit, limitations: List[str]) -> str:
        path = (root / rel).resolve()
        if root not in path.parents or not path.is_file():
            # case-insensitive match helps with paths typed by hand
            match = next((p for p in root.rglob("*") if p.is_file()
                          and p.relative_to(root).as_posix().lower() == rel.lower()), None)
            if match is None:
                hint = f" Documents found in the repo: {', '.join(candidates[:6])}." if candidates else ""
                raise BrdError(f"The BRD '{rel}' does not exist in the repository.{hint}")
            path = match
        emit(f"Reading the BRD you specified: {rel}")
        try:
            text, method = read_brd(path, llm, emit, limitations=limitations)
        except ValueError as exc:
            raise BrdError(f"The BRD '{rel}' could not be read: {exc}") from exc
        emit(f"Using BRD {rel} ({len(text):,} chars{', transcribed by Gemini' if method != 'text' else ''}).", "success")
        return text

    # ── auto-detection ───────────────────────────────────────────────────────

    def _auto_detect(self, root: Path, candidates: List[str], profile: dict, llm, emit, limit,
                     limitations: List[str]) -> Optional[Tuple[str, str]]:
        if not candidates:
            return None
        if len(candidates) > MAX_CANDIDATES:
            limit(f"{len(candidates)} candidate BRD documents were found; only the first {MAX_CANDIDATES} were "
                  f"considered ({', '.join(candidates[MAX_CANDIDATES:MAX_CANDIDATES + 4])}… were not). "
                  "Enter the BRD path to choose one explicitly.")
        previews: Dict[str, str] = {}
        for rel in candidates[:MAX_CANDIDATES]:
            try:
                previews[rel], _ = read_brd_preview(root / rel, llm, emit)
            except ValueError as exc:
                emit(f"Skipping {rel}: {exc}", "warning")
        if not previews:
            return None

        listing = "\n\n".join(f"### {rel}\n{text}" for rel, text in previews.items())
        summary = json.dumps({k: profile.get(k) for k in ("agent_name", "purpose", "capabilities", "domain")},
                             ensure_ascii=False)
        selected: Optional[str] = None
        try:
            choice = generate_json(llm, BRD_RELEVANCE_PROMPT.substitute(
                skill_header=SKILLS["requirement_extraction"].header(), agent_summary=summary, candidates=listing),
                required_keys=["selected_path"], schema=BRD_SELECTION)
        except Exception as exc:
            selected = next(iter(previews))
            limit(f"Could not verify which document is this agent's BRD ({type(exc).__name__}: {str(exc)[:160]}); "
                  f"using the first readable candidate, {selected}, WITHOUT confirming it describes this agent. "
                  "Enter the BRD path to be sure.")
            reason = ""
        else:
            reason = str(choice.get("reason") or "").strip()
            if choice.get("selected_path") in previews:
                selected = choice["selected_path"]
        if selected is None:
            emit(f"None of {', '.join(previews)} describes this agent — {reason}", "warning")
            return None
        try:
            text, method = read_brd(root / selected, llm, emit, limitations=limitations)
        except ValueError as exc:
            emit(f"The selected BRD {selected} could not be read in full: {exc}", "warning")
            return None
        others = [r for r in previews if r != selected]
        if reason:
            emit(f"Using BRD {selected}" + (f" (not {', '.join(others)})" if others else "") + f" — {reason}", "success")
        return selected, text

    # ── generation ───────────────────────────────────────────────────────────

    def _generate(self, llm, profile: dict, request: dict, live_url: Optional[str], emit, limit) -> Tuple[str, str]:
        """Return (brd_markdown, brd_source) — 'generated_live' or 'generated' (from code)."""
        code_digest = request.get("code_digest") or ""
        if live_url:
            evidence = self._live_evidence(live_url, profile, request.get("runtime_profile"), emit)
            if evidence:
                readme = re.search(r"===== FILE: [^\n]*readme[^\n]*=====\n(.*?)(?=\n===== FILE:|\Z)", code_digest, re.I | re.S)
                rendered = render_evidence(evidence)
                if len(rendered) > MAX_EVIDENCE_CHARS:
                    limit(f"Live-app evidence was {len(rendered):,} characters; only the first {MAX_EVIDENCE_CHARS:,} "
                          "were used to write the BRD, so features seen only on later pages may be missing.")
                prompt = BRD_FROM_LIVE_PROMPT.substitute(
                    skill_header=SKILLS["brd_generation"].header(),
                    live_url=live_url,
                    evidence=rendered[:MAX_EVIDENCE_CHARS],
                    code_context=(readme.group(1)[:8000] if readme else "(no README)"),
                )
                emit(f"Writing the BRD from {len(evidence)} piece(s) of live-app evidence.")
                return self._brd_json(llm, prompt), "generated_live"
            emit("Nothing could be observed on the live URL — generating the BRD from the code instead.", "warning")

        if len(code_digest) > MAX_CODE_DIGEST_CHARS:
            limit(f"The code digest was {len(code_digest):,} characters; only the first {MAX_CODE_DIGEST_CHARS:,} "
                  "were used to write the BRD.")
        prompt = BRD_FROM_CODE_PROMPT.substitute(
            skill_header=SKILLS["brd_generation"].header(),
            agent_profile=json.dumps({k: profile.get(k) for k in (
                "agent_name", "purpose", "domain", "target_users", "capabilities", "out_of_scope",
                "tools_and_integrations", "system_prompt_summary", "interface")}, indent=2, ensure_ascii=False),
            code_digest=code_digest[:MAX_CODE_DIGEST_CHARS] or "(no code digest)",
        )
        emit("Writing the BRD from the repository code (each requirement cites its source file).")
        return self._brd_json(llm, prompt), "generated"

    def _live_evidence(self, live_url: str, profile: dict, runtime_profile: Optional[dict], emit) -> List[Dict[str, str]]:
        evidence = evidence_from_runtime_profile(runtime_profile)
        if evidence:
            pages = (runtime_profile or {}).get("pages_inspected") or len((runtime_profile or {}).get("pages") or [])
            emit(f"Documenting the live app from runtime discovery ({pages} page(s) inspected"
                 + (", signed in with the test account" if (runtime_profile or {}).get("authentication") else "")
                 + ") — no second crawl needed.")
            return evidence
        if runtime_profile:
            emit("Runtime discovery saw no usable app pages (login wall or unreachable) — crawling the live URL directly.",
                 "warning")
        emit(f"Exploring the live app at {live_url} to document what it actually does.")
        chat = None
        try:
            chat = connect_live_agent(live_url, profile.get("interface") or {}, log=lambda m: None)
        except Exception:
            emit("The live agent didn't answer chat probes — documenting its pages/API only.")
        try:
            return collect_live_evidence(live_url, emit, chat=chat)
        finally:
            if chat is not None:
                chat.close()

    @staticmethod
    def _brd_json(llm, prompt: str) -> str:
        result = generate_json(llm, prompt, required_keys=["brd_markdown"], schema=BRD_DOCUMENT)
        text = str(result["brd_markdown"]).strip()
        if len(text) < 200:
            raise BrdError("Gemini returned an empty BRD.")
        return text

    # ── requirement extraction ───────────────────────────────────────────────

    def _extract_requirements(self, llm, brd_text: str, source: str, brd_path: Optional[str],
                              limitations: Optional[List[str]] = None) -> Tuple[List[Dict[str, Any]], int]:
        prompt = REQUIREMENT_EXTRACTION_PROMPT.substitute(
            skill_header=SKILLS["requirement_extraction"].header(),
            brd_source="found in repository" if source == "repository" else "generated by MTA",
            brd_path=brd_path or "generated",
            brd_text=brd_text,
            max_requirements=str(MAX_REQUIREMENTS),
        )
        result = generate_json(llm, prompt, required_keys=["requirements"], schema=REQUIREMENTS)
        return normalize_requirements(result.get("requirements") or [], BrdIndex(brd_text), brd_source=source,
                                      limitations=limitations)
