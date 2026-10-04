"""
dom_intents.py — shared reader for module-scoped comprehension/dom_intents.json.

Discovery writes one dom_intents.json per module (or a flat one when the
project declares no modules) — see comprehension_scan_dir. Any agent that
needs the raw, module-scoped intent list (locator_id/action/expected_result)
should read it through this single helper rather than re-implementing the
path lookup and JSON-shape handling per call site.
"""

import json
import os
from typing import List, Optional

from tools.constants import PROJECTS_BASE as _ASSETS_BASE
from tools.discovery.paths import comprehension_scan_dir


def load_dom_intents(safe_project: str, module_id: Optional[str] = None) -> List[dict]:
    """
    Read test_comprehension/dom_intents.json (module-scoped when module_id is
    given) for the given project. Returns [] if discovery hasn't produced
    one for this module (e.g. BRD-only mode, or module not yet scanned).
    """
    comp_dir = comprehension_scan_dir(
        os.path.join(_ASSETS_BASE, safe_project, "test_comprehension"), module_id
    )
    path = os.path.join(comp_dir, "dom_intents.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("intents", [])
    except Exception:
        return []
