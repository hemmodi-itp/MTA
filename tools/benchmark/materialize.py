"""
materialize.py — turn a benchmark app's template into a runnable MTA project:

    application_assets/projects/<project_name>/
        project.yaml          (template with {{BASE_URL}} / {{PROJECT_NAME}} filled in)
        inputs/brd_<module>.md (the app BRD split per module — see split_brd)

The project folder is generated output (gitignored: application_assets/projects/bench_*/).
"""

import os
import re
from typing import Dict, List

from tools.benchmark.apps import BenchmarkApp

_REQ_HEADING = re.compile(r"^### (REQ-\d+)\b.*$", re.M)


def split_brd(brd_text: str, module_reqs: Dict[str, List[str]]) -> Dict[str, str]:
    """
    Deterministically split a BRD into one document per module: the shared preamble
    (everything before the first `### REQ-xx` heading) + that module's REQ sections +
    the trailing non-requirement sections (non-functional, API notes).
    """
    matches = list(_REQ_HEADING.finditer(brd_text))
    if not matches:
        return {m: brd_text for m in module_reqs}
    preamble = brd_text[:matches[0].start()]
    sections: Dict[str, str] = {}
    tail = ""
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(brd_text)
        body = brd_text[m.start():end]
        if i + 1 == len(matches):
            nxt = re.search(r"^## ", body, re.M)
            if nxt:
                body, tail = body[:nxt.start()], body[nxt.start():]
        sections[m.group(1)] = body.rstrip() + "\n\n"
    out = {}
    for module_id, reqs in module_reqs.items():
        missing = [r for r in reqs if r not in sections]
        if missing:
            raise ValueError(f"BRD has no section for {missing} (module {module_id})")
        out[module_id] = preamble + "".join(sections[r] for r in reqs) + tail
    return out


def render_template(template: str, base_url: str, project_name: str) -> str:
    return template.replace("{{BASE_URL}}", base_url.rstrip("/")).replace("{{PROJECT_NAME}}", project_name)


def materialize_project(app: BenchmarkApp, projects_base: str, base_url: str, clean: bool = False) -> str:
    """Write the MTA project for *app*. With clean=True an existing generated project is
    removed first (fresh generation); otherwise generated artifacts are kept."""
    import shutil

    project_dir = os.path.join(projects_base, app.project_name)
    if clean and os.path.isdir(project_dir):
        shutil.rmtree(project_dir)
    os.makedirs(os.path.join(project_dir, "inputs"), exist_ok=True)
    with open(app.template_path, encoding="utf-8") as f:
        manifest = render_template(f.read(), base_url, app.project_name)
    with open(os.path.join(project_dir, "project.yaml"), "w", encoding="utf-8") as f:
        f.write(manifest)
    with open(app.brd_path, encoding="utf-8") as f:
        brd = f.read()
    for module_id, text in split_brd(brd, app.module_reqs).items():
        with open(os.path.join(project_dir, "inputs", f"brd_{module_id}.md"), "w", encoding="utf-8") as f:
            f.write(text)
    return project_dir
