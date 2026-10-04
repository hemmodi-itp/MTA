# RepositoryReviewAgent

Produces **findings about how the application is built**: security, architecture, agent design, workflow,
performance and production readiness. The findings feed the Quality Scorecard and the gates. They never feed the compliance number.

## Inputs
`repo_graph`, `code_chunks`, `repo_tree`, `repo_dir`, `repo_model`, and optionally `agent_profile`. The agent reads `agent_profile.observed_risks` and passes them to the LLM review as unverified hints.

## Outputs
- `findings`: `[{dimension, rule_id, severity, title, file, start_line, end_line, rationale, fix, source: scanner|llm, confidence, verified}]`, sorted by severity with verified findings first.
- `scorecard`: `{dimension: 0-100}`, which is 100 minus the severity penalties (critical 40, high 20, medium 8, low 2). Findings with `verified: false` are **not** penalised.

## Behaviour
1. **Deterministic rules** (`engines/review/rules.py`) run over every indexed language.
   - **Secrets:** hard-coded secrets, committed env files, CORS wildcards and debug mode.
   - **Authentication:**
     - `web/no-auth` (high): no authentication construct exists anywhere. That means no middleware, guard, decorator, dependency (`Depends(get_current_user)`, `@login_required`, `@UseGuards`, `[Authorize]`, `passport.authenticate` …) and no auth library. The words "session" or "login" no longer count.
     - `web/unauthenticated-routes` (medium, confidence 0.6): the app authenticates some routes, but other state-changing routes show nothing.
   - **Reliability:** LLM calls without retries or timeouts.
   - **Readiness:** missing tests (Python, JS/TS, Go, JVM and other test nodes, or test files in the tree), a missing health check or README, and unpinned dependencies.
2. **LLM design review** (one call), at most 20 findings, most severe first.
   - The prompt does not assume an AI app.
   - The summary, scanner titles, observed risks and code are all fenced with `fence_untrusted`.
   - Each finding's file and line are validated. A finding that cannot be located is kept with `verified: false`, its severity is capped at `medium`, and its confidence is 0.4.

## Failure mode
If the LLM review fails, the step returns `status: partial` with the scanner findings only. No repository index means no findings.
