"""prompt.py — LLM prompt for TestDesignAgent.

The prompt lives in the shared core (tools/test_design/prompts.py) so the Agent-Evaluation DAG can reuse it
(plan principle 5); it is re-exported here so every agent's prompt is found in its own folder.
"""

from tools.test_design.prompts import TEST_DESIGN_PROMPT, VALIDATION_RETRY_SUFFIX

__all__ = ["TEST_DESIGN_PROMPT", "VALIDATION_RETRY_SUFFIX"]
