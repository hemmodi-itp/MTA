# MCP Integration Plan — GitHub, Playwright, Atlassian

> Status: **Planned, not yet implemented.** Written 2026-07-07. Run through this doc when ready to actually wire these up.

## Context

The user wants three MCP servers wired into Claude Code for this project (`agentic-qa-platform`):

1. **GitHub** — to push code, open/review PRs, and check merge status directly from a Claude Code session, instead of going through the `gh` CLI manually for everything.
2. **Playwright MCP** — the user believed this was already set up. Investigation found it is **not** — they're conflating it with the `@playwright/test` npm library already used to *run* generated `.spec.ts` files (`agents/test_execution/ui_execution_agent.py` shells out to `npx playwright test`). Playwright MCP is a separate thing: it gives an LLM live, ad-hoc browser-control tools (navigate, click, snapshot, screenshot) — genuinely useful for interactively poking at a failing spec or exploring an app mid-session, which nothing in the current toolset does.
3. **Atlassian (Jira + Confluence)** — to pull requirements/input and read defects directly, instead of the current manual/local-file BRD workflow (`project.yaml`'s `input.brd_dir`).

Investigation findings that shape this plan:
- No `.mcp.json` exists yet anywhere (project or user-level) — starting from zero.
- Git remote is **GitHub Enterprise Server**, not github.com: `https://intuitive-technology-partners-inc.ghe.com/ITP-INC/agentic-qa-platform.git`. This rules out github.com-only hosted options and requires the self-hosted GitHub MCP server pointed at the GHES host.
- **No `.github/workflows/` exists at all** — so today, "merge checks" has nothing to actually check. The user confirmed they want a basic CI workflow added so GitHub MCP's check-status tools have something real to read.
- Jira/Confluence is confirmed **Atlassian Cloud**.
- User wants credentials **project-scoped** (shared via committed `.mcp.json`) using env-var placeholders — never literal secrets in git.

---

## 1. GitHub MCP (GitHub Enterprise Server)

**Server**: [`github/github-mcp-server`](https://github.com/github/github-mcp-server) (GitHub's official MCP server). Supports GHES via the `GITHUB_HOST` env var (confirmed in [GitHub's enterprise-configuration docs](https://docs.github.com/en/copilot/how-tos/provide-context/use-mcp-in-your-ide/enterprise-configuration)) — the github.com-hosted Copilot MCP endpoint is not confirmed to support GHES, so we use the self-hosted binary/Docker path instead.

**What you need**: a GitHub Enterprise Personal Access Token (classic or fine-grained) scoped to `ITP-INC/agentic-qa-platform` with repo + PR permissions, generated from `https://intuitive-technology-partners-inc.ghe.com/settings/tokens`.

**Setup** (run interactively — this needs your token, which should never be typed into a chat session):
```bash
claude mcp add --scope project \
  --env GITHUB_PERSONAL_ACCESS_TOKEN=${GITHUB_PAT} \
  --env GITHUB_HOST=https://intuitive-technology-partners-inc.ghe.com \
  --transport stdio github \
  -- github-mcp-server stdio
```
(If the `github-mcp-server` binary isn't installed, download the Windows release from the repo's Releases page, or run it via Docker instead: `docker run -i --rm -e GITHUB_PERSONAL_ACCESS_TOKEN -e GITHUB_HOST ghcr.io/github/github-mcp-server`.)

This writes an entry to project `.mcp.json` referencing `${GITHUB_PAT}` — each teammate sets their own `GITHUB_PAT` env var locally (e.g. in their shell profile), so the committed file never contains a real token.

**Gives you**: create/push branches, open PRs, post review comments, read check-run/status results, merge PRs — matching "push my code, post review and merge checks."

---

## 2. Playwright MCP

**Server**: [`microsoft/playwright-mcp`](https://github.com/microsoft/playwright-mcp), npm package `@playwright/mcp`. No credentials needed.

**Prerequisite already satisfied**: needs a Chromium browser installed via `npx playwright install chromium` — already done when the corrupted `node_modules/playwright` install was fixed earlier in this project's history.

**Setup**:
```bash
claude mcp add --scope project --transport stdio playwright -- npx @playwright/mcp@latest
```

**What this adds beyond what you have today**: your existing setup *runs* pre-generated `.spec.ts` files. Playwright MCP instead gives an agent live tools — navigate, click, type, snapshot the accessibility tree, screenshot — useful for interactively debugging why a generated spec fails, or exploring a new page live during a Claude Code session, without writing a `.spec.ts` file first. It doesn't replace `agents/test_execution/ui_execution_agent.py`'s execution pipeline; it's a complementary, ad-hoc tool.

---

## 3. Atlassian (Jira + Confluence) — Cloud

**Recommended**: [`atlassian/atlassian-mcp-server`](https://github.com/atlassian/atlassian-mcp-server) — Atlassian's own official **remote** MCP server, OAuth 2.1. Since the instance is Cloud, this is the simplest option: **no static token to manage or distribute at all** — the `.mcp.json` entry is just a URL, and each teammate authorizes their own Atlassian account via OAuth on first use (through `/mcp` in an interactive session). This fits the "project-scoped, no secrets in git" preference even better than an env-var token, since there's no secret in the config file whatsoever.

**Setup**:
```bash
claude mcp add --scope project --transport sse atlassian https://mcp.atlassian.com/v1/sse
```
Then in an interactive session, run `/mcp` and authorize against your Atlassian account. This grants access based on your existing Jira/Confluence permissions — no admin API token needed.

**Alternative** (if the official server's OAuth flow doesn't fit the team's setup, or finer-grained service-account-style auth is needed): [`sooperset/mcp-atlassian`](https://github.com/sooperset/mcp-atlassian), self-hosted via `uvx`, using `JIRA_URL` / `JIRA_USERNAME` / `JIRA_API_TOKEN` (+ Confluence equivalents) as env-var placeholders in `.mcp.json`, same pattern as GitHub above. Only worth the extra moving part if OAuth doesn't work.

**Gives you**: search/read Jira issues (defects) and Confluence pages as input to discovery/comprehension, and create/comment/transition issues — e.g. filing a bug straight from a failed test run, or pulling a requirement doc directly instead of a local BRD markdown file.

---

## 4. New: CI workflow so "merge checks" has something to check

Add `.github/workflows/ci.yml`, triggered on PR to `main`/`demoTest`, running the Python unit suite:
```yaml
- Checkout
- Set up Python 3.14
- pip install -r requirements.txt
- python -m unittest discover -s tests -p "test_*.py"
```

**Important caveat to address before enabling this as a required check**: the suite currently has a known, pre-existing baseline of **5 failures + 7 errors** (stale test/workflow-name mismatches — e.g. `tests/unit/test_orchestrator.py` and `tests/unit/test_workflow_loader.py` expect an old step-name shape that no longer matches `full_workflow.yaml`). Turning on this workflow as a *required* branch-protection check immediately would make every PR red from day one. Recommend either:
- Fixing/quarantining those known-broken tests first (separate follow-up task), or
- Adding the workflow as **non-required/informational** initially, flipping it to required once the baseline is clean.

This plan does **not** run the generated Playwright `.spec.ts` files in CI — those test third-party target applications (e.g. saucedemo.com) via LLM-generated, project-specific specs, not this repo's own code, so they aren't a meaningful "did my code change break something" gate.

---

## Verification (once implemented)

1. After each `claude mcp add`, run `/mcp` in an interactive Claude Code session to confirm the server connects (green/authorized) before relying on it.
2. GitHub: ask Claude to list open PRs on `ITP-INC/agentic-qa-platform` — confirms GHES auth works.
3. Playwright MCP: ask Claude to navigate to a URL and take a snapshot — confirms it launches a browser independently of the test-runner path.
4. Atlassian: ask Claude to search for a known Jira issue — confirms OAuth/token auth works.
5. CI: open a throwaway PR and confirm the new workflow run appears and reports a status (pass/fail) — then use the GitHub MCP to read that check's status back, closing the loop on "merge checks."

## Not covered by this plan (explicitly out of scope, flag if wanted later)
- Actually fixing the 5-failure/7-error baseline test suite (separate task).
- Branch protection rule configuration itself (requires GHES repo admin UI, not something Claude Code can do headlessly).
- Running generated Playwright specs in CI.
