"""Repo fetch: commit pinning, authenticated/private access, rate-limit backoff, truncated trees, zip caps, coverage."""

import io
import json
import time
import urllib.error
import zipfile

import pytest

import tools.agent_eval.github as gh
from agents.comprehension.repo_fetch.agent import RepoFetchAgent
from tools.agent_eval.repo_scan import select_files_for_download, selection_report

SHA = "1234567890abcdef1234567890abcdef12345678"


class _Resp:
    def __init__(self, body: bytes, headers=None):
        self.body, self.headers = body, {"Content-Length": str(len(body)), **(headers or {})}

    def read(self, n=-1):
        return self.body if n is None or n < 0 else self.body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http_error(url, code, headers=None):
    return urllib.error.HTTPError(url, code, "err", headers or {}, io.BytesIO(b""))


class FakeGitHub:
    """Routes urlopen calls by URL; records requests."""

    def __init__(self, routes):
        self.routes, self.requests = routes, []

    def __call__(self, req, timeout=30):
        self.requests.append(req)
        for key, handler in self.routes.items():
            if key in req.full_url:
                out = handler(req) if callable(handler) else handler
                if isinstance(out, Exception):
                    raise out
                return out if isinstance(out, _Resp) else _Resp(out if isinstance(out, bytes) else json.dumps(out).encode())
        raise _http_error(req.full_url, 404)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(gh, "_sleep", lambda s: slept.append(s))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    return slept


def _zip(files: dict, top="r-" + SHA) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for rel, text in files.items():
            z.writestr(f"{top}/{rel}", text)
    return buf.getvalue()


def test_rate_limit_waits_for_reset_then_succeeds(monkeypatch, no_sleep):
    calls = {"n": 0}

    def meta(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return _http_error(req.full_url, 403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(int(time.time()) + 5)})
        return {"full_name": "o/r", "default_branch": "dev", "size": 10}

    monkeypatch.setattr(gh, "_urlopen", FakeGitHub({"api.github.com/repos/o/r": meta}))
    m = gh.fetch_repo_metadata(gh.RepoRef("o", "r"))
    assert m.default_branch == "dev" and calls["n"] == 2 and 1 <= no_sleep[0] <= 8


def test_rate_limit_beyond_the_bound_fails_clearly(monkeypatch):
    far = str(int(time.time()) + 3600)
    monkeypatch.setattr(gh, "_urlopen", FakeGitHub({"api.github.com": lambda r: _http_error(
        r.full_url, 403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": far})}))
    with pytest.raises(gh.GitHubRateLimited, match="GitHub API rate limit"):
        gh.fetch_repo_metadata(gh.RepoRef("o", "r"))


def test_transient_errors_back_off_with_jitter(monkeypatch, no_sleep):
    seq = [_http_error("u", 502), urllib.error.URLError("reset"), {"full_name": "o/r", "default_branch": "main"}]
    monkeypatch.setattr(gh, "_urlopen", FakeGitHub({"api.github.com": lambda r: seq.pop(0)}))
    assert gh.fetch_repo_metadata(gh.RepoRef("o", "r")).default_branch == "main"
    assert len(no_sleep) == 2 and no_sleep[0] <= 1.0 and no_sleep[1] <= 2.0


def test_private_repo_messages_and_token_headers(monkeypatch):
    monkeypatch.setattr(gh, "_urlopen", FakeGitHub({}))
    with pytest.raises(gh.RepoAccessError, match="set GITHUB_TOKEN"):
        gh.fetch_repo_metadata(gh.RepoRef("o", "r"))
    monkeypatch.setenv("GITHUB_TOKEN", "t0k")
    with pytest.raises(gh.RepoAccessError, match="token has no access|GITHUB_TOKEN has no access"):
        gh.fetch_repo_metadata(gh.RepoRef("o", "r"))
    raw = gh._request("https://raw.githubusercontent.com/o/r/x/a.py", "*/*")
    assert raw.get_header("Authorization") == "Bearer t0k"
    assert "Authorization" not in raw.headers  # unredirected: never forwarded on a redirect
    assert gh._request("https://github.com/o/r.git/info/refs").get_header("Authorization").startswith("Basic ")
    assert gh._request("https://example.com/x").get_header("Authorization") is None


def test_ref_advertisement_gives_default_branch_and_shas():
    def pkt(s: str) -> bytes:
        b = s.encode()
        return f"{len(b) + 4:04x}".encode() + b
    raw = (pkt("# service=git-upload-pack\n") + b"0000" + pkt(f"{SHA} HEAD\0multi_ack symref=HEAD:refs/heads/trunk agent=git\n")
           + pkt(f"{'f' * 40} refs/heads/trunk\n") + pkt(f"{'e' * 40} refs/heads/feature/x\n") + b"0000")
    default, refs = gh.parse_ref_advertisement(raw)
    assert default == "trunk" and refs["trunk"] == "f" * 40 and refs["feature/x"] == "e" * 40


def test_zip_extracts_only_selected_files_under_caps(tmp_path, monkeypatch):
    payload = _zip({"app.py": "print(1)\n", "big.bin": "x" * 5000, "node_modules/m.js": "1"})
    monkeypatch.setattr(gh, "_urlopen", FakeGitHub({f"/zip/{SHA}": payload}))
    root, entries = gh.download_repo(gh.RepoRef("o", "r"), SHA, tmp_path / "repo", select=lambda e: ["app.py"])
    assert sorted(p for p, _ in entries) == ["app.py", "big.bin", "node_modules/m.js"]
    assert (root / "app.py").exists() and not (root / "big.bin").exists()
    with pytest.raises(gh.RepoAccessError, match="decompresses"):
        gh.download_repo(gh.RepoRef("o", "r"), SHA, tmp_path / "repo2", max_bytes=100)
    with pytest.raises(gh.RepoAccessError, match="lists"):
        gh.download_repo(gh.RepoRef("o", "r"), SHA, tmp_path / "repo3", max_members=2)


def test_selection_covers_new_languages_and_reports_skips():
    entries = [("src/App.vue", 100), ("ios/View.swift", 100), ("lib/main.dart", 100), ("infra/main.tf", 100),
               ("app/build.gradle.kts", 100), ("src/site.scss", 100), ("logo.png", 100), ("node_modules/x.js", 10),
               ("huge.py", 900_000), ("package-lock.json", 10), (".env.example", 20)]
    sel = select_files_for_download(entries)
    assert {"src/App.vue", "ios/View.swift", "lib/main.dart", "infra/main.tf", "app/build.gradle.kts",
            "src/site.scss", ".env.example"} <= set(sel)
    assert selection_report(entries, sel) == {"lockfile_or_minified": 1, "too_large": 1, "unsupported_type": 1,
                                              "vendored_or_hidden": 1}


def _agent_request(tmp_path):
    return {"github_url": "https://github.com/o/r", "workspace_dir": str(tmp_path)}


def test_agent_pins_every_file_to_the_commit_and_reports_coverage(tmp_path, monkeypatch):
    fake = FakeGitHub({
        "/commits/main": _Resp(SHA.encode()),
        f"/git/trees/{SHA}": {"truncated": False, "tree": [
            {"path": "app.py", "type": "blob", "size": 10}, {"path": "logo.png", "type": "blob", "size": 10}]},
        f"raw.githubusercontent.com/o/r/{SHA}/app.py": b"print(1)\n",
        "api.github.com/repos/o/r": {"full_name": "o/r", "default_branch": "main", "size": 1},
    })
    monkeypatch.setattr(gh, "_urlopen", fake)
    out = RepoFetchAgent({}).execute(_agent_request(tmp_path), {})
    assert out["status"] == "success" and out["commit_sha"] == SHA and out["branch"] == "main"
    cov = out["repo_coverage"]
    assert cov["files_in_tree"] == 2 and cov["selected"] == 1 and cov["fetched"] == 1
    assert cov["skipped"] == {"unsupported_type": 1} and cov["truncated"] is False and cov["source"] == "tree"
    assert out["repo_tree"] == ["app.py", "logo.png"]
    raw_urls = [r.full_url for r in fake.requests if "raw.githubusercontent" in r.full_url]
    assert raw_urls and all(f"/{SHA}/" in u for u in raw_urls)


def test_agent_truncated_tree_falls_back_to_the_zip(tmp_path, monkeypatch):
    fake = FakeGitHub({
        "/commits/main": _Resp(SHA.encode()),
        f"/git/trees/{SHA}": {"truncated": True, "tree": [{"path": "a.py", "type": "blob", "size": 5}]},
        f"/zip/{SHA}": _zip({"a.py": "x=1\n", "b.py": "y=2\n"}),
        "api.github.com/repos/o/r": {"full_name": "o/r", "default_branch": "main", "size": 1},
    })
    monkeypatch.setattr(gh, "_urlopen", fake)
    out = RepoFetchAgent({}).execute(_agent_request(tmp_path), {})
    assert out["status"] == "success" and out["repo_coverage"]["source"] == "zip"
    assert out["repo_coverage"]["files_in_tree"] == 2 and sorted(out["repo_tree"]) == ["a.py", "b.py"]


def test_agent_rate_limited_api_uses_git_refs_not_main(tmp_path, monkeypatch):
    def pkt(s: str) -> bytes:
        b = s.encode()
        return f"{len(b) + 4:04x}".encode() + b
    refs = pkt("# service=git-upload-pack\n") + b"0000" + pkt(f"{SHA} HEAD\0symref=HEAD:refs/heads/develop\n") \
        + pkt(f"{SHA} refs/heads/develop\n") + b"0000"
    limited = lambda r: _http_error(r.full_url, 429, {"Retry-After": "3600"})  # noqa: E731
    fake = FakeGitHub({"github.com/o/r.git/info/refs": refs, f"/zip/{SHA}": _zip({"a.py": "x=1\n"}),
                       "api.github.com": limited})
    monkeypatch.setattr(gh, "_urlopen", fake)
    out = RepoFetchAgent({}).execute(_agent_request(tmp_path), {})
    assert out["status"] == "success" and out["branch"] == "develop" and out["commit_sha"] == SHA
    assert out["repo_coverage"]["source"] == "zip"
