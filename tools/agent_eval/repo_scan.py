"""
repo_scan.py — turn a downloaded repo into something an LLM can read.

  select_files_for_download() → which files of a (possibly huge) repo are worth fetching
  scan_repo()          → RepoScan: file list, rendered tree, detected languages
  build_code_digest()  → one text blob of the most informative files, under a char budget
  find_brd_candidates()→ ranked files that look like a BRD / PRD / requirements spec
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from engines.repo_intel.files import (
    KEY_FILE_NAMES,
    LANG_BY_EXT,
    MAX_FETCH_BYTES,
    MAX_FILE_BYTES,
    MAX_FILES,
    SKIP_DIRS,
    TEXT_EXT,
    is_skipped,
    is_text_candidate,
    is_lock_or_minified,
    language_of,
    skip_reason,
)

# Which files exist for the evaluation (skip-dirs, size limit, extensions, file cap) is defined once in
# engines/repo_intel/files.py and shared with the indexer, so what is fetched is exactly what can be indexed.
_SKIP_DIRS = SKIP_DIRS
_TEXT_EXT = TEXT_EXT
_LANG_BY_EXT = LANG_BY_EXT

# Files that tell us what the agent is and how it's run — always read first.
_KEY_FILE_NAMES = KEY_FILE_NAMES
_ENTRYPOINT_HINT = re.compile(
    r"(^|/)(main|app|server|api|agent|agents|graph|chain|bot|chat|crew|workflow|tools?|prompts?|router|routes|index|streamlit_app)"
    r"[^/]*\.(py|ts|js|tsx|jsx|go|java|kt|rb|php|cs|rs|swift|dart|vue|svelte)$",
    re.I,
)
_TEST_HINT = re.compile(r"(^|/)(tests?|__tests__|spec)(/|$)|(_test|\.test|\.spec|test_)[^/]*$", re.I)

_BRD_EXT = {".md", ".txt", ".pdf", ".docx"}
_BRD_NAME = re.compile(
    r"(brd|business[\s_-]*requirement|requirement[s]?[\s_-]*(doc|spec)|prd|product[\s_-]*requirement|"
    r"\bsrs\b|functional[\s_-]*spec|specification|user[\s_-]*stor(y|ies)|acceptance[\s_-]*criteria|"
    r"requirements)",
    re.I,
)
_BRD_DIR = re.compile(r"(^|/)(docs?|requirements|specs?|brd|documentation)(/|$)", re.I)
_LOW_VALUE_EXT = (".css", ".scss", ".sass", ".less", ".svg", ".xml", ".csproj", ".sln", ".ipynb")


@dataclass
class RepoScan:
    root: Path
    files: List[str] = field(default_factory=list)  # repo-relative POSIX paths
    languages: Dict[str, int] = field(default_factory=dict)
    total_files: int = 0

    def tree(self, limit: int = 400) -> str:
        shown = self.files[:limit]
        more = f"\n… and {len(self.files) - limit} more files" if len(self.files) > limit else ""
        return "\n".join(shown) + more


def _skipped(rel: str) -> bool:
    """True if any directory in the path is vendored/build/hidden."""
    return is_skipped(rel)


def scan_repo(root: Path, all_paths: Optional[List[str]] = None) -> RepoScan:
    """Scan a checkout. all_paths = the repo's full file list when only a subset was downloaded,
    so the tree, language stats and BRD detection still reflect the whole repository."""
    scan = RepoScan(root=root)
    if all_paths is not None:
        for rel in sorted(p for p in all_paths if not _skipped(p)):
            scan.files.append(rel)
            lang = language_of(rel)
            if lang:
                scan.languages[lang] = scan.languages.get(lang, 0) + 1
        scan.total_files = len(scan.files)
        return scan
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not is_skipped(f"{d}/x"))
        for name in sorted(filenames):
            full = Path(dirpath) / name
            rel = full.relative_to(root).as_posix()
            scan.files.append(rel)
            lang = language_of(rel)
            if lang:
                scan.languages[lang] = scan.languages.get(lang, 0) + 1
    scan.total_files = len(scan.files)
    return scan


def _read_text(path: Path, limit: int) -> Optional[str]:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if "\x00" in text[:2000]:
        return None  # binary
    return text if len(text) <= limit else text[:limit] + "\n… [truncated]"


def _priority(rel: str) -> int:
    lower = rel.lower()
    name = lower.rsplit("/", 1)[-1]
    depth = lower.count("/")
    if name in _KEY_FILE_NAMES:
        return 0 + depth
    if _ENTRYPOINT_HINT.search(lower) and not _TEST_HINT.search(lower):
        return 10 + depth
    if "prompt" in lower:
        return 15 + depth
    if _TEST_HINT.search(lower):
        return 40 + depth
    if name.endswith((".md", ".rst")):
        return 30 + depth
    if name.endswith(_LOW_VALUE_EXT):  # stylesheets / project files: fetched last, after all code
        return 35 + depth
    return 20 + depth


def build_code_digest(
    scan: RepoScan,
    char_budget: int = 180_000,
    per_file_limit: int = 20_000,
    exclude: Optional[List[str]] = None,
) -> str:
    """Concatenate the most informative text files, highest priority first."""
    excluded = set(exclude or [])
    candidates = [
        rel for rel in scan.files
        if rel not in excluded
        and is_text_candidate(rel) and not is_lock_or_minified(rel)
    ]
    candidates.sort(key=lambda r: (_priority(r), r))

    parts: List[str] = []
    used = 0
    for rel in candidates:
        text = _read_text(scan.root / rel, per_file_limit)
        if not text or not text.strip():
            continue
        block = f"\n===== FILE: {rel} =====\n{text}\n"
        if used + len(block) > char_budget:
            if used > char_budget * 0.9:
                break
            continue  # a smaller file further down may still fit
        parts.append(block)
        used += len(block)
    return "".join(parts)


def select_files_for_download(
    entries: List[Tuple[str, int]],
    must_include: Optional[List[str]] = None,
    # Repository Intelligence indexes everything fetched and traceability searches it, so the
    # budget is sized for code coverage (1,200 files / 10 MB), not just the ~180k-char digest.
    byte_budget: int = MAX_FETCH_BYTES,
    max_files: int = MAX_FILES,
    max_doc_bytes: int = 30 * 1024 * 1024,
) -> List[str]:
    """Pick the files worth fetching from a repo's (path, size) listing.

    Always: every BRD-like document (and must_include, e.g. the user's BRD path).
    Then: readable text/code files in digest-priority order, until the budget is used.
    """
    by_path = dict(entries)
    wanted: List[str] = []
    lowered = {p.lower(): p for p in by_path}
    for rel in must_include or []:
        real = lowered.get(rel.lower())
        if real and by_path[real] <= max_doc_bytes:
            wanted.append(real)
    docs = find_brd_candidates(RepoScan(root=Path("."), files=[p for p in by_path if not _skipped(p)]))
    wanted += [d for d in docs[:8] if by_path.get(d, 0) <= max_doc_bytes and d not in wanted]

    code = [p for p, size in by_path.items() if p not in wanted and skip_reason(p, size) is None]
    code.sort(key=lambda r: (_priority(r), r))
    used = 0
    for rel in code:
        if len(wanted) >= max_files or used >= byte_budget:
            break
        if used + by_path[rel] > byte_budget:
            continue
        wanted.append(rel)
        used += by_path[rel]
    return wanted


def selection_report(entries: List[Tuple[str, int]], selected: List[str]) -> Dict[str, int]:
    """Why each file of the listing was not selected: {reason: count}. Reasons match the indexer's coverage keys
    (vendored_or_hidden, lockfile_or_minified, unsupported_type, too_large, empty) plus `budget` (eligible, but the
    file/byte budget was used up)."""
    chosen = set(selected)
    out: Dict[str, int] = {}
    for path, size in entries:
        if path in chosen:
            continue
        reason = skip_reason(path, size) or "budget"
        out[reason] = out.get(reason, 0) + 1
    return dict(sorted(out.items()))


def find_brd_candidates(scan: RepoScan) -> List[str]:
    """Repo-relative paths that look like a requirements document, best match first."""
    scored = []
    for rel in scan.files:
        path = Path(rel)
        name = path.name.lower()
        if path.suffix.lower() not in _BRD_EXT:
            continue
        if name in ("requirements.txt", "requirements-dev.txt", "dev-requirements.txt") or name.startswith("requirements-"):
            continue  # Python dependency lists, not a BRD
        score = 0
        if _BRD_NAME.search(path.stem):
            score += 10
        if re.search(r"\bbrd\b|business", path.stem, re.I):
            score += 5
        if _BRD_DIR.search(rel):
            score += 3
        if path.suffix.lower() in (".pdf", ".docx"):
            score += 1
        if score >= 10:
            scored.append((score, -rel.count("/"), rel))
    scored.sort(reverse=True)
    return [rel for _, _, rel in scored]
