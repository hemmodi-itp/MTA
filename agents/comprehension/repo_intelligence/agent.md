# RepoIntelligenceAgent

Agent-evaluation step that turns the fetched repository into a **knowledge graph and code chunks** for the
Traceability engine and the review. It is deterministic and makes no LLM calls. The logic lives in `engines/repo_intel/`.

## Inputs
| Key | Type | Required | Notes |
|---|---|---|---|
| `repo_dir` | string | yes | Fetched checkout (RepoFetchAgent) |
| `repo_tree` | array | no | The commit's full file list. Unfetched files still appear as graph nodes and in coverage |
| `repo_full_name`, `commit_sha` | string | yes | Snapshot cache key |

## Outputs
- `snapshot_id`: the `RepoSnapshot` row actually used. It is null when nothing was cached (no commit SHA, or no database).
- `repo_graph`, `code_chunks`: in-memory, for later steps in this run.
- `repo_model`: contains:
  - node counts, routes, pages, models, env vars, dependencies, the build plan and risk signals;
  - **`coverage`**: `files_listed`, `files_on_disk`, `files_indexed`, `by_language`, `skipped` {reason: n},
    `unfetched_source[_count]`, `unindexed_source[_count]`, `file_cap` and `complete`.

  The traceability absence protocol reads `coverage`.

## Behaviour
1. **Cache:** if the (repo, commit, `INDEXER_VERSION` = `ri-2.0`) snapshot exists, the agent loads it. Without a SHA it neither looks up nor saves.
2. **Python** (stdlib `ast`): symbols, routes and LLM/agent constructs. Routes cover:
   - FastAPI and Flask decorators with router prefixes;
   - `add_url_rule` and `add_api_route`;
   - Django `urls.py` `path`, `re_path` and `url`.

   Streamlit and Gradio scripts become page and form entry points, so code they call is provably wired.
3. **JS, TS, HTML, Vue and Svelte:**
   - routes on server receivers only (`app`, `server`, `fastify`, `hono`, `*Router`), NestJS controllers and Next.js;
   - React-Router and Vue-Router pages and SPA entry pages;
   - components, fetch/axios calls, forms, LLM calls and prompts;
   - Jest, Vitest, Playwright and Cypress tests, linked to the modules they import.
4. **Every other source language** (`generic_parser.py`: Java, Kotlin, Go, Rust, Ruby, PHP, C#, Swift, Dart, C/C++ and more):
   - chunks aligned to declarations;
   - symbols with spans and call names;
   - routes for Spring, ASP.NET, net/http and gin, actix and axum, Rails and Sinatra, Laravel, Ktor, Vapor and shelf;
   - test nodes;
   - Prisma and SQL tables.

   Stylesheets, SQL and other text are chunked, so BM25 and the secret scan see them.
5. **Docs and manifests:** README sections, dependencies, and the keys of `.env.example`, `.sample` and `.template` files.
6. **Linking:**
   - call names become `calls` edges;
   - handler names become `exposes` and `submits_to` edges;
   - frontend URLs become `calls_api` edges;
   - tests become `tests` edges;
   - pages become `renders` edges to components.
7. **Persist** in one transaction (`RepoSnapshot`, `KgNode`, `KgEdge`, `CodeChunk`). If another run saved the same commit first, its id is returned.

`engines/repo_intel/files.py` is the single definition of skip-dirs, the size limit, extensions and the file cap
(1200). It is shared with the fetcher.

## Failure mode
- **One bad file:** a parse error in a single file falls back to window chunks.
- **Database unavailable:** a cache or database error degrades to an in-memory index and returns `status: partial` with `error`.
