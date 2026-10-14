"""prompt.py — the one LLM prompt of TriageAgent: a verdict for a failure the deterministic rules left `unknown`.
Filled with str.format(test=..., error=...); the answer must quote the error (tools/triage/service.py checks it)."""

TRIAGE_PROMPT = """You classify ONE failed UI test. Answer with JSON only:
{{"verdict": "product_defect" | "test_defect.locator" | "test_defect.data" | "environment",
  "quotes": ["exact text copied from the error below that supports the verdict"],
  "reason": "one sentence"}}
product_defect = the application behaved wrongly; test_defect.locator = the test could not find / pick the element;
test_defect.data = test data collided or a precondition was missing; environment = infrastructure, network or auth
state. Every quote must be copied verbatim from the error. If you cannot tell, use the verdict that the quoted text
supports best.

Test: {test}
Error:
{error}
"""
