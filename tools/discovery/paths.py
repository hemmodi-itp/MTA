"""
paths.py — single source of truth for module-scoped discovery output paths.

DOM/interactive scan artifacts (dom_elements.json, dom_intents.json,
.scan_checkpoint.json, interactive/) are scoped per module so that scanning
module M04 does not overwrite module M01's data. Everything else under
comprehension/ (business_scenarios.json/.md, run summaries shared across
modules) stays at the comprehension root — only pass a module_id here for
the DOM/interactive scan artifacts themselves.
"""

import os
from typing import Optional


def comprehension_scan_dir(comprehension_root: str, module_id: Optional[str]) -> str:
    """
    Return the directory DOM/interactive scan artifacts should live in.

    comprehension_root/modules/{module_id} when module_id is given, else
    comprehension_root unchanged — preserves the flat layout for projects
    that don't declare modules (or aren't run with --module).
    """
    if module_id:
        return os.path.join(comprehension_root, "modules", module_id)
    return comprehension_root
