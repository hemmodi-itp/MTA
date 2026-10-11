"""
CLI: run deep discovery for a project without the rest of the pipeline (no LLM).

    python -m tools.discovery.deep --project <name> [--force] [--no-probes]

Writes test_comprehension/{app_map,form_model,api_inventory,permission_matrix,baseline}.json.
Requires `discovery.deep: true` in the project's project.yaml (use --enable to run anyway).
"""

import argparse
import json
import logging
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--force", action="store_true", help="crawl even if a fresh app_map.json can be reused")
    ap.add_argument("--no-probes", action="store_true", help="skip the form validation probes")
    ap.add_argument("--enable", action="store_true", help="run even if discovery.deep is false in project.yaml")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from tools.discovery.deep import service

    overrides = {}
    if args.enable:
        overrides["deep"] = True
    if args.no_probes:
        overrides["validation"] = {"enabled": False}
    result = service.ensure_app_discovery(args.project, force=args.force, log=print, discovery_overrides=overrides)
    print(json.dumps({k: v for k, v in result.items() if k != "paths"}, indent=2, default=str))
    return 0 if result.get("status") in ("success", "reused") else 1


if __name__ == "__main__":
    sys.exit(main())
