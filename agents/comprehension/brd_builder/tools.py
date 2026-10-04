"""tools.py — tool surface for BrdBuilderAgent (re-exported from tools/agent_eval/)."""

from tools.agent_eval.brd_source import BrdIndex, normalize_brd_path, read_brd, read_brd_preview  # noqa: F401
from tools.agent_eval.live_client import connect_live_agent  # noqa: F401
from tools.agent_eval.live_discovery import (  # noqa: F401
    collect_live_evidence,
    evidence_from_runtime_profile,
    render_evidence,
)
from tools.agent_eval.llm_json import generate_json  # noqa: F401
from tools.agent_eval.schemas import BRD_DOCUMENT, BRD_SELECTION, REQUIREMENTS  # noqa: F401
