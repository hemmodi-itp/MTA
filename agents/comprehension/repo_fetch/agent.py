"""
RepoFetchAgent — checks that a GitHub repository is readable, pins it to one commit and fetches what the
evaluation needs from it.

First step of the agent-evaluation pipeline (workflows/agent_evaluation.yaml). No LLM calls.

1. Resolve the default branch and the commit SHA of the requested branch *first* (REST API; when that stays
   rate-limited, git's ref advertisement — the branch is never guessed).
2. List the commit's tree and fetch only the selected files, by SHA, in parallel — so the content evaluated is
   exactly what the Repository Intelligence cache key (repo, SHA, indexer version) names.
3. Fall back to the commit's zip when the tree API is unavailable or the listing is truncated (same file
   selection, decompressed-size and member caps), unless the repo is too large to download.
4. Report `repo_coverage`: files in the tree, selected, fetched, skipped by reason, truncation — the absence
   protocol in requirement traceability and the report's limitations read it.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agents.base_agent import BaseAgent
from agents.comprehension.repo_fetch.tools import (
    BranchNotFound,
    GitHubRateLimited,
    RepoAccessError,
    download_files,
    download_repo,
    fetch_repo_metadata,
    fetch_tree,
    has_token,
    ls_remote,
    normalize_brd_path,
    parse_github_url,
    resolve_commit_sha,
    select_files_for_download,
    selection_report,
)
from tools.shared import get_logger

# Above this GitHub-reported size, the zip fallback is refused (it would take many minutes).
MAX_ZIP_FALLBACK_KB = 150 * 1024


class RepoFetchAgent(BaseAgent):
    MODULE_NAME = "repo_fetch"

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self.logger = get_logger("agent.repo_fetch")

    def execute(self, request: dict, state: dict) -> Dict[str, Any]:
        emit = request.get("emit") or (lambda *a, **k: None)
        dest = Path(request["workspace_dir"]) / "repo"

        try:
            ref = parse_github_url(request.get("github_url", ""))
            meta, refs = None, None
            try:
                meta = fetch_repo_metadata(ref)
                default_branch = meta.default_branch
                size = f"{meta.size_kb / 1024:.0f} MB" if meta.size_kb >= 1024 else f"{meta.size_kb} KB"
                access = "private, read with GITHUB_TOKEN" if meta.private else "public"
                emit(f"{meta.full_name} is {access} ({meta.language or 'unknown language'}, {size}).")
            except GitHubRateLimited as exc:
                emit(f"{exc} Resolving the branch through git instead.", "warning")
                default_branch, refs = ls_remote(ref)
                if not default_branch:
                    raise GitHubRateLimited(f"{exc} The default branch could not be determined either.") from exc
            if not default_branch:  # empty repository
                raise RepoAccessError(f"Repository {ref.full_name} has no commits to evaluate.")

            requested = (request.get("branch") or ref.ref or "").strip()
            branch = requested or default_branch
            try:
                sha, refs = self._sha(ref, branch, refs)
            except BranchNotFound:
                if branch == default_branch:
                    raise
                emit(f"Branch '{branch}' not found — using the default branch '{default_branch}'.", "warning")
                branch = default_branch
                sha, refs = self._sha(ref, branch, refs)
            emit(f"Evaluating {ref.full_name}@{branch}, pinned to commit {sha[:7]}.")

            user_brd = normalize_brd_path(request.get("brd_path"), ref.full_name)
            must = [user_brd] if user_brd else None
            listing, why_zip = None, None
            if refs is None:  # REST API usable
                try:
                    listing = fetch_tree(ref, sha)
                    if listing.truncated:
                        why_zip = (f"GitHub truncated the file listing ({len(listing.entries):,} files shown), "
                                   "so the commit archive is used to see every file")
                except GitHubRateLimited as exc:
                    why_zip = str(exc)
            else:
                why_zip = "GitHub API rate limit"

            if listing is not None and not why_zip:
                repo_dir, coverage = self._fetch_selected(ref, sha, listing.entries, dest, must, emit, "tree")
            elif meta and meta.size_kb > MAX_ZIP_FALLBACK_KB:
                if listing is not None and listing.entries:  # truncated listing: use what it shows, say so
                    emit(f"{why_zip}, but the repository is {meta.size_kb // 1024} MB — too large to download in full; "
                         "evaluating the files the truncated listing shows.", "warning")
                    repo_dir, coverage = self._fetch_selected(ref, sha, listing.entries, dest, must, emit, "tree")
                    coverage.update(truncated=True, truncation_reason="GitHub truncated the recursive tree listing; "
                                                                      "files beyond it were not seen")
                else:
                    raise RepoAccessError(
                        f"GitHub's file-listing API is unavailable ({why_zip}) and the repository is "
                        f"{meta.size_kb // 1024} MB — too large to download in full. "
                        + ("Try again after the rate limit resets." if has_token()
                           else "Set GITHUB_TOKEN for the evaluation service, or try again in an hour."))
            else:
                emit(f"{why_zip} — downloading the commit archive instead.", "warning")
                repo_dir, coverage = self._fetch_zip(ref, sha, dest, must, emit)
        except RepoAccessError as exc:
            return {"module": self.MODULE_NAME, "status": "failed", "error": str(exc), "blocking": True}
        except ValueError as exc:  # bad BRD link (points at another repo, escapes the repo)
            return {"module": self.MODULE_NAME, "status": "failed", "error": str(exc), "blocking": True}

        coverage.update(commit_sha=sha, authenticated=has_token(), private=bool(meta and meta.private))
        if coverage.get("truncated"):
            emit(f"Coverage limitation: {coverage['truncation_reason']}.", "warning")
        repo_tree = coverage.pop("_all_paths")
        return {
            "module": self.MODULE_NAME,
            "status": "success",
            "repo_dir": str(repo_dir),
            "repo_tree": repo_tree,
            "repo_full_name": meta.full_name if meta else ref.full_name,
            "branch": branch,
            "commit_sha": sha,
            "repo_coverage": coverage,
            "repo_metadata": {
                "description": meta.description if meta else "",
                "language": meta.language if meta else "",
                "size_kb": meta.size_kb if meta else None,
                "html_url": meta.html_url if meta else f"https://github.com/{ref.full_name}",
                "private": bool(meta and meta.private),
            },
        }

    @staticmethod
    def _sha(ref, branch: str, refs: Optional[Dict[str, str]]) -> Tuple[str, Optional[Dict[str, str]]]:
        """Commit SHA of `branch`; switches to git ref discovery when the REST API is rate-limited."""
        if refs is None:
            try:
                return resolve_commit_sha(ref, branch), None
            except GitHubRateLimited:
                _, refs = ls_remote(ref)
        if len(branch) == 40 and all(c in "0123456789abcdef" for c in branch.lower()):
            return branch.lower(), refs
        sha = refs.get(branch)
        if not sha:
            raise BranchNotFound(f"Branch '{branch}' of {ref.full_name} was not found.")
        return sha, refs

    def _fetch_selected(self, ref, sha: str, entries: List[Tuple[str, int]], dest: Path, must, emit, source: str):
        selected = select_files_for_download(entries, must_include=must)
        total_mb = sum(size for _, size in entries) / 2 ** 20
        emit(f"Repository has {len(entries):,} files ({total_mb:.0f} MB); fetching the {len(selected)} "
             "that matter for the evaluation (docs, manifests, entry points, source).")
        got, failed = download_files(
            ref, sha, selected, dest,
            progress=lambda done, n: emit(f"Fetched {done}/{n} files…") if n >= 200 else None,
        )
        if got == 0:
            raise RepoAccessError("None of the repository's files could be downloaded from GitHub.")
        if failed:
            emit(f"{len(failed)} file(s) could not be fetched and were skipped.", "warning")
        emit(f"Fetched {got} files from {ref.full_name}@{sha[:7]}.", "success")
        return dest.resolve(), self._coverage(source, entries, selected, got, failed, truncated=False)

    def _fetch_zip(self, ref, sha: str, dest: Path, must, emit):
        chosen: List[str] = []

        def select(entries):
            chosen[:] = select_files_for_download(entries, must_include=must)
            return chosen

        root, entries = download_repo(ref, sha, dest, select=select)
        emit(f"Extracted {len(chosen)} of {len(entries):,} files from the commit archive.", "success")
        return root, self._coverage("zip", entries, chosen, len(chosen), [], truncated=False)

    @staticmethod
    def _coverage(source: str, entries, selected: List[str], got: int, failed: List[str], truncated: bool) -> Dict:
        skipped = selection_report(entries, selected)
        if failed:
            skipped["fetch_failed"] = len(failed)
        return {
            "source": source,                     # tree | zip
            "files_in_tree": len(entries),
            "selected": len(selected),
            "fetched": got,
            "in_tree": len(entries),              # alias read by engines/report/final.py
            "skipped": skipped,                   # {reason: count}; see repo_scan.selection_report
            # readable files left out (budget, size, fetch errors) — not images/vendored/lockfiles, which never matter
            "skipped_total": sum(skipped.get(k, 0) for k in ("budget", "too_large", "fetch_failed")),
            "failed_paths": failed[:50],
            "truncated": truncated,
            "truncation_reason": None,
            "_all_paths": [p for p, _ in entries],  # becomes repo_tree, not part of the coverage record
        }
