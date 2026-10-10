"""
policy.py — the per-project safety policy (project.yaml `environment:` + `safety:`).

    environment: local | dev | staging | prod       # missing -> "unspecified"
    safety:
      allow_destructive: false
      allow_security_probes: false
      allowed_hosts: [myapp.example.com]           # missing -> derived from the project's URLs

Rules (docs/phases/phase-0-design.md §6):
  * Destructive actions run only when allow_destructive is true AND the environment
    is local/dev/staging. "prod" and "unspecified" always refuse.
  * Active security probes: same rule, on allow_security_probes. prod/unspecified
    always refuse, whatever the flags say.
  * A missing `environment` is not an error (existing projects keep running), but it
    is gated exactly like prod and a warning is logged.
"""

import logging
import os
from typing import Any, Dict, Iterable, List, Literal, Optional

import yaml
from pydantic import BaseModel, Field

from tools.safety.hosts import normalize_hosts, url_allowed

_log = logging.getLogger("workflow.safety")

ENVIRONMENTS = ("local", "dev", "staging", "prod")
_NON_PROD = {"local", "dev", "staging"}
_ALIASES = {
    "production": "prod",
    "live": "prod",
    "development": "dev",
    "develop": "dev",
    "stage": "staging",
    "localhost": "local",
}

Environment = Literal["local", "dev", "staging", "prod", "unspecified"]


def normalize_environment(value: Any) -> str:
    """Map a raw `environment:` value to one of ENVIRONMENTS or 'unspecified'."""
    if value is None:
        return "unspecified"
    text = str(value).strip().lower()
    text = _ALIASES.get(text, text)
    return text if text in ENVIRONMENTS else "unspecified"


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def derive_allowed_hosts(raw: Dict[str, Any]) -> List[str]:
    """Hosts implied by the project's own URLs: project.url, modules[].url,
    modules[].setup[].goto, auth.setup_url / auth.wait_for_url."""
    urls: List[str] = []
    project = raw.get("project") or {}
    if isinstance(project, dict) and project.get("url"):
        urls.append(project["url"])
    for mod in raw.get("modules") or []:
        if not isinstance(mod, dict):
            continue
        if mod.get("url"):
            urls.append(mod["url"])
        for step in mod.get("setup") or []:
            if isinstance(step, dict) and isinstance(step.get("goto"), str):
                urls.append(step["goto"])
    auth = raw.get("auth") or {}
    if isinstance(auth, dict):
        for key in ("setup_url", "wait_for_url"):
            if isinstance(auth.get(key), str):
                urls.append(auth[key])
    return normalize_hosts(u for u in urls if isinstance(u, str) and "://" in u)


class SafetyPolicy(BaseModel):
    environment: Environment = "unspecified"
    environment_declared: bool = False
    allow_destructive: bool = False
    allow_security_probes: bool = False
    allowed_hosts: List[str] = Field(default_factory=list)
    allowed_hosts_source: Literal["explicit", "derived"] = "derived"

    @property
    def non_prod(self) -> bool:
        return self.environment in _NON_PROD

    @property
    def destructive_allowed(self) -> bool:
        return self.allow_destructive and self.non_prod

    @property
    def security_probes_allowed(self) -> bool:
        return self.allow_security_probes and self.non_prod

    def url_allowed(self, url: Optional[str]) -> bool:
        return url_allowed(url, self.allowed_hosts)

    def to_request(self) -> Dict[str, Any]:
        """JSON-safe dict carried in the orchestrator request (`request['safety']`)."""
        data = self.model_dump()
        data["destructive_allowed"] = self.destructive_allowed
        data["security_probes_allowed"] = self.security_probes_allowed
        return data

    @classmethod
    def from_request(cls, data: Optional[Dict[str, Any]]) -> "SafetyPolicy":
        if not isinstance(data, dict):
            return cls()
        known = {k: v for k, v in data.items() if k in cls.model_fields}
        return cls(**known)

    @classmethod
    def from_project_config(cls, raw: Optional[Dict[str, Any]]) -> "SafetyPolicy":
        raw = raw if isinstance(raw, dict) else {}
        env_raw = raw.get("environment")
        safety = raw.get("safety") if isinstance(raw.get("safety"), dict) else {}
        explicit_hosts = safety.get("allowed_hosts")
        if isinstance(explicit_hosts, (list, tuple)):
            hosts = normalize_hosts(str(h) for h in explicit_hosts)
            source = "explicit"
        else:
            hosts = derive_allowed_hosts(raw)
            source = "derived"
        return cls(
            environment=normalize_environment(env_raw),
            environment_declared=env_raw is not None,
            allow_destructive=_as_bool(safety.get("allow_destructive", False)),
            allow_security_probes=_as_bool(safety.get("allow_security_probes", False)),
            allowed_hosts=hosts,
            allowed_hosts_source=source,
        )


def load_safety_policy(project_name: str, warn: bool = True) -> SafetyPolicy:
    """Read application_assets/projects/<project>/project.yaml and build its policy.
    A missing/unreadable file yields the most restrictive default policy."""
    from tools import constants  # read at call time so test isolation applies

    path = os.path.join(constants.PROJECTS_BASE, project_name, "project.yaml")
    raw: Dict[str, Any] = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
        except Exception as exc:  # unreadable manifest -> restrictive default
            _log.warning("[safety] could not read %s (%s) — using restrictive defaults", path, exc)
            raw = {}
    policy = SafetyPolicy.from_project_config(raw)
    if warn:
        warn_if_unspecified(policy, project_name)
    return policy


def warn_if_unspecified(policy: SafetyPolicy, project_name: str) -> None:
    if not policy.environment_declared:
        _log.warning(
            "[safety] project '%s' declares no `environment:` in project.yaml — treated as "
            "'unspecified' (gated like prod: destructive actions and security probes are refused). "
            "Add `environment: local|dev|staging|prod`.",
            project_name,
        )


def hosts_env_value(hosts: Iterable[str]) -> str:
    """Value for the MTA_ALLOWED_HOSTS env var read by the TS runtime."""
    return ",".join(hosts)
