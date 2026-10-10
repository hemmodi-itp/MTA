"""Phase 0.5 — SafetyPolicy (project.yaml environment + safety) and host matching."""

import os

import pytest
import yaml

from tools.safety.hosts import host_matches, normalize_hosts, parse_host_entry, url_allowed
from tools.safety.policy import (
    SafetyPolicy,
    derive_allowed_hosts,
    load_safety_policy,
    normalize_environment,
)


@pytest.mark.parametrize("raw,expected", [
    ("local", "local"), ("dev", "dev"), ("staging", "staging"), ("prod", "prod"),
    ("Production", "prod"), ("development", "dev"), ("stage", "staging"),
    (None, "unspecified"), ("qa-cluster-7", "unspecified"), ("", "unspecified"),
])
def test_normalize_environment(raw, expected):
    assert normalize_environment(raw) == expected


@pytest.mark.parametrize("env,allow,expected", [
    ("local", True, True), ("dev", True, True), ("staging", True, True),
    ("prod", True, False),          # prod always refuses, whatever the flag
    (None, True, False),            # undeclared env is gated like prod
    ("local", False, False), ("prod", False, False),
])
def test_destructive_and_probe_gating_matrix(env, allow, expected):
    raw = {"safety": {"allow_destructive": allow, "allow_security_probes": allow}}
    if env is not None:
        raw["environment"] = env
    policy = SafetyPolicy.from_project_config(raw)
    assert policy.destructive_allowed is expected
    assert policy.security_probes_allowed is expected


def test_defaults_are_most_restrictive():
    policy = SafetyPolicy.from_project_config({})
    assert policy.environment == "unspecified"
    assert policy.environment_declared is False
    assert policy.allow_destructive is False
    assert policy.allow_security_probes is False


def test_flags_accept_string_booleans():
    policy = SafetyPolicy.from_project_config(
        {"environment": "dev", "safety": {"allow_destructive": "yes", "allow_security_probes": "false"}}
    )
    assert policy.destructive_allowed is True
    assert policy.security_probes_allowed is False


def test_allowed_hosts_derived_from_project_urls():
    raw = {
        "project": {"url": "https://app.example.com/home"},
        "modules": [
            {"id": "M01", "url": "https://app.example.com/login"},
            {"id": "M02", "url": "http://127.0.0.1:8765/products",
             "setup": [{"goto": "https://sso.example.org/auth"}, {"click": "#go"}]},
        ],
        "auth": {"setup_url": "https://idp.example.net/login", "wait_for_url": "https://app.example.com/dash"},
    }
    hosts = derive_allowed_hosts(raw)
    assert hosts == ["app.example.com", "127.0.0.1:8765", "sso.example.org", "idp.example.net"]
    policy = SafetyPolicy.from_project_config(raw)
    assert policy.allowed_hosts_source == "derived"
    assert policy.url_allowed("https://app.example.com/anything")
    assert not policy.url_allowed("https://evil.example.com/")


def test_explicit_allowed_hosts_replace_derived():
    raw = {"project": {"url": "https://app.example.com"},
           "safety": {"allowed_hosts": ["api.example.com", "*.cdn.example.com"]}}
    policy = SafetyPolicy.from_project_config(raw)
    assert policy.allowed_hosts_source == "explicit"
    assert policy.allowed_hosts == ["api.example.com", "*.cdn.example.com"]
    assert not policy.url_allowed("https://app.example.com/")
    assert policy.url_allowed("https://img.cdn.example.com/x.png")


@pytest.mark.parametrize("url,allowed,expected", [
    ("/relative/path", [], True),
    ("", [], True),
    (None, [], True),
    ("?q=1", ["a.com"], True),
    ("about:blank", [], True),
    ("javascript:alert(1)", ["a.com"], False),
    ("file:///etc/passwd", ["a.com"], False),
    ("https://a.com/x", ["a.com"], True),
    ("https://A.COM/x", ["a.com"], True),
    ("https://b.a.com/x", ["a.com"], False),
    ("https://b.a.com/x", ["*.a.com"], True),
    ("https://a.com/x", ["*.a.com"], False),          # wildcard excludes the apex
    ("http://127.0.0.1:8765/p", ["127.0.0.1"], True),  # host without port = any port
    ("http://127.0.0.1:8765/p", ["127.0.0.1:8765"], True),
    ("http://127.0.0.1:9999/p", ["127.0.0.1:8765"], False),
    ("//a.com/x", ["a.com"], True),
    ("https://a.com.evil.net/", ["a.com"], False),
])
def test_url_allowed(url, allowed, expected):
    assert url_allowed(url, allowed) is expected


def test_host_entry_parsing_and_normalization():
    assert parse_host_entry("https://Example.com:8080/x") == ("example.com", 8080)
    assert parse_host_entry("  ") is None
    assert normalize_hosts(["A.com", "a.com", "https://a.com/x", "b.com:81"]) == ["a.com", "b.com:81"]
    assert host_matches("x.y.com", None, ["*.y.com"]) is True


def test_request_round_trip():
    policy = SafetyPolicy.from_project_config(
        {"environment": "local", "safety": {"allow_destructive": True}, "project": {"url": "http://h"}}
    )
    data = policy.to_request()
    assert data["destructive_allowed"] is True
    again = SafetyPolicy.from_request(data)
    assert again == policy
    assert SafetyPolicy.from_request(None) == SafetyPolicy()


def test_load_safety_policy_from_project_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.constants.PROJECTS_BASE", str(tmp_path))
    proj = tmp_path / "demo"
    proj.mkdir()
    (proj / "project.yaml").write_text(yaml.safe_dump(
        {"environment": "staging", "safety": {"allow_destructive": True},
         "modules": [{"id": "M01", "url": "https://demo.test/"}]}), encoding="utf-8")
    policy = load_safety_policy("demo", warn=False)
    assert policy.destructive_allowed is True
    assert policy.allowed_hosts == ["demo.test"]
    assert load_safety_policy("missing", warn=False) == SafetyPolicy()


def test_unspecified_environment_warns(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr("tools.constants.PROJECTS_BASE", str(tmp_path))
    (tmp_path / "old").mkdir()
    (tmp_path / "old" / "project.yaml").write_text("project: {name: old}\n", encoding="utf-8")
    with caplog.at_level("WARNING", logger="workflow.safety"):
        load_safety_policy("old")
    assert any("declares no `environment:`" in r.message for r in caplog.records)


def test_manifest_carries_policy_and_contracts(tmp_path, monkeypatch):
    import tools.project_manifest as pm

    monkeypatch.setattr(pm, "_PROJECTS_DIR", str(tmp_path))
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "project.yaml").write_text(yaml.safe_dump({
        "project": {"name": "p"}, "environment": "dev",
        "safety": {"allow_destructive": True}, "contracts": {"enforce": "block"},
        "modules": [{"id": "M01", "url": "https://p.test/"}],
    }), encoding="utf-8")
    flat = pm.load_project_manifest("p")
    assert flat["environment"] == "dev"
    assert flat["safety"]["destructive_allowed"] is True
    assert flat["safety"]["allowed_hosts"] == ["p.test"]
    assert flat["contracts"] == {"enforce": "block"}


@pytest.mark.parametrize("value,expected", [("warn", "warn"), ("BLOCK", "block"), ("nonsense", "warn"), (None, "warn")])
def test_contracts_enforce_values(value, expected):
    from tools.project_manifest import resolve_contracts_config

    raw = {"contracts": {"enforce": value}} if value is not None else {}
    assert resolve_contracts_config(raw) == {"enforce": expected}
