"""
suite_orchestrator.py — 4-level test execution orchestrator for AppEvolve.

Level 1 : individual test file  (one scenario spec)
Level 2 : module                (all specs in a module directory)
Level 3 : test suite            (smoke / regression / per-module, defined in test_suites/)
Level 4 : workflow              (multi-step spec in test_scripts/workflows/)
"""

import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional


def resolve_suite_spec_files(project_dir: str, suite_name: str) -> List[Dict[str, Any]]:
    """Return resolved entries for a named suite.

    Each entry is {"path": Path, "grep": Optional[str]}.
    - path  : absolute path to the .spec.ts file
    - grep  : Playwright --grep pattern, or None to run the entire spec

    Scenario entries in the suite JSON may be:
      "SC-M01-001"                          plain string  → whole spec, no grep
      {"id": "SC-M01-001"}                  dict, no grep → whole spec, no grep
      {"id": "SC-M01-001", "grep": "text"}  dict with grep → filtered run
    """
    project_path = Path(project_dir)
    suite_file = project_path / "test_suites" / f"{suite_name}_suite.json"
    manifest_file = project_path / "test_creation" / "test_suite.json"
    scripts_root = project_path / "test_creation" / "test_scripts"

    if not suite_file.exists():
        raise FileNotFoundError(f"Suite file not found: {suite_file}")
    if not manifest_file.exists():
        raise FileNotFoundError(f"test_suite.json manifest not found: {manifest_file}")

    with open(suite_file, encoding="utf-8") as f:
        suite_config = json.load(f)
    with open(manifest_file, encoding="utf-8") as f:
        specs = json.load(f).get("specs", [])

    # Index by module → sorted list of specs
    module_specs: Dict[str, list] = defaultdict(list)
    for s in specs:
        module_specs[s["module_id"]].append(s)
    for mid in module_specs:
        module_specs[mid].sort(key=lambda s: s["spec_id"])

    if suite_config.get("all_modules"):
        return [
            {"path": scripts_root / s["file"], "grep": None}
            for s in specs
            if (scripts_root / s["file"]).exists()
        ]

    result: List[Dict[str, Any]] = []
    for scenario in suite_config.get("scenarios", []):
        entry = _resolve_scenario(scenario, module_specs, scripts_root)
        if entry:
            result.append(entry)
    return result


def _resolve_scenario(
    scenario: Any,
    module_specs: Dict[str, list],
    scripts_root: Path,
) -> Optional[Dict[str, Any]]:
    """Resolve one scenario entry (string or dict) to {"path": Path, "grep": Optional[str]}."""
    if isinstance(scenario, dict):
        scenario_id = scenario.get("id", "")
        grep_pattern: Optional[str] = scenario.get("grep") or None
    else:
        scenario_id = scenario
        grep_pattern = None

    path = _resolve_scenario_id(scenario_id, module_specs, scripts_root)
    if path is None:
        return None
    return {"path": path, "grep": grep_pattern}


def _resolve_scenario_id(
    scenario_id: str,
    module_specs: Dict[str, list],
    scripts_root: Path,
) -> Optional[Path]:
    # SC-M01-003 — ordinal within a module
    sc_match = re.match(r"^SC-([A-Z]\d+)-(\d+)$", scenario_id)
    if sc_match:
        module_id = sc_match.group(1)
        seq = int(sc_match.group(2))
        specs_in_module = module_specs.get(module_id, [])
        if not specs_in_module:
            print(f"[suite_resolver] WARNING: '{scenario_id}' — module '{module_id}' not in manifest", file=sys.stderr)
            return None
        if seq < 1 or seq > len(specs_in_module):
            print(f"[suite_resolver] WARNING: '{scenario_id}' — index {seq} out of range ({len(specs_in_module)} specs in {module_id})", file=sys.stderr)
            return None
        spec = specs_in_module[seq - 1]
        path = scripts_root / spec["file"]
        if not path.exists():
            print(f"[suite_resolver] WARNING: '{scenario_id}' → '{spec['file']}' not found on disk", file=sys.stderr)
            return None
        return path

    # Direct spec_id match — covers every scheme script_generation has ever
    # used: legacy hyphenated ("BS-001", "SC-001") and the current
    # module-scoped underscore scheme ("M03_BS_006"). A real spec_id lookup
    # against the manifest is correct regardless of the id's shape, so this
    # is tried for anything that isn't the SC-M01-003 ordinal form above.
    for specs in module_specs.values():
        for s in specs:
            if s["spec_id"] == scenario_id:
                path = scripts_root / s["file"]
                if not path.exists():
                    print(f"[suite_resolver] WARNING: '{scenario_id}' → '{s['file']}' not found on disk", file=sys.stderr)
                    return None
                return path

    print(f"[suite_resolver] WARNING: '{scenario_id}' not found in manifest", file=sys.stderr)
    return None


class SuiteOrchestrator:
    def __init__(self, project_dir: str) -> None:
        self.project_dir = Path(project_dir)
        self.test_suites_dir = self.project_dir / "test_suites"
        self.test_scripts_dir = self.project_dir / "test_creation" / "test_scripts"
        self.comprehension_dir = self.project_dir / "test_comprehension"

    # ── Level 1: individual test file ─────────────────────────────────────

    def run_individual_test(self, test_file: str, headless: bool = True) -> Dict[str, Any]:
        """Run a single .spec.ts file from the individual/ directory."""
        test_path = self.test_scripts_dir / "individual" / test_file
        if not test_path.exists():
            return self._not_found(1, "test_file", test_file, test_path)

        cmd = self._playwright_cmd(str(test_path), workers=1, headless=headless)
        return self._run(cmd, level=1, key="test_file", value=test_file)

    # ── Level 2: module ────────────────────────────────────────────────────

    def run_module(self, module_name: str, headless: bool = True) -> Dict[str, Any]:
        """Run all .spec.ts files in a module sub-directory."""
        module_dir = self.test_scripts_dir / module_name
        if not module_dir.exists():
            return self._not_found(2, "module", module_name, module_dir)

        test_files = sorted(module_dir.glob("*.spec.ts"))
        if not test_files:
            return {"level": 2, "module": module_name, "status": "no_tests", "test_count": 0}

        cmd = self._playwright_cmd(
            " ".join(str(f) for f in test_files), workers=4, headless=headless
        )
        result = self._run(cmd, level=2, key="module", value=module_name)
        result["test_count"] = len(test_files)
        return result

    # ── Level 3: test suite ────────────────────────────────────────────────

    def run_suite(self, suite_name: str, headless: bool = True) -> Dict[str, Any]:
        """Run a named suite defined in test_suites/<suite_name>_suite.json."""
        suite_file = self.test_suites_dir / f"{suite_name}_suite.json"
        if not suite_file.exists():
            return self._not_found(3, "suite", suite_name, suite_file)

        with open(suite_file, encoding="utf-8") as f:
            suite_config = json.load(f)

        test_files = self._resolve_suite_files(suite_config)
        if not test_files:
            return {
                "level": 3,
                "suite": suite_name,
                "status": "no_tests",
                "scenario_count": len(suite_config.get("scenarios", [])),
            }

        workers = suite_config.get("execution", {}).get("parallel", 4)
        cmd = self._playwright_cmd(
            " ".join(str(f) for f in test_files), workers=workers, headless=headless
        )
        result = self._run(cmd, level=3, key="suite", value=suite_name)
        result["scenario_count"] = len(suite_config.get("scenarios", []))
        result["test_count"] = len(test_files)
        return result

    # ── Level 4: workflow ─────────────────────────────────────────────────

    def run_workflow(self, workflow_name: str, headless: bool = True) -> Dict[str, Any]:
        """Run a multi-step workflow spec from test_scripts/workflows/."""
        workflow_file = self.test_scripts_dir / "workflows" / f"{workflow_name}.spec.ts"
        if not workflow_file.exists():
            return self._not_found(4, "workflow", workflow_name, workflow_file)

        cmd = self._playwright_cmd(str(workflow_file), workers=1, headless=headless)
        return self._run(cmd, level=4, key="workflow", value=workflow_name)

    # ── Discovery helpers ─────────────────────────────────────────────────

    def list_suites(self) -> List[str]:
        if not self.test_suites_dir.exists():
            return []
        return sorted(
            f.stem.replace("_suite", "")
            for f in self.test_suites_dir.glob("*_suite.json")
        )

    def list_modules(self) -> List[str]:
        if not self.test_scripts_dir.exists():
            return []
        return sorted(
            d.name
            for d in self.test_scripts_dir.iterdir()
            if d.is_dir() and d.name.startswith("module_")
        )

    def list_workflows(self) -> List[str]:
        workflows_dir = self.test_scripts_dir / "workflows"
        if not workflows_dir.exists():
            return []
        return sorted(f.stem for f in workflows_dir.glob("*.spec.ts"))

    # ── Internal helpers ───────────────────────────────────────────────────

    def _resolve_suite_files(self, suite_config: dict) -> List[Path]:
        """Return the set of test files that belong to this suite."""
        individual_dir = self.test_scripts_dir / "individual"
        test_files: List[Path] = []

        if suite_config.get("all_modules"):
            if individual_dir.exists():
                test_files = sorted(individual_dir.glob("*.spec.ts"))
        else:
            for scenario_id in suite_config.get("scenarios", []):
                matches = sorted(individual_dir.glob(f"test_{scenario_id}_*.spec.ts"))
                test_files.extend(matches)

        return test_files

    @staticmethod
    def _playwright_cmd(targets: str, workers: int, headless: bool) -> str:
        cmd = f"npx playwright test {targets} --workers={workers}"
        if not headless:
            cmd += " --headed"
        return cmd

    @staticmethod
    def _run(cmd: str, level: int, key: str, value: str) -> Dict[str, Any]:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return {
            "level": level,
            key: value,
            "status": "passed" if result.returncode == 0 else "failed",
            "returncode": result.returncode,
            "output": result.stdout + result.stderr,
        }

    @staticmethod
    def _not_found(
        level: int, key: str, value: str, path: Path
    ) -> Dict[str, Any]:
        return {
            "level": level,
            key: value,
            "status": "error",
            "error": f"Not found: {path}",
        }


# ── CLI ────────────────────────────────────────────────────────────────────

def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="4-level test executor")
    parser.add_argument("--project", required=True, help="Project directory path")
    parser.add_argument(
        "--level", type=int, choices=[1, 2, 3, 4], required=True,
        help="1=file 2=module 3=suite 4=workflow",
    )
    parser.add_argument("--target", required=True, help="File / module / suite / workflow name")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    orch = SuiteOrchestrator(args.project)
    dispatch = {
        1: lambda: orch.run_individual_test(args.target, not args.headed),
        2: lambda: orch.run_module(args.target, not args.headed),
        3: lambda: orch.run_suite(args.target, not args.headed),
        4: lambda: orch.run_workflow(args.target, not args.headed),
    }
    result = dispatch[args.level]()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("status") in ("passed", "no_tests") else 1)


if __name__ == "__main__":
    _cli()
