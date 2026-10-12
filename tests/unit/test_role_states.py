"""Phase 4.3 — per-role storage states before a run (tools/auth/role_states.py). No real browser:
`open_role` (Phase 2) is replaced by a fake and the browser factory is a test seam."""

import contextlib
import json
import logging
import os
import time

import pytest

import tools.auth.role_states as rs
from tools.discovery.deep.config import RoleConfig


class _Ctx:
    def __init__(self, url):
        self.closed = False
        self.page = type("P", (), {"url": url})()

    def storage_state(self, path):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"cookies": [{"name": "session", "value": "tok"}], "origins": []}, fh)

    def close(self):
        self.closed = True


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(rs.constants, "PROJECTS_BASE", str(tmp_path))
    return tmp_path


@contextlib.contextmanager
def fake_browser():
    yield object()


def fake_open_role(results):
    """results: {role name: (final url, ok, error)}"""
    contexts = {}

    def _open(browser, role, viewport=None):
        url, ok, err = results[role.name]
        ctx = _Ctx(url)
        contexts[role.name] = ctx
        return ctx, ctx.page, ({"ok": True} if ok else {"ok": False, "error": err})
    return _open, contexts


ROLES = [
    RoleConfig(name="user", strategy="setup", steps=[{"goto": "http://shop/login"},
                                                     {"fill": {"selector": "#password", "value": "alice-pass-1"}}]),
    RoleConfig(name="admin", strategy="credentials", login_url="http://shop/login",
               username_env="ADMIN_U", password_env="ADMIN_P"),
    RoleConfig(name="guest", strategy="anonymous"),
]


def test_captures_each_logging_in_role_and_skips_anonymous(project, monkeypatch, caplog):
    opener, contexts = fake_open_role({"user": ("http://shop/products", True, None),
                                       "admin": ("http://shop/admin", True, None)})
    monkeypatch.setattr("tools.discovery.deep.roles.open_role", opener)
    with caplog.at_level(logging.INFO, logger="workflow.auth.roles"):
        summary = rs.ensure_role_states("shop", ROLES, browser_factory=fake_browser)
    by = {e["name"]: e for e in summary["roles"]}
    assert by["user"]["status"] == by["admin"]["status"] == "captured"
    assert by["guest"]["status"] == "anonymous" and "path" not in by["guest"]
    assert summary["failed"] == []
    assert os.path.exists(project / "shop" / ".auth" / "user.json")
    assert os.path.exists(project / "shop" / ".auth" / "admin.json")
    assert not any(n.endswith(".tmp") for n in os.listdir(project / "shop" / ".auth"))
    assert all(c.closed for c in contexts.values())
    # nothing secret in the logs or the summary: no step values, no env values, no cookie values
    text = "\n".join(r.getMessage() for r in caplog.records) + json.dumps(summary)
    for secret in ("alice-pass-1", "tok", "ADMIN_P"):
        assert secret not in text


def test_fresh_files_are_reused_and_force_logs_in_again(project, monkeypatch):
    auth = project / "shop" / ".auth"
    auth.mkdir(parents=True)
    (auth / "user.json").write_text("{}", encoding="utf-8")
    opener, contexts = fake_open_role({"user": ("http://shop/products", True, None)})
    monkeypatch.setattr("tools.discovery.deep.roles.open_role", opener)
    summary = rs.ensure_role_states("shop", ROLES[:1], max_age_minutes=30, browser_factory=fake_browser)
    assert summary["roles"][0]["status"] == "reused" and contexts == {}
    old = time.time() - 3600
    os.utime(auth / "user.json", (old, old))
    summary = rs.ensure_role_states("shop", ROLES[:1], max_age_minutes=30, browser_factory=fake_browser)
    assert summary["roles"][0]["status"] == "captured"
    (auth / "user.json").touch()
    summary = rs.ensure_role_states("shop", ROLES[:1], force=True, browser_factory=fake_browser)
    assert summary["roles"][0]["status"] == "captured"


def test_a_login_that_stays_on_the_login_page_fails_and_is_listed(project, monkeypatch):
    opener, _ = fake_open_role({"user": ("http://shop/login?error=1", True, None),
                                "admin": ("http://shop/x", False, "RuntimeError: Environment variable 'ADMIN_U' is not set.")})
    monkeypatch.setattr("tools.discovery.deep.roles.open_role", opener)
    summary = rs.ensure_role_states("shop", ROLES, browser_factory=fake_browser)
    by = {e["name"]: e for e in summary["roles"]}
    assert by["user"]["status"] == "failed" and "login page" in by["user"]["error"]
    assert "?error" not in by["user"]["error"]                      # query strings are not echoed
    assert by["admin"]["status"] == "failed"
    assert sorted(summary["failed"]) == ["admin", "user"]
    assert not os.path.exists(project / "shop" / ".auth" / "user.json")


def test_success_url_decides_when_given(project, monkeypatch):
    role = RoleConfig(name="ops", strategy="credentials", login_url="http://shop/signin", success_url="http://shop/dash")
    opener, _ = fake_open_role({"ops": ("http://shop/elsewhere", True, None)})
    monkeypatch.setattr("tools.discovery.deep.roles.open_role", opener)
    assert rs.ensure_role_states("shop", [role], browser_factory=fake_browser)["failed"] == ["ops"]


def test_storage_state_roles_are_only_checked(project, tmp_path):
    saved = tmp_path / "saved.json"
    saved.write_text("{}", encoding="utf-8")
    roles = [RoleConfig(name="a", strategy="storageState", storage_state_path=str(saved)),
             RoleConfig(name="b", strategy="storageState", storage_state_path=str(tmp_path / "nope.json"))]

    def boom():
        raise AssertionError("no browser needed")
    summary = rs.ensure_role_states("shop", roles, browser_factory=boom)
    by = {e["name"]: e for e in summary["roles"]}
    assert by["a"]["status"] == "ok" and by["b"]["status"] == "missing"
    assert summary["failed"] == ["b"]


def test_browser_launch_failure_marks_pending_roles_failed(project):
    @contextlib.contextmanager
    def broken():
        raise RuntimeError("Executable doesn't exist")
        yield  # pragma: no cover
    summary = rs.ensure_role_states("shop", ROLES[:1], browser_factory=broken)
    assert summary["roles"][0]["status"] == "failed" and "browser launch failed" in summary["roles"][0]["error"]


def test_only_filter_and_file_names(project, monkeypatch):
    opener, contexts = fake_open_role({"admin": ("http://shop/admin", True, None)})
    monkeypatch.setattr("tools.discovery.deep.roles.open_role", opener)
    summary = rs.ensure_role_states("shop", ROLES, only=["admin"], browser_factory=fake_browser)
    assert [e["name"] for e in summary["roles"]] == ["admin"] and list(contexts) == ["admin"]
    assert rs.role_file_name("Sales Manager/EU") == "Sales_Manager_EU.json"
    assert rs.role_file_name("__") == "role.json"


def test_project_roles_reads_auth_roles_even_when_auth_disabled():
    roles = rs.project_roles({"auth": {"enabled": False, "roles": {"guest": {"anonymous": True},
                                                                  "user": {"strategy": "setup", "steps": []}}}})
    assert [(r.name, r.strategy) for r in roles] == [("guest", "anonymous"), ("user", "setup")]
    assert rs.project_roles(None) == []


def test_cli_without_roles_exits_1(project, capsys):
    (project / "shop").mkdir()
    (project / "shop" / "project.yaml").write_text("project: {name: shop}\n", encoding="utf-8")
    assert rs.main(["--project", "shop"]) == 1
    assert "declares no auth.roles" in capsys.readouterr().err
