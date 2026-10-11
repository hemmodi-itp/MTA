"""
config.py — the `discovery:` and `auth.roles:` blocks of project.yaml (Phase 2).

    discovery:
      deep: false               # master switch (default off; plan principle 4)
      max_pages: 25             # per role
      max_depth: 4
      max_minutes: 10           # the whole deep pass, all roles
      samples_per_template: 1
      reuse_minutes: 60
      capture:    {frames: true, shadow: true, cursor_pointer: true, max_pointer: 300}
      expanders: true
      max_expanders_per_state: 20
      validation: {enabled: true, max_probes_per_form: 20, long_text_length: 1000}
      network: true
      baseline: true

    auth:
      roles:                    # read even when auth.enabled is false
        admin: {strategy: credentials, login_url: …, username_env: …, password_env: …, …}
        user:  {strategy: storageState, storage_state_path: .auth/user.json}
        alice: {strategy: setup, steps: [{goto: …}, {fill: {selector: …, value_env: …}}, {click: …}]}
        guest: {anonymous: true}
"""

import hashlib
import json
import logging
import os
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

_log = logging.getLogger("workflow.discovery.deep")


class CaptureConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    frames: bool = True
    shadow: bool = True
    cursor_pointer: bool = True
    max_pointer: int = Field(300, ge=0, le=5000)


class ValidationConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    enabled: bool = True
    max_probes_per_form: int = Field(20, ge=1, le=500)
    long_text_length: int = Field(1000, ge=2, le=100_000)


class DiscoveryConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    deep: bool = False
    max_pages: int = Field(25, ge=1, le=1000)
    max_depth: int = Field(4, ge=0, le=50)
    max_minutes: float = Field(10, gt=0, le=600)
    samples_per_template: int = Field(1, ge=1, le=50)
    reuse_minutes: float = Field(60, ge=0)
    capture: CaptureConfig = Field(default_factory=CaptureConfig)
    expanders: bool = True
    max_expanders_per_state: int = Field(20, ge=0, le=500)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    network: bool = True
    baseline: bool = True


Strategy = Literal["credentials", "storageState", "setup", "anonymous"]


class RoleConfig(BaseModel):
    """One identity the crawler signs in as. Secrets come from env vars (credentials) or from
    setup steps the project already declares; nothing here is written to an artifact."""
    model_config = ConfigDict(extra="allow")
    name: str
    strategy: Strategy = "anonymous"
    # credentials (live login; tools/auth/live_login.perform_login keys)
    login_url: Optional[str] = None
    success_url: Optional[str] = None
    username_env: Optional[str] = None
    password_env: Optional[str] = None
    username_selector: Optional[str] = None
    password_selector: Optional[str] = None
    submit_selector: Optional[str] = None
    # storageState
    storage_state_path: Optional[str] = None
    # setup
    steps: List[Dict[str, Any]] = Field(default_factory=list)

    @field_validator("steps", mode="before")
    @classmethod
    def _steps_are_dicts(cls, v):
        # a malformed step is dropped, not the whole role (setup steps are free-form YAML)
        return [s for s in (v or []) if isinstance(s, dict) and s]

    def public(self) -> Dict[str, Any]:
        """What may appear in an artifact: the role name and strategy, never selectors or values."""
        return {"name": self.name, "strategy": self.strategy}


def resolve_discovery_config(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """project.yaml dict -> JSON-safe discovery config (defaults filled; invalid values -> defaults + warning)."""
    raw = raw if isinstance(raw, dict) else {}
    block = raw.get("discovery") if isinstance(raw.get("discovery"), dict) else {}
    try:
        cfg = DiscoveryConfig(**block)
    except ValidationError as exc:
        _log.warning("[discovery] invalid `discovery:` block (%s) — using defaults", exc.errors()[:3])
        cfg = DiscoveryConfig(deep=bool(block.get("deep", False)))
    return cfg.model_dump()


def load_config(data: Optional[Dict[str, Any]]) -> DiscoveryConfig:
    """Request dict (`request['discovery']`) -> DiscoveryConfig."""
    if isinstance(data, DiscoveryConfig):
        return data
    try:
        return DiscoveryConfig(**(data or {}))
    except ValidationError:
        return DiscoveryConfig()


def resolve_roles(raw: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """`auth.roles` -> list of role dicts (read regardless of auth.enabled). Invalid roles are
    skipped with one warning each; `anonymous: true` is shorthand for strategy anonymous."""
    raw = raw if isinstance(raw, dict) else {}
    auth = raw.get("auth") if isinstance(raw.get("auth"), dict) else {}
    roles = auth.get("roles") if isinstance(auth.get("roles"), dict) else {}
    out: List[Dict[str, Any]] = []
    for name, spec in roles.items():
        spec = dict(spec) if isinstance(spec, dict) else {}
        if spec.pop("anonymous", False):
            spec["strategy"] = "anonymous"
        try:
            out.append(RoleConfig(name=str(name), **spec).model_dump())
        except ValidationError as exc:
            _log.warning("[discovery] auth.roles.%s is invalid (%s) — role skipped", name, exc.errors()[:2])
    return out


def load_roles(data: Optional[List[Dict[str, Any]]]) -> List[RoleConfig]:
    out = []
    for r in data or []:
        try:
            out.append(r if isinstance(r, RoleConfig) else RoleConfig(**r))
        except ValidationError:
            continue
    return out


def config_hash(cfg: DiscoveryConfig, roles: List[RoleConfig], seeds: List[str], safety: Dict[str, Any]) -> str:
    """Changes whenever anything that shapes the crawl changes (reuse key for app_map.json)."""
    payload = {
        "discovery": cfg.model_dump(),
        "roles": [{**r.model_dump(), "storage_mtime": _mtime(r.storage_state_path)} for r in roles],
        "seeds": list(seeds),
        "safety": {k: safety.get(k) for k in ("environment", "allowed_hosts", "allow_destructive",
                                               "allow_security_probes")},
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _mtime(path: Optional[str]) -> Optional[float]:
    try:
        return os.path.getmtime(path) if path else None
    except OSError:
        return None
