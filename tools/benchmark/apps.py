"""
apps.py — benchmark app registry (Phase 0.2/0.3).

Each entry says how to start the app, where its ground truth lives, and how its
BRD is split per MTA module.
"""

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List

import yaml

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


@dataclass(frozen=True)
class BenchmarkApp:
    name: str
    module: str                      # python -m <module> --port N
    app_dir: str                     # benchmarks/apps/<name>
    health_path: str
    default_port: int
    project_name: str                # generated MTA project folder (gitignored)
    module_reqs: Dict[str, List[str]] = field(default_factory=dict)  # MTA module -> REQ ids

    @property
    def bugs_yaml(self) -> str:
        return os.path.join(self.app_dir, "bugs.yaml")

    @property
    def brd_path(self) -> str:
        return os.path.join(self.app_dir, "brd.md")

    @property
    def template_path(self) -> str:
        return os.path.join(self.app_dir, "mta_project", "project.yaml.tmpl")


APPS: Dict[str, BenchmarkApp] = {
    "buggy_shop": BenchmarkApp(
        name="buggy_shop",
        module="benchmarks.apps.buggy_shop",
        app_dir=os.path.join(REPO_ROOT, "benchmarks", "apps", "buggy_shop"),
        health_path="/api/health",
        default_port=8765,
        project_name="bench_buggy_shop",
        module_reqs={
            "M01": ["REQ-01"],
            "M02": ["REQ-02", "REQ-08"],
            "M03": ["REQ-03"],
            "M04": ["REQ-05", "REQ-06"],
            "M05": ["REQ-04"],
            "M06": ["REQ-07"],
        },
    ),
}


def load_bugs(app: BenchmarkApp) -> List[dict]:
    with open(app.bugs_yaml, encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("bugs", [])


_AC_LINE = re.compile(r"^\s*-\s*(AC-\d+\.\d+)\s*:", re.M)


def load_acs(app: BenchmarkApp) -> List[str]:
    """Every acceptance-criterion id declared in the app's BRD (`- AC-xx.y: ...`)."""
    with open(app.brd_path, encoding="utf-8") as f:
        return sorted(set(_AC_LINE.findall(f.read())))
