"""prompt.py — LLM prompt template for AgentQualityTestingAgent's judge.

The judge prompt lives in the shared core (tools/agent_tests/judge.py) so the CLI and this agent use the same one;
it is re-exported here. Untrusted text — the test inputs (they carry injection payloads), the agent's replies and
check details quoting them — is fenced at substitution time (FencedTemplate).
"""

from tools.agent_tests.judge import JUDGE_PROMPT, JUDGE_SCHEMA  # noqa: F401
