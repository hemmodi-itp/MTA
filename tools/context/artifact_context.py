"""
ProjectArtifactContext — loads existing artifacts and .md files for a project,
producing a compact, LLM-safe context object that creating agents use before
calling the LLM.

Design rules:
  - No LLM calls, no writes — pure read + compact.
  - All text fields are capped so injected context stays well under 4 000 chars total.
  - Missing files return safe empty defaults; no exceptions bubble to callers.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Dict, Set

import yaml

from tools.constants import PROJECTS_BASE as _ASSETS_BASE

# Hard caps for content injected into LLM prompts
_MAX_FORMAT_GUIDE_CHARS = 1_500   # per .md file used as format guide
_MAX_EXISTING_ITEMS_CHARS = 800   # compact dedup summary (intents list or TC list)


@dataclass
class ProjectArtifactContext:
    """
    Loaded once per agent execute() call.  Agents use it to:
      - Skip LLM calls when no uncovered scenarios exist.
      - Inject compact existing-items hints into prompts (dedup).
      - Inject capped .md content as format/style guides.
      - Merge newly generated items with existing ones before writing.
    """
    project_state: dict

    # Filter sets — used to skip covered scenarios
    covered_scenario_ids: Set[str]      # BS-IDs that already have at least one intent
    scenarios_with_test_data: Set[str]  # BS-IDs that already have test data
    scenarios_with_specs: Set[str]      # BS-IDs that already have a .spec.ts in test_suite.json

    # Compact dedup hints for LLM prompts (capped strings)
    existing_intents_compact: str       # one line per intent: "INT-001: fill_email (fill) — BS-001"
    existing_tc_compact: str            # one line per TC: "TC-001: Submit form (BS-001, positive)"
    existing_specs_compact: str         # one line per spec: "BS-007: test_BS-007_search.spec.ts (new)"

    # Format guides for LLM prompts (first N chars of .md files)
    format_guide_scenarios: str         # from comprehension/business_scenarios.md
    format_guide_testdata: str          # from test_data/test_data.md

    # Full raw data for merge steps (not injected into prompts)
    existing_test_data_raw: Dict        # {scenario_id: raw JSON dict} from test_data.json
    existing_intents_raw: list          # list of intent dicts from intents.yaml

    @classmethod
    def load(cls, project_name: str, project_state: dict) -> "ProjectArtifactContext":
        """
        Load context for a project.  Always succeeds — missing files produce empty defaults.

        Args:
            project_name:   project folder name (will be sanitised to safe form)
            project_state:  full project_state dict from request["project_state"]
        """
        safe = _safe_name(project_name)
        base = os.path.join(_ASSETS_BASE, safe)

        format_guide_scenarios = _read_md_capped(
            os.path.join(base, "test_comprehension", "business_scenarios.md")
        )
        format_guide_testdata = _read_md_capped(
            os.path.join(base, "test_creation", "test_data", "test_data.md")
        )

        existing_intents_raw, covered_scenario_ids, existing_intents_compact = _load_intents(
            os.path.join(base, "test_creation", "intents.yaml")
        )

        existing_test_data_raw, scenarios_with_test_data = _load_test_data(
            os.path.join(base, "test_creation", "test_data", "test_data.json")
        )

        scenarios_with_specs, existing_specs_compact = _load_specs_from_suite(
            os.path.join(base, "test_creation", "test_suite.json")
        )

        existing_tc_compact = _compact_test_cases(project_state.get("test_cases", {}))

        return cls(
            project_state=project_state,
            covered_scenario_ids=covered_scenario_ids,
            scenarios_with_test_data=scenarios_with_test_data,
            scenarios_with_specs=scenarios_with_specs,
            existing_intents_compact=existing_intents_compact,
            existing_tc_compact=existing_tc_compact,
            existing_specs_compact=existing_specs_compact,
            format_guide_scenarios=format_guide_scenarios,
            format_guide_testdata=format_guide_testdata,
            existing_test_data_raw=existing_test_data_raw,
            existing_intents_raw=existing_intents_raw,
        )

    def has_existing_intents(self) -> bool:
        return bool(self.existing_intents_raw)

    def has_existing_test_data(self) -> bool:
        return bool(self.existing_test_data_raw)

    def has_existing_specs(self) -> bool:
        return bool(self.scenarios_with_specs)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_name(name: str) -> str:
    sanitised = "".join(c if (c.isalnum() or c in "-_") else "_" for c in name).strip("_")
    return sanitised or "project"


def _read_md_capped(path: str) -> str:
    """Read a .md file and return its first _MAX_FORMAT_GUIDE_CHARS chars."""
    if not os.path.exists(path):
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
        if len(content) > _MAX_FORMAT_GUIDE_CHARS:
            return content[:_MAX_FORMAT_GUIDE_CHARS] + "\n[... truncated for brevity ...]"
        return content
    except Exception:
        return ""


def _load_intents(path: str):
    """
    Load intents.yaml.
    Returns: (raw_intent_list, covered_scenario_id_set, compact_str)
    """
    if not os.path.exists(path):
        return [], set(), ""
    try:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        intents = raw.get("intents", [])
        covered: Set[str] = set()
        lines = []
        for intent in intents:
            sources = intent.get("source_scenarios", [])
            covered.update(sources)
            lines.append(
                f"{intent.get('intent_id', '?')}: {intent.get('intent_name', '?')} "
                f"({intent.get('action', '?')}) — {', '.join(sources)}"
            )
        compact = _cap("\n".join(lines), _MAX_EXISTING_ITEMS_CHARS)
        return intents, covered, compact
    except Exception:
        return [], set(), ""


def _load_test_data(path: str):
    """
    Load test_data.json.
    Returns: (dict keyed by scenario_id, set of covered scenario IDs)
    """
    if not os.path.exists(path):
        return {}, set()
    try:
        with open(path, encoding="utf-8") as f:
            records = json.load(f)
        by_scenario: Dict = {}
        covered: Set[str] = set()
        for r in records:
            sid = r.get("scenario_id", "")
            if sid:
                by_scenario[sid] = r
                covered.add(sid)
        return by_scenario, covered
    except Exception:
        return {}, set()


def _compact_test_cases(test_cases: dict) -> str:
    """Format existing test cases as a compact dedup-hint string."""
    if not test_cases:
        return ""
    lines = [
        f"{tc_id}: {tc.get('name', '?')} ({tc.get('scenario', '?')}, {tc.get('suite', '?')})"
        for tc_id, tc in test_cases.items()
    ]
    return _cap("\n".join(lines), _MAX_EXISTING_ITEMS_CHARS)


def _cap(text: str, limit: int) -> str:
    if len(text) > limit:
        return text[:limit] + "\n[... truncated ...]"
    return text


def _load_specs_from_suite(suite_path: str):
    """
    Load test_suite.json and return (scenarios_with_specs, compact_str).

    scenarios_with_specs — set of spec_id values (BS-NNN) already generated
    compact_str          — one line per spec for LLM dedup hints
    """
    if not os.path.exists(suite_path):
        return set(), ""
    try:
        with open(suite_path, encoding="utf-8") as f:
            suite = json.load(f) or {}
        ids: Set[str] = set()
        lines = []
        for spec in suite.get("specs", []):
            sid = spec.get("spec_id", "")
            if sid:
                ids.add(sid)
                lines.append(
                    f"{sid}: {spec.get('file', '?')} "
                    f"({spec.get('status', 'unknown')})"
                )
        return ids, _cap("\n".join(lines), _MAX_EXISTING_ITEMS_CHARS)
    except Exception:
        return set(), ""
