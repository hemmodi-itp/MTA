#!/usr/bin/env python3
"""
AppEvolve Test Orchestrator CLI

Usage
-----
  # Run tests at a specific level
  python cli_appevolve.py test --level 1 --file test_SC-001_search_products.spec.ts
  python cli_appevolve.py test --level 2 --module module_dashboard
  python cli_appevolve.py test --level 3 --suite smoke
  python cli_appevolve.py test --level 4 --workflow complete_flow

  # Discovery
  python cli_appevolve.py list suites
  python cli_appevolve.py list modules
  python cli_appevolve.py list workflows

  # Headed mode
  python cli_appevolve.py test --level 3 --suite smoke --headed
"""

import argparse
import json
import sys

from tools.suite_orchestrator import SuiteOrchestrator

PROJECT_DIR = "application_assets/projects/AppEvolve"


def cmd_test(args: argparse.Namespace, orch: SuiteOrchestrator) -> int:
    headless = not args.headed
    if args.level == 1:
        if not args.file:
            print("ERROR: --file is required for --level 1", file=sys.stderr)
            return 2
        result = orch.run_individual_test(args.file, headless)
    elif args.level == 2:
        if not args.module:
            print("ERROR: --module is required for --level 2", file=sys.stderr)
            return 2
        result = orch.run_module(args.module, headless)
    elif args.level == 3:
        if not args.suite:
            print("ERROR: --suite is required for --level 3", file=sys.stderr)
            return 2
        result = orch.run_suite(args.suite, headless)
    elif args.level == 4:
        if not args.workflow:
            print("ERROR: --workflow is required for --level 4", file=sys.stderr)
            return 2
        result = orch.run_workflow(args.workflow, headless)
    else:
        print(f"ERROR: unknown level {args.level}", file=sys.stderr)
        return 2

    status = result.get("status", "unknown").upper()
    print(f"\n{'='*60}")
    print(f"  Status: {status}")
    if result.get("error"):
        print(f"  Error : {result['error']}")
    if result.get("test_count") is not None:
        print(f"  Tests : {result['test_count']}")
    print(f"{'='*60}\n")

    return 0 if result.get("status") in ("passed", "no_tests") else 1


def cmd_list(args: argparse.Namespace, orch: SuiteOrchestrator) -> int:
    resource = args.resource
    if resource == "suites":
        items = orch.list_suites()
        label = "Available suites"
    elif resource == "modules":
        items = orch.list_modules()
        label = "Available modules"
    elif resource == "workflows":
        items = orch.list_workflows()
        label = "Available workflows"
    else:
        print(f"ERROR: unknown resource '{resource}'", file=sys.stderr)
        return 2

    print(f"\n{label}:")
    if items:
        for item in items:
            print(f"  - {item}")
    else:
        print("  (none found)")
    print()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AppEvolve Test Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", help="Command")
    subparsers.required = True

    # ── test ──────────────────────────────────────────────────────────────
    test_p = subparsers.add_parser("test", help="Run tests at a given level")
    test_p.add_argument("--level", type=int, choices=[1, 2, 3, 4], required=True,
                        help="1=file 2=module 3=suite 4=workflow")
    test_p.add_argument("--file",     help="Spec filename (level 1)")
    test_p.add_argument("--module",   help="Module directory name (level 2)")
    test_p.add_argument("--suite",    help="Suite id (level 3): smoke|regression|module_navigation")
    test_p.add_argument("--workflow", help="Workflow name (level 4)")
    test_p.add_argument("--headed",   action="store_true", help="Run in headed (visible) browser mode")

    # ── list ──────────────────────────────────────────────────────────────
    list_p = subparsers.add_parser("list", help="List discoverable resources")
    list_p.add_argument("resource", choices=["suites", "modules", "workflows"])

    args = parser.parse_args()
    orch = SuiteOrchestrator(PROJECT_DIR)

    if args.command == "test":
        return cmd_test(args, orch)
    if args.command == "list":
        return cmd_list(args, orch)
    return 0


if __name__ == "__main__":
    sys.exit(main())
