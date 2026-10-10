"""
migrate.py — validate / migrate project artifacts on disk.

    python -m contracts.artifacts.migrate --all                  # dry run, every project
    python -m contracts.artifacts.migrate --project sauceLabs    # dry run, one project
    python -m contracts.artifacts.migrate --project X --write    # upgrade v1 files to v2 (.v1.bak kept)
    python -m contracts.artifacts.migrate --project X --write --to 1   # downgrade (restores v1 bodies)

Roots scanned by --all: application_assets/projects and application_assets/myTestProjects
(override with --root, repeatable). Exit code 1 when any file fails its contract.
"""

import argparse
import json
import os
import shutil
import sys
from typing import Dict, List

from contracts.artifacts.io import atomic_write_json, read_json, validate_document
from contracts.artifacts.migrations import detect_version, to_v1, to_v2
from contracts.artifacts.paths import iter_project_artifacts, project_dirs
from contracts.artifacts.registry import spec_for

DEFAULT_ROOTS = [os.path.join("application_assets", "projects"),
                 os.path.join("application_assets", "myTestProjects")]


def scan_project(project_dir: str, write: bool = False, to_version: int = 2) -> List[Dict]:
    rows = []
    for name, path in iter_project_artifacts(project_dir):
        row = {"project": os.path.basename(project_dir), "artifact": name, "path": path}
        try:
            data = read_json(path)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            rows.append({**row, "ok": False, "status": "invalid_json", "errors": [str(exc)]})
            continue
        report = validate_document(name, data, path)
        status = "valid" if report.ok else "invalid"
        if report.ok and report.migrated:
            status = "migrates"
        row.update(ok=report.ok, status=status, version=report.version_found, errors=report.errors)
        if write and report.ok and spec_for(name).kind != "plain":
            current = detect_version(name, data)
            target = to_v2(name, data) if to_version == 2 else to_v1(name, data)
            if current != to_version:
                shutil.copyfile(path, f"{path}.v{current}.bak")
                atomic_write_json(path, target)
                row["written"] = f"v{current} -> v{to_version}"
        rows.append(row)
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--project", help="project folder name (under --root) or a path")
    g.add_argument("--all", action="store_true")
    ap.add_argument("--root", action="append", help="projects root (repeatable)")
    ap.add_argument("--write", action="store_true", help="rewrite files (default: dry run)")
    ap.add_argument("--to", type=int, choices=(1, 2), default=2)
    ap.add_argument("--json", action="store_true", help="print rows as JSON")
    args = ap.parse_args(argv)

    roots = args.root or DEFAULT_ROOTS
    if args.all:
        dirs = [d for r in roots for d in project_dirs(r)]
    elif os.path.isdir(args.project):
        dirs = [args.project]
    else:
        dirs = [os.path.join(r, args.project) for r in roots if os.path.isdir(os.path.join(r, args.project))]
        if not dirs:
            print(f"project '{args.project}' not found under {roots}", file=sys.stderr)
            return 2

    rows = [row for d in dirs for row in scan_project(d, write=args.write, to_version=args.to)]
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for r in rows:
            mark = "OK " if r["ok"] else "ERR"
            extra = f" [{r['written']}]" if r.get("written") else ""
            print(f"{mark} {r['status']:<9} {r['artifact']:<21} {r['path']}{extra}")
            for e in r.get("errors") or []:
                print(f"      - {e}")
    counts: Dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    bad = sum(1 for r in rows if not r["ok"])
    print(f"\n{len(rows)} artifact file(s) in {len(dirs)} project(s): "
          + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) + f"; failing={bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
