# Phase 9 — AI Agent / LLM Application Testing: Report (session 1 of 2: 9.0, 9.1, 9.2)

> Design: `docs/phases/phase-9-design.md`. Approved decisions: D1 (runner + benchmark this session) yes, D4
> (14 weaknesses) yes, D3 (`eval_sets/<agent>/agent.yaml` opt-in) yes, **D7 (BRD → spec LLM drafter) deferred** to
> the integration session, where `brd_builder` supplies its input. 9.3 (judge + calibration), 9.4 (statistics),
> 9.5 (regression) and the `agent_evaluation.yaml` integration were not started. Not committed yet.

## 1. What changed

### New
- **`tools/agent_tests/`**: the Phase 9 package.
  - `models` (case record + closed vocabularies + JSON Schema export) and `spec` (`AgentSpec` = `agent.yaml`)
  - `config` (minimums, defaults), `canaries` (per-run tokens), `catalogs` + `catalog/*.yaml` (6 curated, versioned
    catalogs)
  - `generators/` (15: one per dimension + `base`)
  - `checks/` (canary, refusal, json_schema, text, consistency, trace, latency, aggregator)
  - `dataset` (load / validate / merge / write / review / manifest)
  - `transport` (conversation transport: HTTP via `net_guard`, in-process ASGI), `runner`, `bench`, `cli`
  - `README.md`, `schema/agent_test_case.v1.schema.json`
- **`eval_sets/buggy_bot/`**: `agent.yaml` (hand-written from the BRD), 15 `*.jsonl` (96 cases), `manifest.json`
  (dataset v1, seed 7).
- **`benchmarks/agents/buggy_bot/`**: `kb.yaml` (12 documents), `brd.md` (11 REQ / 35 AC), `llm_mode.py` (optional
  real-LLM mode).
- **`benchmarks/results/2026-10-12_buggy_bot_phase9.{json,md}`**
- **Tests**: 11 new files, `tests/unit/test_agent_tests_*.py` and `test_http_ssl_guarded_opener.py`.

### Changed
| File | Change |
|---|---|
| `benchmarks/agents/buggy_bot/app.py` | Restructured around a stateful `Bot`. 10 new weaknesses (05–14). The KB comes from `kb.yaml` with citations. Adds JSON mode, memory for name and order number, a tool trace, token usage, scope redirect, policy refusal, document summaries that never echo the document, `BOT_CANARY` / `BOT_SEED` / `BOT_MEMORY_TURNS` / `BOT_SLOW_MS` / `BOT_TRACES`, and `BOT_MODE=llm`. Every Phase 0 public name and reply is kept. |
| `benchmarks/agents/buggy_bot/weaknesses.yaml` | 14 entries, plus `detected_by`, `may_affect` and `ac_ids` |
| `benchmarks/agents/buggy_bot/README.md` | Rewritten for 14 weaknesses and two modes |
| `tests/unit/test_bench_buggy_bot.py` | Phase 0 assertions kept. The count assertion changed from 4 to 14 (the ground truth grew). 30 new tests. |
| `tools/agent_eval/http_ssl.py` | **Pre-existing deadlock fixed** (§6.1). One line moved. |
| `requirements.txt` | `+ jsonschema>=4.0`. It was already installed transitively; now it is declared. |

No new agent was needed (no DAG step this session), so `tools/scaffold_agent.py` was not used.

## 2. Tests

Interpreter: `../MTA/.venv/Scripts/python.exe` (the worktree has no venv of its own).

| Suite | Command | Result |
|---|---|---|
| Phase 9 files | `python -m pytest tests/unit/test_agent_tests_*.py tests/unit/test_bench_buggy_bot.py tests/unit/test_http_ssl_guarded_opener.py -q` | **244 passed**, 0 failed (55 s) |
| Full unit suite | `python -m pytest tests/unit -q --ignore=tests/unit/test_agent_tests_bench.py` | **1,838 passed**, 0 failed, 10 warnings (10 min 11 s). The bench file (21 tests) is in the Phase 9 row; the Phase 9 files were re-run after the last edits |

What the required tests cover:

| Required test | Where | What it proves |
|---|---|---|
| Canary detector | `test_agent_tests_canary.py` | 16 leaked + 14 clean labelled texts: exact, obfuscated, zero-width, base64, url-safe base64, hex, rot13, reversed. No false hit on a different canary, a truncated one, or the same hex behind another prefix. Per-run tokens are deterministic and unique per run id. |
| JSON-schema checker | `test_agent_tests_json_schema.py` | Valid replies, 7 kinds of violation, strict vs lenient extraction |
| Refusal detector | `test_agent_tests_refusal.py` | 32 labelled replies across don't-know / refusal / redirect / complies (EN, ES, FR). Mixed signals are low confidence. |
| Consistency scorer | `test_agent_tests_consistency.py` | Fact disagreement fails, paraphrase with the same facts is "unsure", key-fact extraction |
| Wilson interval + gating, κ computation | — | **next session** (9.3 / 9.4) |
| Each generator (counts, fields, determinism) | `test_agent_tests_generators.py` | Per dimension: count ≥ minimum, required fields, schema round trip, hash, AC link, in-process determinism. Byte-identical output across processes with `PYTHONHASHSEED` 0 / 1 / 4242. Cut reasons: not_authorized, no_traces, no_session_support, disabled, spec_lacks_material, not_applicable. |
| Dataset loader / validator | `test_agent_tests_dataset.py` | Record validation (7 invalid shapes), loader errors (bad JSON, duplicate id, wrong file, hand edits), dangling `same_as`, D9 merge rules, byte-stable regeneration, review + version bump, CRLF checkouts, the exported JSON Schema is fresh and validates every committed case, the committed dataset is current |
| DAG wiring | — | **next session** (no DAG change yet) |
| Also | `test_agent_tests_runner.py`, `_transport.py`, `_trace_latency.py`, `_bench.py`, `test_http_ssl_guarded_opener.py` | Every runner outcome; session-canary rule; robustness same-verdict rule; k-run disagreement; budget, authorization and session cuts; transport body / parse / net_guard refusal; the benchmark as tests (every weakness, no collateral, determinism); the deadlock regression |

## 3. Benchmark: buggy_bot (mock mode, real HTTP, seed 7, 2 runs per configuration)

`python -m tools.agent_tests bench --seed 7 --repeat 2` took about 9 min, most of it BOT_BUG_10's deliberate
1.2 s sleeps. Output: `benchmarks/results/2026-10-12_buggy_bot_phase9.{json,md}`.

| Metric | Result |
|---|---|
| Seeded weaknesses detected | **14 / 14** |
| False positives, all flags off | **0**. All 15 dimensions pass, none undecided, 0 canary hits |
| Collateral failures outside `detected_by ∪ may_affect` | **0** |
| Identical verdicts, run 1 vs run 2 of every configuration | **yes** |
| Requests per configuration | 141 (96 cases; consistency sends 5×, multi-turn up to 10 turns) |
| Baseline latency | p50 4.6 ms · p95 26.5 ms · p95 tokens/turn 50 (budgets: 500 ms / 1000 ms / 150) |

| Weakness | Detected in | Also failing (allowed by `may_affect`) |
|---|---|---|
| 01 system-prompt leak | data_leakage (incl. the base64-encoded leak) | prompt_injection_direct / indirect |
| 02 direct injection | prompt_injection_direct | — |
| 03 hallucination | hallucination | — |
| 04 forgets turn-1 context | multi_turn | — |
| 05 indirect injection | prompt_injection_indirect | — |
| 06 inconsistent repeats | consistency | robustness |
| 07 broken JSON | instruction_format | — |
| 08 out-of-scope answers | scope | — |
| 09 session leak | session_isolation | data_leakage |
| 10 slow replies | latency_cost (p50 1206 ms > 500, p95 1226 ms > 1000) | — |
| 11 fragile matching | robustness | groundedness |
| 12 harmful compliance | harmful_refusal | — |
| 13 tool misuse | tool_use | — |
| 14 ungrounded facts | groundedness | task_success, multi_turn |

Every dimension has a seeded weakness that it alone must catch. task_success is caught as a side effect of 14.

## 4. Acceptance criteria: proof

| # | Criterion | Command | Result |
|---|---|---|---|
| 1 | Every seeded weakness detected when on, not reported when off | `python -m tools.agent_tests bench --seed 7 --repeat 2` · `pytest tests/unit/test_agent_tests_bench.py` | 14/14 detected; 0 false positives with all flags off; 0 collateral; 21 tests pass |
| 2 | Each 9.1 dimension generates cases and produces a verdict | `python -m tools.agent_tests generate --agent buggy_bot` · the benchmark baseline table | 15/15 dimensions generate ≥ their minimum (task 12, grounded 6, no-answer 5, consistency 3×5, robustness 18, multi-turn 5, format 4, scope 7, injection 8 + 5, leakage 6, harmful 5, tool 4, isolation 3, latency 5). Each produces a pass verdict on the clean bot and a fail with its weakness on |
| 3 | Same seed, mock mode → identical verdicts; real-LLM variance below threshold | `bench --repeat 2` · `test_same_seed_gives_identical_verdicts` · `test_generation_is_identical_across_processes_and_hash_seeds` | Mock: **met** (identical over HTTP and in-process, generation byte-identical). Real-LLM variance: **not measured**. It needs 9.4's k-run statistics and LLM credits; `BOT_MODE=llm` is built and unit-tested with a fake connector |
| 4 | Calibration export + κ on the synthetic example | — | **Next session** (9.3) |
| 5 | Existing (non-chatbot) agent-evaluation runs unaffected | `git diff --stat` · full unit suite | No file under `api/`, `agents/`, `workflows/`, `engines/` or `frontend/` changed. The only shared runtime change is the `http_ssl` deadlock fix, which makes a previously hanging call work. Full suite: 1,838 passed, 0 failed |

## 5. Deviations from the plan / design

1. **D7 deferred** (approved "do what is best"). buggy_bot's spec is hand-written from its BRD (`source: brd`).
2. **Runner + benchmark built before 9.3/9.4** (D1). Verdicts are deterministic only, with k = 1 by default; `--k`
   exists, and disagreeing runs are marked `non_deterministic` until the Wilson intervals land.
3. **14 weaknesses instead of 10** (D4), so every dimension has a defect to detect.
4. `weaknesses.yaml` BOT_BUG_11 `may_affect` gained `groundedness, task_success, multi_turn` after the first
   benchmark run. Case-sensitive matching (the weakness itself) also fails "delivery to **Canada**". That is the
   bot really answering wrongly, not an MTA false positive; the ground truth was incomplete.
5. 10 injection cases are split 8 direct + 5 indirect (the plan gives only the total of 10).
6. The plan's "BOT_BUG_04 forgets after N turns" is implemented as a memory window (`BOT_MEMORY_TURNS`, default 1)
   so the Phase 0 test (ask at turn 3) still holds.
7. Paraphrase and other-language variants come from the spec only. A generator never invents them.

## 6. Open issues

1. **Pre-existing deadlock in `tools/agent_eval/http_ssl.guarded_urlopen`** (since the initial import, untested).
   It held the module's non-reentrant `_lock` while calling `ssl_context()`, which takes the same lock, so the first
   guarded request in a process hung forever. **This also affects production:** `live_agent_execution` reaches agents
   through `connect_live_agent` → `_http_call` → `guarded_urlopen`, so its HTTP fallback would hang (until the step's
   1800 s soft timeout) on the first call.
   - **Fix:** take the SSL context before the lock (one line); the guard is unchanged.
   - **Regression test:** `test_http_ssl_guarded_opener.py`. It fails without the fix (deadlock detected in 10 s) and
     passes with it.
   - Worth checking whether any deployed run shows `live_agent_execution` timing out.
2. **The 96 cases are unreviewed** (`reviewed: false`). The human review is yours: `python -m tools.agent_tests review
   --agent buggy_bot --dimension <d> --by "<name>"`. The runner reports the unreviewed count.
3. **Real-LLM mode is untested against a real model** (no credits used). Prompt assembly per flag is unit-tested;
   detection rates in llm mode need 9.4.
4. **Mock-mode numbers are an upper bound.** The rule-based bot's replies are regular. Detectors were also tested on
   real-style phrasings (32 refusal / 30 canary labels), but real agents will produce more `needs_judge`.
5. **The web chat transport** (`WebChatClient`, fresh page per send) has no multi-turn support yet. Phase 9 currently
   tests HTTP agents; browser-chat multi-turn comes with the DAG integration.
6. **TTFT = total time** (non-streaming HTTP). It is stated in every run result.

## 7. Next session (9.3–9.5 + integration), as designed in §7 of the design note

- Scaffold `agents/test_execution/agent_quality_testing/`. DAG step `agent_quality_testing` (needs
  `live_agent_execution`, provides `agent_quality`, non-critical, 2400 s); `brd_compliance.needs +=`. Append-only
  `TestCase` rows; detail in `.aqp_artifacts/runs/<id>/agent_quality.json`.
- LLM judge for `needs_judge` (different model, `FencedTemplate`, schema-validated, quote-grounded); calibration CSV
  + Cohen's κ, with "unverified judge" when κ < 0.6.
- k runs with Wilson intervals, gating on the lower bound; per-dimension regression history.
- D7 drafter (BRD → `agent.yaml` draft).

## 8. Merge notes

| File | Kind | Note |
|---|---|---|
| `tools/agent_eval/http_ssl.py` | **shared, bug fix** | `guarded_urlopen` builds the SSL context before taking `_lock` (3-line diff). Additive and behaviour-preserving except that it no longer deadlocks. Phase 4 doesn't touch this file as far as I know. |
| `requirements.txt` | shared, additive | `+ jsonschema>=4.0` (one line after `pydantic`) |
| `benchmarks/agents/buggy_bot/*`, `tests/unit/test_bench_buggy_bot.py` | Phase 9-owned | No other phase uses buggy_bot |
| New paths | Phase 9-owned | `tools/agent_tests/`, `eval_sets/`, `benchmarks/results/*buggy_bot*`, `tests/unit/test_agent_tests_*.py`, `tests/unit/test_http_ssl_guarded_opener.py`, `docs/phases/phase-9-*.md` |
| Not touched | — | README.md, playwright.config.ts, package*.json, TS runtime, spec_renderer.py, UIExecutionAgent, `workflows/*` (including `agent_evaluation.yaml`), `agents/registry_setup.py`, `api/`, Prisma schema |
| Prisma | — | No change this session. The integration session needs one additive migration (`ALTER TYPE "PipelineStage" ADD VALUE 'agent_quality'`) |
| README "Agent Evaluation" section | deferred | Document Phase 9 in README.md at merge time (README is off-limits during parallel work). Text to adapt: `tools/agent_tests/README.md` |
