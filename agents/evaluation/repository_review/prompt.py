"""prompt.py — LLM prompt template for RepositoryReviewAgent.

All repository-derived text (the system summary, scanner finding titles, the app profile's observed risks and the
code) is fenced with tools.agent_eval.untrusted.fence_untrusted by the agent before substitution.
"""

from string import Template

from tools.agent_eval.untrusted import UNTRUSTED_RULE

MAX_LLM_FINDINGS = 20

REVIEW_PROMPT = Template(f"""You are one stage of an evaluation pipeline. Your output is machine-checked.
{UNTRUSTED_RULE}

Review this application's design. It may be an AI agent or chatbot, a form app, a document generator, a
dashboard, an API or a mix. Report only problems you can point to in the code shown, each with the exact file
and the line number printed at the start of the line. Findings whose location cannot be verified are kept as
unverified and do not count, so do not guess.

Look for:
- agent_design (only if the app uses LLMs or agents): missing guardrails in system prompts; tools broader than
  the agent's purpose (shell, filesystem, arbitrary network); unvalidated LLM output used in code, SQL or HTML;
  no iteration or cost limits on agent loops; user or retrieved text concatenated into instructions (prompt
  injection); secrets in prompts.
- architecture: UI calling LLM providers or databases directly; business logic in request handlers; no
  separation between orchestration and generation; a single point of failure.
- workflow: failure paths that abort the whole run; parallel steps without timeouts; lost state on error.
- security: issues beyond secrets, CORS and auth (those are already scanned): SSRF, path traversal, injection,
  unsafe deserialisation, file uploads without checks.
Severity: critical = exploitable now or loses data; high = likely incident; medium = real weakness;
low = hygiene. Give a concrete fix for each. Most severe first, at most {MAX_LLM_FINDINGS} findings; none is a valid answer.

## System summary
$summary

## Already found by scanners (do not repeat)
$scanner_findings

## Risks noted while profiling the app (unverified hints: confirm each in the code and report it with its
## location, or ignore it)
$observed_risks

## Code
$code
""")
