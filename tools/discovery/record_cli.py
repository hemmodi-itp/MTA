"""
record_cli.py — human-guided interactive recording, run via:

    python main.py --project <name> [--module <id>] --record

Resolves the module's URL/setup_steps/auth exactly the way a normal pipeline
run would (reusing tools.project_manifest, the same code OrchestratorAgent
uses), then drives tools.interactive_scanner directly — outside the timed
discovery step entirely, so a human taking as long as they like to click
around never races a pipeline timeout. Captured elements/clicks are written
to disk by tools.discovery.interactive_dom_scan for the next normal
`python main.py --project <name> --module <id>` run to consume.
"""

import os

from tools.constants import PROJECTS_BASE as _ASSETS_BASE
from tools.discovery.interactive_dom_scan import save_dom_scan_interactive, scan_dom_interactive
from tools.discovery.paths import comprehension_scan_dir
from tools.project_manifest import load_project_manifest, narrow_to_module


def run_interactive_recording(project_name: str, module_filter: str = None) -> str:
    """
    Execute one interactive recording session for *project_name* (optionally
    narrowed to *module_filter*). Returns the directory the artifacts were
    written to.

    Raises:
        FileNotFoundError — project.yaml not found
        ValueError        — interactive_scan not enabled, or no URL resolved,
                             or module_filter doesn't match any declared module
    """
    safe = _safe_name(project_name)
    manifest_path = os.path.join(_ASSETS_BASE, safe, "project.yaml")
    if not os.path.exists(manifest_path):
        raise FileNotFoundError(
            f"project.yaml not found at '{manifest_path}'. "
            "Ensure the project directory exists under application_assets/projects/."
        )

    flat = load_project_manifest(project_name)
    if not flat.get("interactive_scan"):
        raise ValueError(
            f"project.yaml for '{project_name}' does not have interactive_scan: true — "
            "recording only applies to interactive-scan projects."
        )

    flat = narrow_to_module(flat, module_filter, project_name)
    url = flat.get("url")
    if not url:
        raise ValueError(
            f"No URL resolved for project '{project_name}'"
            + (f", module '{module_filter}'" if module_filter else "")
            + " — check project.yaml."
        )

    auth = flat.get("auth", {})
    storage_state_path = auth.get("storage_state_path", "") or None
    if storage_state_path and not os.path.exists(storage_state_path):
        storage_state_path = None
    live_auth = auth if auth.get("strategy") == "live_login" else None
    setup_steps = flat.get("setup_steps")
    browser = flat.get("browser", "chromium")

    comp_root = os.path.join(_ASSETS_BASE, safe, "test_comprehension")
    output_dir = comprehension_scan_dir(comp_root, module_filter)
    checkpoint_path = os.path.join(output_dir, ".scan_checkpoint.json")
    resume = os.path.exists(checkpoint_path)

    print(f"\n{'='*60}")
    print(f"  Interactive Recording — {project_name}" + (f" / {module_filter}" if module_filter else ""))
    print(f"  URL:      {url}")
    print(f"  Output:   {output_dir}")
    if resume:
        print("  Resuming from an existing in-progress checkpoint")
    print(f"{'='*60}")
    print("  A browser window will open. Explore the app as you normally")
    print("  would — every click and the elements around it are recorded.")
    print("  Click the 'Finish Recording' banner (bottom-right) when done,")
    print("  or simply close the browser window.")
    print(f"{'='*60}\n")

    project_dir = os.path.join(_ASSETS_BASE, safe)
    raw = scan_dom_interactive(
        url=url,
        browser=browser,
        project_dir=project_dir,
        resume=resume,
        storage_state_path=storage_state_path,
        auth_config=live_auth,
        setup_steps=setup_steps,
        module_id=module_filter,
    )

    paths = save_dom_scan_interactive(
        scan_data=raw,
        url=url,
        project_name=project_name,
        output_dir=output_dir,
        module_id=module_filter,
    )

    print(f"\nRecording complete: {raw['total_element_count']} elements across "
          f"{len(raw.get('pages', []))} page(s), {len(raw.get('_user_flows', []))} flow(s) recorded")
    print(f"  {paths['dom_elements']}")
    print(f"  {paths['dom_intents']}")
    print(f"\nRun the normal pipeline now to consume this recording:")
    if module_filter:
        print(f"  python main.py --project {project_name} --module {module_filter}\n")
    else:
        print(f"  python main.py --project {project_name}\n")

    return output_dir


def _safe_name(name: str) -> str:
    sanitised = "".join(
        c if (c.isalnum() or c in "-_") else "_" for c in name
    ).strip("_")
    return sanitised or "project"
