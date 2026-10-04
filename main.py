from tools.startup import display_platform_ready, display_startup_banner, startup_status

display_startup_banner()

import argparse
import os
import sys
import uuid
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from agents.orchestrator.agent import OrchestratorAgent
from agents.registry_setup import build_default_registry
from contracts.request_models import RequestModel
from tools.file_manager import load_yaml_file
from tools.logger_config import configure_logging
from tools.persistence import save_workflow_run
from tools.test_execution.reports.ns_report import write_ns_agents_report
from workflows.workflow_loader import load_workflow


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an agentic QA workflow.")
    parser.add_argument("--project", "-p", required=True,
                        help="Project name (e.g. 'hungryMinds', 'alterdomus')")
    parser.add_argument("--workflow", "-w", default="full_workflow",
                        help="Workflow name (default: full_workflow)")
    parser.add_argument("--show-state", action="store_true",
                        help="Print the persistent project state summary and exit")
    parser.add_argument("--force-rediscover", action="store_true",
                        help="Bypass fingerprint check and re-run discovery even if content is unchanged")
    parser.add_argument("--force-execute", action="store_true",
                        help="Run all test scripts found on disk even when project state has no new_additions")
    parser.add_argument("--module", "-m", default=None,
                        help="Run pipeline for a single module only (e.g. M01). Only applies to modular projects.")
    parser.add_argument("--auth-setup", action="store_true",
                        help="Run one-time auth setup: opens browser, saves storageState to .auth/auth.json")
    parser.add_argument("--record", action="store_true",
                        help="Run a human-guided interactive recording session for --project "
                             "(and --module, if the project is modular) and exit. Opens a real "
                             "browser with a 'Finish Recording' banner; captured elements/clicks "
                             "are written to disk for the next normal discovery run to consume. "
                             "Only applies when the project's project.yaml has interactive_scan: true.")
    parser.add_argument("--suite", "-s", default=None,
                        help="Run a named test suite (e.g. 'smoke', 'regression', 'module_01'). "
                             "Bypasses new_additions guard and filters execution to suite specs.")
    args = parser.parse_args()

    # ── Auth setup and exit early ──────────────────────────────────────
    if args.auth_setup:
        from tools.auth.auth_setup import run_auth_setup
        try:
            run_auth_setup(args.project)
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            print(f"Auth setup failed: {exc}", file=sys.stderr)
            return 1
        return 0

    # ── Interactive recording and exit early ────────────────────────────
    if args.record:
        from tools.discovery.record_cli import run_interactive_recording
        try:
            run_interactive_recording(args.project, args.module)
        except (FileNotFoundError, ValueError) as exc:
            print(f"Recording failed: {exc}", file=sys.stderr)
            return 1
        return 0

    # ── Show state and exit early ──────────────────────────────────────
    if args.show_state:
        from tools.state import project_state_manager as psm
        state = psm.load(args.project)
        psm.print_summary(state)
        return 0

    base_dir = os.path.dirname(os.path.abspath(__file__))
    settings_path = os.path.join(base_dir, "workflows", "settings.yaml")
    agents_path = os.path.join(base_dir, "workflows", "agents.yaml")

    request_payload = {
        "project_name": args.project,
        "workflow": args.workflow,
        "force_rediscover": args.force_rediscover,
        "force_execute": args.force_execute,
        "module_filter": args.module,
        "suite": args.suite,
    }
    completed_steps = []

    def mark_done(label: str) -> None:
        startup_status(label)
        completed_steps.append(label)

    request = RequestModel.from_dict(request_payload)
    settings = load_yaml_file(settings_path)
    agents_config = load_yaml_file(agents_path)
    mark_done("Loading Configuration")

    configure_logging(settings)
    mark_done("Initializing Logger")

    workflow = load_workflow(request.workflow)
    mark_done("Initializing Workflow Engine")
    registry = build_default_registry(scope="legacy")
    mark_done("Registering Agents")
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    mark_done("All Systems Ready")

    display_platform_ready(
        details={
            "Provider": str(settings.get("connectors", {}).get("llm", "unknown")),
            "Environment": str(settings.get("environment", "unknown")),
            "Workflow": request.workflow,
            "Steps": str(len(workflow.steps)),
            "Run ID": run_id[:8],
            "Started At": started_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
        },
        checklist=completed_steps,
    )

    orchestrator = OrchestratorAgent(
        settings=settings,
        agents_config=agents_config,
        registry=registry,
        run_id=run_id,
    )
    result = orchestrator.run(request_payload, workflow)
    final_report = result["final_report"]

    run_file = save_workflow_run(
        run_id,
        {
            "run_id": run_id,
            "project": args.project,
            "workflow": request.workflow,
            "started_at": started_at.isoformat(),
            "status": final_report["status"],
            "execution_trace": final_report["execution_trace"],
            "errors": final_report["errors"],
            "outputs": result["state"].outputs,
        },
        project=args.project,
        started_at=started_at,
    )

    print("Workflow completed")
    print(f"Run ID:   {run_id}")
    print(f"Project:  {args.project}")
    print(f"Workflow: {final_report['workflow']}")
    print(f"Status:   {final_report['status']}")
    print(f"Steps:    {final_report['steps_executed']}")
    outputs = result["state"].outputs
    if outputs:
        print("Step outputs:")
        for step, output in outputs.items():
            display = {k: v for k, v in output.items() if k not in ("module", "ns_connector")}
            preview = str(display)[:100]
            print(f"  Response --> {step} --> {preview}...")
    if final_report.get("errors"):
        print("Errors:")
        for err in final_report["errors"]:
            print(f"  {err.get('step', '?')}: {err.get('reason', err)}")
    ns_trace = result.get("ns_call_trace", [])
    if ns_trace:
        ns_report = write_ns_agents_report(
            project=args.project,
            run_id=run_id,
            workflow=request.workflow,
            started_at=started_at,
            ns_call_trace=ns_trace,
        )
        print(f"NS report:    {os.path.relpath(ns_report)}")

    print(f"Run saved to: {os.path.relpath(run_file)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
