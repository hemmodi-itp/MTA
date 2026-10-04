"""
github.py — repository access, commit pinning and source download, no git binary needed.

Everything is pinned to one commit: the branch (requested, or the repository's default branch) is resolved to
a commit SHA *first*, and the tree, every raw file and the zip fallback are then fetched by that SHA, so the
content that is evaluated is exactly the content the Repository Intelligence cache key names.

Access
  * Public repositories work without credentials. With GITHUB_TOKEN set, every GitHub request (REST API, raw
    files, zip, git ref discovery) is authenticated — raising the API limit from 60 to 5000 requests/hour and
    allowing **private** repositories the token can read. Without a token a private repo is reported as
    "not found or private" with how to fix it. The Authorization header is never forwarded across redirects.
  * Rate limits (403/429 with x-ratelimit-remaining 0, or Retry-After) are retried, waiting for the reset /
    Retry-After when that is within a bound (MAX_RATE_LIMIT_WAIT_S per wait, MAX_TOTAL_WAIT_S overall), then fail
    with a clear "GitHub API rate limit" error (GitHubRateLimited). The default branch is never guessed: when the
    REST API stays rate-limited, it and the commit SHA come from git's smart-HTTP ref advertisement (ls_remote),
    which is not subject to the REST limit.
  * Transient failures (5xx, timeouts, connection resets) are retried with exponential backoff and jitter.

Source
  * fetch_tree(): the commit's full tree (GET /git/trees/<sha>?recursive=1), with `truncated` reported.
  * download_files(): the selected files from raw.githubusercontent.com/<repo>/<sha>/…, in parallel.
  * download_repo(): the zip fallback (tree unavailable or truncated). Only the selected members are extracted,
    under a decompressed-size cap (MAX_ZIP_BYTES) and a member-count cap (MAX_ZIP_MEMBERS), zip-slip guarded.
"""

import base64
import io
import json
import os
import random
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from engines.repo_intel.files import MAX_ZIP_BYTES, MAX_ZIP_MEMBERS
from tools.agent_eval.http_ssl import urlopen as _urlopen

_URL_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/"
    r"(?P<repo>[A-Za-z0-9._-]+?)(?:\.git)?(?:/tree/(?P<ref>[^?#]+))?/?(?:[?#].*)?$"
)
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

MAX_ARCHIVE_BYTES = 150 * 1024 * 1024  # compressed zip we are willing to download
RETRY_ATTEMPTS = 4
MAX_RATE_LIMIT_WAIT_S = 60.0   # longest single wait for a rate-limit reset / Retry-After
MAX_TOTAL_WAIT_S = 150.0       # total waiting per request before giving up
_USER_AGENT = "agentic-qa-platform"
_GITHUB_HOSTS = ("api.github.com", "raw.githubusercontent.com", "codeload.github.com", "github.com")
_sleep = time.sleep  # tests replace it


class RepoAccessError(Exception):
    """Repo is private, missing, too large, or GitHub refused the request."""


class GitHubRateLimited(RepoAccessError):
    """GitHub kept rate-limiting the request beyond the retry bound."""


class BranchNotFound(RepoAccessError):
    """The requested branch / ref does not exist."""


@dataclass
class RepoRef:
    owner: str
    repo: str
    ref: Optional[str] = None

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


@dataclass
class RepoMetadata:
    full_name: str
    default_branch: str
    description: str
    language: str
    size_kb: int
    html_url: str
    private: bool = False


@dataclass
class TreeListing:
    entries: List[Tuple[str, int]] = field(default_factory=list)  # (path, size) of every blob
    truncated: bool = False


def parse_github_url(url: str) -> RepoRef:
    match = _URL_RE.match((url or "").strip())
    if not match:
        raise RepoAccessError(
            f"'{url}' is not a GitHub repository URL (expected https://github.com/<owner>/<repo>)."
        )
    return RepoRef(match["owner"], match["repo"], match["ref"])


def has_token() -> bool:
    return bool(os.environ.get("GITHUB_TOKEN", "").strip())


def _request(url: str, accept: str = "application/vnd.github+json") -> urllib.request.Request:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, "Accept": accept})
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    host = urllib.parse.urlsplit(url).hostname or ""
    if token and host in _GITHUB_HOSTS:
        if host == "github.com":  # git smart-HTTP wants Basic auth
            cred = base64.b64encode(f"x-access-token:{token}".encode()).decode()
            req.add_unredirected_header("Authorization", f"Basic {cred}")
        else:
            req.add_unredirected_header("Authorization", f"Bearer {token}")
    return req


# ── retries ──────────────────────────────────────────────────────────────────

def _backoff(attempt: int, base: float = 1.0, cap: float = 20.0) -> float:
    """Exponential backoff with full jitter."""
    return random.uniform(0.5, 1.0) * min(cap, base * (2 ** attempt))


def _rate_limit_wait(exc: urllib.error.HTTPError) -> Optional[float]:
    """Seconds GitHub asks us to wait, if this response is a rate limit; None otherwise."""
    if exc.code not in (403, 429):
        return None
    headers = exc.headers or {}
    retry_after = headers.get("Retry-After")
    if retry_after:
        try:
            return max(1.0, float(retry_after))
        except ValueError:
            return 60.0
    if headers.get("x-ratelimit-remaining") == "0":
        try:
            return max(1.0, float(headers.get("x-ratelimit-reset")) - time.time() + 1)
        except (TypeError, ValueError):
            return 60.0
    if exc.code == 429:
        return 0.0  # rate limited without a hint: plain backoff
    return None  # an ordinary 403 (forbidden)


def _reset_hint(exc: urllib.error.HTTPError) -> str:
    try:
        reset = float((exc.headers or {}).get("x-ratelimit-reset"))
        return f" It resets at {time.strftime('%H:%M UTC', time.gmtime(reset))}."
    except (TypeError, ValueError):
        return ""


def _rate_limited_error(url: str, exc: urllib.error.HTTPError) -> GitHubRateLimited:
    what = "API" if "api.github.com" in url else "download"
    fix = "" if has_token() else " Set GITHUB_TOKEN for the evaluation service to raise the limit (60 → 5000 requests/hour)."
    return GitHubRateLimited(f"GitHub {what} rate limit reached and not lifted within "
                             f"{int(MAX_TOTAL_WAIT_S)}s.{_reset_hint(exc)}{fix}")


def _get(url: str, accept: str = "application/vnd.github+json", timeout: float = 30,
         attempts: int = RETRY_ATTEMPTS, max_bytes: Optional[int] = None) -> Tuple[bytes, Dict[str, str]]:
    """GET with rate-limit and transient-error retries. Raises urllib HTTPError for real errors (404, 401 …),
    GitHubRateLimited when the rate limit outlasts the bound, URLError / TimeoutError after the last retry."""
    waited = 0.0
    for attempt in range(attempts):
        try:
            with _urlopen(_request(url, accept), timeout=timeout) as resp:
                if max_bytes is not None:
                    declared = int(resp.headers.get("Content-Length") or 0)
                    if declared > max_bytes:
                        raise RepoAccessError(f"Download is {declared // 2**20} MB — the limit is {max_bytes // 2**20} MB.")
                    data = resp.read(max_bytes + 1)
                    if len(data) > max_bytes:
                        raise RepoAccessError(f"Download exceeds {max_bytes // 2**20} MB.")
                else:
                    data = resp.read()
                return data, dict(resp.headers.items())
        except urllib.error.HTTPError as exc:
            wait = _rate_limit_wait(exc)
            if wait is not None:
                wait = wait or _backoff(attempt)
                if attempt == attempts - 1 or wait > MAX_RATE_LIMIT_WAIT_S or waited + wait > MAX_TOTAL_WAIT_S:
                    raise _rate_limited_error(url, exc) from exc
                _sleep(wait + random.uniform(0, 1))
                waited += wait
                continue
            if exc.code >= 500 and attempt < attempts - 1:
                _sleep(_backoff(attempt))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            if attempt < attempts - 1:
                _sleep(_backoff(attempt))
                continue
            raise
    raise RepoAccessError(f"GitHub request failed after {attempts} attempts: {url}")  # pragma: no cover


def _not_found_message(ref: RepoRef) -> str:
    if has_token():
        return (f"Repository {ref.full_name} was not found, or the configured GITHUB_TOKEN has no access to it. "
                "Check the URL, or grant the token read access to this repository.")
    return (f"Repository {ref.full_name} was not found or is private. To evaluate a private repository, set "
            "GITHUB_TOKEN for the evaluation service to a token with read access to it.")


def _http_error(ref: RepoRef, exc: urllib.error.HTTPError, what: str) -> RepoAccessError:
    if exc.code == 404:
        return RepoAccessError(_not_found_message(ref))
    if exc.code == 401:
        return RepoAccessError("GitHub rejected the configured GITHUB_TOKEN (bad or expired credentials). "
                               "Fix or remove it and try again.")
    if exc.code == 403:
        return RepoAccessError(f"GitHub refused access to {ref.full_name} ({what}: HTTP 403). "
                               + ("The GITHUB_TOKEN may lack the required scope." if has_token() else ""))
    return RepoAccessError(f"GitHub returned HTTP {exc.code} for {ref.full_name} ({what}).")


# ── metadata, refs, commit ───────────────────────────────────────────────────

def fetch_repo_metadata(ref: RepoRef, timeout: int = 20) -> RepoMetadata:
    """Repository metadata. Raises RepoAccessError when the repo is missing / not readable with the configured
    credentials, GitHubRateLimited when the API stays rate-limited beyond the retry bound."""
    try:
        raw, _ = _get(f"https://api.github.com/repos/{ref.full_name}", timeout=timeout)
        data = json.loads(raw.decode("utf-8"))
    except GitHubRateLimited:
        raise
    except urllib.error.HTTPError as exc:
        raise _http_error(ref, exc, "repository lookup") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise RepoAccessError(f"Could not reach GitHub: {getattr(exc, 'reason', exc)}") from exc
    except ValueError as exc:
        raise RepoAccessError(f"GitHub returned an unreadable response for {ref.full_name}.") from exc

    private = bool(data.get("private"))
    if private and not has_token():  # cannot happen through the API, kept as a guard
        raise RepoAccessError(_not_found_message(ref))
    return RepoMetadata(
        full_name=data.get("full_name", ref.full_name),
        default_branch=data.get("default_branch") or "",
        description=data.get("description") or "",
        language=data.get("language") or "",
        size_kb=int(data.get("size") or 0),
        html_url=data.get("html_url") or f"https://github.com/{ref.full_name}",
        private=private,
    )


def ls_remote(ref: RepoRef, timeout: int = 30) -> Tuple[Optional[str], Dict[str, str]]:
    """(default branch, {branch: sha, "HEAD": sha}) from git's smart-HTTP ref advertisement (no REST rate limit)."""
    url = f"https://github.com/{ref.full_name}.git/info/refs?service=git-upload-pack"
    try:
        raw, _ = _get(url, accept="application/x-git-upload-pack-advertisement", timeout=timeout)
    except urllib.error.HTTPError as exc:
        raise _http_error(ref, exc, "git ref discovery") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise RepoAccessError(f"Could not reach GitHub: {getattr(exc, 'reason', exc)}") from exc
    return parse_ref_advertisement(raw)


def parse_ref_advertisement(raw: bytes) -> Tuple[Optional[str], Dict[str, str]]:
    refs: Dict[str, str] = {}
    default: Optional[str] = None
    pos = 0
    while pos + 4 <= len(raw):
        try:
            n = int(raw[pos:pos + 4], 16)
        except ValueError:
            break
        if n == 0:  # flush packet
            pos += 4
            continue
        line = raw[pos + 4:pos + n].decode("utf-8", "replace").rstrip("\n")
        pos += n
        if line.startswith("#"):
            continue
        head, _, caps = line.partition("\0")
        sha, _, name = head.partition(" ")
        m = re.search(r"symref=HEAD:refs/heads/(\S+)", caps)
        if m:
            default = m.group(1)
        if name == "HEAD":
            refs["HEAD"] = sha
        elif name.startswith("refs/heads/"):
            refs[name[len("refs/heads/"):]] = sha
    return default, refs


def resolve_commit_sha(ref: RepoRef, branch: str, timeout: int = 20) -> str:
    """The commit SHA `branch` (or a tag / SHA) points at. Raises BranchNotFound, GitHubRateLimited, RepoAccessError."""
    if _SHA_RE.match(branch or ""):
        return branch
    url = f"https://api.github.com/repos/{ref.full_name}/commits/{urllib.parse.quote(branch, safe='')}"
    try:
        raw, _ = _get(url, accept="application/vnd.github.sha", timeout=timeout)
    except GitHubRateLimited:
        raise
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 422):
            raise BranchNotFound(f"Branch '{branch}' of {ref.full_name} was not found.") from exc
        raise _http_error(ref, exc, "commit lookup") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise RepoAccessError(f"Could not reach GitHub: {getattr(exc, 'reason', exc)}") from exc
    sha = raw.decode("utf-8", "replace").strip()[:40]
    if not _SHA_RE.match(sha):
        raise RepoAccessError(f"GitHub returned no commit for '{branch}' of {ref.full_name}.")
    return sha


# ── tree / files / zip ───────────────────────────────────────────────────────

def fetch_tree(ref: RepoRef, sha: str, timeout: int = 60) -> TreeListing:
    """Every blob in the commit as (path, size), and whether GitHub truncated the listing.
    Raises GitHubRateLimited / RepoAccessError; the caller falls back to the zip."""
    url = f"https://api.github.com/repos/{ref.full_name}/git/trees/{urllib.parse.quote(sha, safe='')}?recursive=1"
    try:
        raw, _ = _get(url, timeout=timeout)
        data = json.loads(raw.decode("utf-8"))
    except GitHubRateLimited:
        raise
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 422):
            raise BranchNotFound(f"Commit {sha[:7]} of {ref.full_name} was not found.") from exc
        raise _http_error(ref, exc, "tree listing") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as exc:
        raise RepoAccessError(f"GitHub tree listing failed: {getattr(exc, 'reason', exc)}") from exc
    entries = [(e["path"], int(e.get("size") or 0)) for e in data.get("tree", []) if e.get("type") == "blob"]
    return TreeListing(entries, bool(data.get("truncated")))


def download_files(
    ref: RepoRef,
    sha: str,
    paths: List[str],
    dest: Path,
    progress: Callable[[int, int], None] = lambda done, total: None,
    workers: int = 8,
    timeout: int = 60,
) -> Tuple[int, List[str]]:
    """Fetch the given files of commit `sha` into dest/, preserving paths. Returns (downloaded, failed_paths).
    A rate limit that outlasts the retry bound fails the remaining files instead of hanging."""
    root = dest.resolve()
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    limited: List[GitHubRateLimited] = []

    def one(rel: str) -> bool:
        target = (root / rel).resolve()
        if root not in target.parents:
            return False  # never write outside dest/
        if limited:
            return False
        url = (f"https://raw.githubusercontent.com/{ref.full_name}/"
               f"{urllib.parse.quote(sha, safe='')}/{urllib.parse.quote(rel, safe='/')}")
        try:
            data, _ = _get(url, accept="*/*", timeout=timeout)
        except GitHubRateLimited as exc:
            limited.append(exc)
            return False
        except Exception:
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return True

    failed: List[str] = []
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for rel, ok in zip(paths, pool.map(one, paths)):
            done += 1
            if not ok:
                failed.append(rel)
            if done % 100 == 0 or done == len(paths):
                progress(done, len(paths))
    if limited and len(failed) == len(paths):
        raise limited[0]
    return len(paths) - len(failed), failed


def download_repo(
    ref: RepoRef,
    sha: str,
    dest: Path,
    select: Optional[Callable[[List[Tuple[str, int]]], List[str]]] = None,
    timeout: int = 180,
    max_bytes: int = MAX_ZIP_BYTES,
    max_members: int = MAX_ZIP_MEMBERS,
) -> Tuple[Path, List[Tuple[str, int]]]:
    """Download commit `sha` as a zip and extract it into dest/. Returns (root, entries) where entries lists every
    file in the archive as (path, size). With `select`, only the paths it returns are extracted (the same selection
    as the tree path, so coverage and the indexer's file cap match). Refuses archives over MAX_ARCHIVE_BYTES
    compressed, more than `max_members` entries, or more than `max_bytes` decompressed (what is actually written
    is counted, not what the archive claims)."""
    url = (f"https://api.github.com/repos/{ref.full_name}/zipball/{urllib.parse.quote(sha, safe='')}" if has_token()
           else f"https://codeload.github.com/{ref.full_name}/zip/{urllib.parse.quote(sha, safe='')}")
    try:
        payload, _ = _get(url, accept="application/zip", timeout=timeout, attempts=3, max_bytes=MAX_ARCHIVE_BYTES)
    except GitHubRateLimited:
        raise
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise RepoAccessError(_not_found_message(ref)) from exc
        raise RepoAccessError(f"Download failed: HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise RepoAccessError(f"Could not reach GitHub: {getattr(exc, 'reason', exc)}") from exc

    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    root = dest.resolve()
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise RepoAccessError("GitHub returned a corrupt repository archive.") from exc
    with archive:
        members = [m for m in archive.infolist() if not m.is_dir()]
        if len(members) > max_members:
            raise RepoAccessError(f"Repository archive lists {len(members):,} files — the limit is {max_members:,}.")
        names = [m.filename for m in members]
        tops = {n.split("/", 1)[0] for n in names}  # codeload wraps everything in one "<repo>-<sha>/" folder
        prefix = f"{tops.pop()}/" if len(tops) == 1 and all("/" in n for n in names) else ""
        by_rel = {m.filename[len(prefix):]: m for m in members if m.filename.startswith(prefix)}
        entries = sorted((rel, m.file_size) for rel, m in by_rel.items() if rel)
        wanted = select(entries) if select else [rel for rel, _ in entries]
        written = 0
        for rel in wanted:
            m = by_rel.get(rel)
            if m is None:
                continue
            target = (root / rel).resolve()
            if root != target and root not in target.parents:  # zip-slip guard
                raise RepoAccessError(f"Archive contains an unsafe path: {m.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(m) as src, open(target, "wb") as out:
                while True:
                    block = src.read(1 << 16)
                    if not block:
                        break
                    written += len(block)
                    if written > max_bytes:
                        raise RepoAccessError(f"Repository archive decompresses to more than {max_bytes // 2**20} MB.")
                    out.write(block)
    return root, entries
