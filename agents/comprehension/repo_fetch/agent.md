# RepoFetchAgent

First step of the agent-evaluation pipeline (`workflows/agent_evaluation.yaml`). It checks that the GitHub repository is
readable, **pins it to one commit** and fetches the files the evaluation needs. It makes no LLM calls.

## Inputs
| Key | Type | Required | Notes |
|---|---|---|---|
| `github_url` | string | yes | `https://github.com/<owner>/<repo>`. A `/tree/<branch>` suffix is honoured |
| `branch` | string | no | Defaults to the repo's default branch |
| `brd_path` | string | no | Always fetched |
| `workspace_dir` | string | yes | The repo lands in `<workspace_dir>/repo/` |
| `emit` | callable | no | Progress callback |

## Outputs
- `repo_dir`, `repo_full_name`, `branch` and `commit_sha` (always resolved).
- `repo_tree`: every path in the commit, from the tree or from the zip.
- `repo_metadata`: description, language, size_kb, html_url and private.
- **`repo_coverage`:** `{source: tree|zip, files_in_tree, selected, fetched, skipped: {reason: n}, failed_paths, truncated, truncation_reason, commit_sha, authenticated, private}`.
  - Skip reasons are `vendored_or_hidden`, `lockfile_or_minified`, `unsupported_type`, `too_large`, `empty`, `budget` and `fetch_failed`.
  - Traceability's absence protocol and the report's limitations read it.

## Behaviour
1. **Metadata.** It calls `GET /repos/<owner>/<repo>`.
   - With `GITHUB_TOKEN` set, every GitHub request is authenticated, so private repositories the token can read are allowed.
   - The token header is never forwarded across a redirect.
   - Without a token, a private repo gets the message "not found or private; set GITHUB_TOKEN …".
2. **Commit first.** The default branch and the commit SHA are resolved before any file is fetched.
   - The REST API is used first.
   - If it stays rate-limited, the git smart-HTTP ref advertisement is used. The branch is never guessed as `main`.
   - A missing requested branch falls back to the default branch.
3. **Tree by SHA** (`/git/trees/<sha>?recursive=1`).
   - `select_files_for_download` picks the BRD, BRD-like docs and code in priority order, up to 1200 files and 10 MB. Extensions cover Python, JS/TS, Vue/Svelte, CSS/SCSS, JVM, Go, Rust, Ruby, PHP, C#, Swift, Dart, C/C++, Prisma, Terraform, Gradle, properties and more.
   - Files are fetched by SHA from raw.githubusercontent.com, in parallel.
4. **Zip fallback.** The commit zip is used when the tree API is rate-limited or the listing is **truncated**.
   - Only the same selection is extracted.
   - The archive is capped at 150 MB compressed, 500 MB decompressed (counting what is actually written) and 200,000 members, and is zip-slip guarded.
   - Repos over 150 MB are not zipped. A truncated listing is then used as-is and reported as a coverage limitation.
5. **Retries.**
   - Rate limits (403/429 with `x-ratelimit-remaining: 0` or `Retry-After`) wait for the reset, up to 60 s per wait and 150 s in total. After that the agent fails with a clear "GitHub API rate limit" error.
   - 5xx responses, timeouts and connection errors use exponential backoff with jitter.

The skip-dirs, size limit, extensions and file cap are shared with the indexer (`engines/repo_intel/files.py`).

## Failure mode
Returns `status: failed, blocking: true` with a user-readable `error` in these cases:
- a missing or unreadable repo;
- a rejected token;
- a missing branch;
- a lasting rate limit;
- a BRD link to another repo;
- a repo too large for the zip fallback;
- no file could be downloaded.
