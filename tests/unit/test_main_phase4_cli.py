"""Phase 4 — main.py: --auth-setup also captures auth.roles; --merge-reports; tag/shard flags reach the request."""

import sys

import pytest

import main as mta_main


@pytest.fixture
def project(tmp_path, monkeypatch):
    import tools.constants as constants
    monkeypatch.setattr(constants, "PROJECTS_BASE", str(tmp_path))
    (tmp_path / "shop").mkdir()
    return tmp_path / "shop"


def _yaml(pdir, text):
    (pdir / "project.yaml").write_text(text, encoding="utf-8")


def _stub(monkeypatch, single_ok=True, failed=()):
    seen = {"single": 0, "roles": None}

    def single(project):
        seen["single"] += 1
        if not single_ok:
            raise ValueError("auth.enabled is false")
    monkeypatch.setattr("tools.auth.auth_setup.run_auth_setup", single)

    def roles(project, roles, force=False, **kw):
        seen["roles"] = ([r.name for r in roles], force)
        return {"roles": [{"name": r.name, "strategy": r.strategy, "status": "captured"} for r in roles],
                "failed": list(failed)}
    monkeypatch.setattr("tools.auth.role_states.ensure_role_states", roles)
    return seen


def test_auth_setup_roles_only_project(project, monkeypatch, capsys):
    _yaml(project, "auth:\n  enabled: false\n  roles:\n    user: {strategy: setup, steps: [{goto: 'http://x/login'}]}\n"
                   "    guest: {anonymous: true}\n")
    seen = _stub(monkeypatch)
    assert mta_main._auth_setup("shop") == 0
    assert seen["single"] == 0 and seen["roles"] == (["user", "guest"], True)
    assert "role user" in capsys.readouterr().out


def test_auth_setup_single_identity_unchanged(project, monkeypatch):
    _yaml(project, "auth:\n  enabled: true\n  strategy: storageState\n")
    seen = _stub(monkeypatch)
    assert mta_main._auth_setup("shop") == 0
    assert seen["single"] == 1 and seen["roles"] is None


def test_auth_setup_without_any_auth_keeps_the_old_error(project, monkeypatch, capsys):
    _yaml(project, "project: {name: shop}\n")
    seen = _stub(monkeypatch, single_ok=False)
    assert mta_main._auth_setup("shop") == 1
    assert seen["single"] == 1 and "Auth setup failed" in capsys.readouterr().err


def test_auth_setup_reports_a_failed_role(project, monkeypatch):
    _yaml(project, "auth:\n  roles:\n    admin: {strategy: credentials, login_url: 'http://x/login'}\n")
    _stub(monkeypatch, failed=["admin"])
    assert mta_main._auth_setup("shop") == 1


def test_merge_reports_flag_exits_through_the_merge_cli(monkeypatch):
    called = {}
    monkeypatch.setattr("tools.execution.merge_reports.main", lambda argv: called.setdefault("argv", argv) and 0)
    monkeypatch.setattr(sys, "argv", ["main.py", "--project", "shop", "--merge-reports", "ci-1"])
    assert mta_main.main() == 0
    assert called["argv"] == ["--project", "shop", "--run", "ci-1"]
