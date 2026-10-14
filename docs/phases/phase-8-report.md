# Phase 8 report — API Testing and White-Box Testing

New package `tools/whitebox/`. Flags: `white_box: {enabled, source_dir, exclude}` and `test_types.api` in
project.yaml (absent = off); `api_tests.ownership` lists resources that belong to a role.

**8.2 White-box rule extraction** (`python_rules.py` — stdlib `ast`; `js_rules.py` — patterns; `extract.py` — driver):
routes (FastAPI / Flask / APIRouter / Blueprint / add_api_route, Express / Koa) with templated paths, parameters
(path / query / form / file / JSON body), auth style (session redirect vs 401), role checks, access-check helpers,
literal statuses, the validation-error status, JSON response keys, stateful fields and stored-state preconditions;
input rules from `if` guards (required / length / range / options / pattern — the variable is traced to its request
field through `data.get`, `Form(...)` parameters and helper calls, constants resolved across files, feature-flag
conditions kept as `guards` with the flag-off behaviour), pydantic, marshmallow, zod, yup, joi and class-validator.
Every rule cites `file:line`; output `test_comprehension/code_rules.json`. TestDesignAgent runs it first and merges
the rules into the Phase 3 constraints as source `code` (BRD > observed > code > default); cases built from a code
bound carry `citations`. EP gained a "wrong format" invalid class for any pattern constraint.

**8.4 Contract checks** (in `extract.py`): a form or UI call with no backend route, a field the backend never reads,
and a browser-enforced rule the server does not enforce ("server accepts what the client rejects"). buggy_shop: the
login form marks username/password required; the server only rejects them through authentication.

**8.1 API tests** (`api_tests.py`, runtime helpers `fixtures/apiChecks.ts`): per endpoint of code_rules ∪
api_inventory — signed out (401 / login redirect), wrong role (403), ownership (denied), undefined method (405), valid
request + response keys, one case per code rule sent straight to the server (rejected outside, accepted at the
boundary), pagination edges and unusual query values (never 5xx), PUT/DELETE idempotency, and a warning when JSON error
bodies differ. Data changes only with `safety.allow_destructive` in a non-prod environment; limits that depend on stored
state and routes with a stored-state precondition are skipped with the reason. Wired into ScriptGeneration (registered
like the NFR specs; traceability links API ACs such as "all API endpoints need a session").

**8.3 Coverage**: `coverage_server.py` runs the ASGI app under coverage.py (branch) and saves on a graceful stop;
`AppServer(coverage_data=...)` uses it (CTRL_BREAK on Windows). `coverage_gap.py`: statement / branch %, uncovered
critical functions, uncovered lines → function → routes reaching it (call graph) → API tests for exactly those routes
(`gap_*.spec.ts`). Frontend: `MTA_JS_COVERAGE=<dir>` records Chromium V8 coverage per test (`jsCoverage` fixture);
`js_coverage.py` reports function coverage (no source maps / v8-to-istanbul). coverage.py 7.10.7 added to
requirements-dev.

**8.5 Mutation testing** (`mutation.py`, built-in runner): comparison / condition / boolean / constant mutants of
selected functions, the original always restored (also after an interrupted run); scheduled CLI, reused by Phase 12.

**Benchmark** (`python -m tools.benchmark.whitebox_bench --mutants 12`, buggy_shop, real Chromium;
`benchmarks/results/2026-10-14_buggy_shop_phase8_whitebox.{json,md}`): 26 routes and 10 input rules extracted, each
citing `app.py:<line>`.

| KPI | Result | Target |
|---|---|---|
| API endpoint coverage | **96.2%** (25/26; `POST /login` is exercised by the UI login, not the API suite) | ≥ 90% |
| Clean run of the API suite | 116 tests: 108 passed, **0 failed**, 8 skipped with a reason (destructive / stored-state) | no false failures |
| One coverage-gap round | branches **29.1% → 63.8%**, statements 61.8% → 82.9% (40 functions → tests for 25 routes) | measurable rise |
| "Server accepts what the client rejects" (BUG_02) | **caught** by `price below min (-0.01) -> rejected [app.py:99]` | all |
| Other seeded bugs caught by the API suite | **7/8**: BUG_01, 18, 21 (rule cases), 16 (role), 04 (ownership), 07 (unusual query values) | — |
| Mutation score, `validate_product` + `parse_quantity` | **10/12 killed (83.3%)**, `app.py` restored byte-identical | — |

Not caught: BUG_17 (upload allow-list is a local variable inside the handler, so no rule is extracted) and BUG_13
(the wording of a UI message — not an API behaviour). Surviving mutants: `app.py:85` `>=`→`>` sits in the
`BUG_01`-only branch, unreachable with the flag off (equivalent mutant); `app.py:161` `qty > QTY_MAX`→`>=` needs a
"quantity 99 accepted" case, which is skipped because the cart limit depends on stored state. Frontend V8 coverage:
buggy_shop's JavaScript is inline in the HTML, so 0 JS functions are attributed to files (needs source maps).

**Tests**: `tests/unit/test_phase8_whitebox.py` 16 (path templating, if guards with flags/constants/helpers, pydantic,
marshmallow, zod, yup, joi, class-validator, Express routes, buggy_shop extraction + contract, generator incl. safety
skips); `tests/unit/test_phase8_coverage_mutation.py` 6 (real coverage.py data → report → gaps → routes, JS coverage
summary, every mutation operator, runner score + restore, crash/leftover restore, code rules → design citations).
