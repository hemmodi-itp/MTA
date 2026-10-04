"""
skills.py — repair-tool registry for HealingAgent.

HealingAgent is still invoked directly by the orchestrator via
execute(request, state), not through a skill-selection interface — but this
is the first agent whose skills.py reflects real ADK tools (see tools.py's
build_tools) rather than deterministic Skill objects, per the org's ADK
reference-pattern intent.
"""

SKILLS: dict = {
    "propose_locator_fix": "Live-re-resolve a failing locator against the current DOM; propose a replacement. Now treats a locator matching 2+ elements as unresolved (strict-mode-aware), not just 0.",
    "propose_timing_fix": "Check whether a failing locator resolves given a longer wait.",
    "propose_compilation_fix": "Fix deprecated/incorrect Playwright API shapes preventing a test from running.",
    "propose_test_data_fix": "Identify stale/conflicting literal test-data values in a failing block.",
    "propose_navigation_fix": "Check a hardcoded page.goto(...) URL against project.yaml's configured url.",
    "propose_fixture_fix": "Detect a missing upload-fixture file (ENOENT / 'Upload fixture not found') — always not-healable, never a locator issue.",
    "apply_patch": "Structurally validate and atomically write a healed test() block — the only writer.",
    "run_tests": "Re-run specific spec files via UIExecutionAgent to verify a patch.",
    "mark_not_healable": "Declare a failure a real defect, never re-attempted this run.",
}
