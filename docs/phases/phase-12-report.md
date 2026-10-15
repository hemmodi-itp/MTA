# Phase 12 report — MTA Self-Testing and Continuous Benchmarking

MTA now tests itself in six ways:
- property tests over its generators and renderer;
- golden snapshots of the spec renderer;
- contract tests on recorded inputs;
- eval sets for every LLM agent, replayable without an LLM;
- metric regression gates over the benchmarks;
- mutation testing of its own core modules.

The work found two real bugs in generated tests, three mismatches between agents and their manifests or test
isolation, and one wrong check of our own. All are fixed and listed in "Bugs found" below.

## 12.1 Property-based tests

`tests/unit/test_phase12_properties.py` (Hypothesis) has 11 properties:
- renderer: string literals, balanced brackets, titles that parse back;
- test-title and `--grep` round trips;
- API boundary values sit on the right side of each bound;
- length boundaries;
- path templating;
- quarantine signature and release;
- fingerprint diff;
- every mutant parses;
- the assertion linter never crashes.

All 11 pass in **8.6 s** at 150 examples per property. `MTA_HYPOTHESIS_EXAMPLES=3000` runs a deep pass: all 11 pass
in 154 s, and the nightly job runs 2000 examples. The earlier 14-minute run was not reproduced. It was most likely
Hypothesis shrinking the two failing properties (shrinking random text is slow) while the CI benchmark shared the
machine. Lowering the example count was not needed. The quarantine property keeps its real `quarantine.yaml` I/O
(1.9 s), because it tests the file round trip.

The two failures from the earlier session:
- **Real bug, `tools/whitebox/api_tests.py` `_bad_cases`.** Decimal ranges were always written with 2 decimals, so
  for `max 0.016` the "at max, accepted" case sent `"0.02"`, which is above the max. A correct app would have failed
  the test. The step and the decimal places now come from the bounds' own precision: `_places` gives at least 2
  decimals and step = 10^-places. `0.016` is now sent as `"0.016"` and `"0.017"`. Bounds that need 2 decimals or
  fewer are unchanged, and the Phase 8 tests pass (23).
- **Second real bug, found by the deeper run:** the out-of-range label formatted the value with `:g` (6 significant
  digits). It said `above max (1000.11)` while sending `1000.106`. The label now shows the value actually sent, and
  the property asserts that.
- **`test_renderer_any_strings_stay_inside_literals` was the test's fault, not the renderer's.** The failing input was
  a scenario title of `"\x85"`. The test's `_code_only` helper split lines with Python's `str.splitlines()`, which also
  breaks on `\x85`, `\x0b`, `\x1c` and similar characters. JavaScript line terminators are only `\n`, `\r`, U+2028 and
  U+2029, and the last two are legal inside string literals since ES2019. The renderer escapes `\n` and `\r`, so the
  generated file is valid. TypeScript 5.9 `tsc` compiles a spec with raw U+2028 and `\x85` in its strings. The helper
  now splits on `\n` only; the property passes at 3000 examples.

## 12.2 Golden snapshots

These were already done (5 cases, plus a check that every step action is covered and a `tsc` type check of every
golden). Confirmed: 7/7 pass.

## 12.3 Contract tests on recorded inputs

`tests/unit/test_phase12_contracts.py` has 45 tests. The recorded inputs come from the bench_buggy_shop discovery run:
requirements, business scenarios, app map, form model, API inventory, and one Playwright JSON report with 3
failures. They are stored in `tests/fixtures/recorded/buggy_shop/` as compact JSON, 580 KB in total. The pipeline runs
in one temporary project:
- TestDesignAgent (`design_llm: false`);
- white-box `extract.run` and `api_tests.generate`;
- TriageAgent (`triage_llm` and re-runs off);
- ReportingAgent.

Checks:
- Every artifact a step writes is validated with `contracts/artifacts`, using the orchestrator's own step-to-artifact
  map (`boundary.validate_step_outputs`).
- Artifacts with no registered model get a structural check: `code_rules.json`, `triage.json`, `defects.json`, the
  API specs and the report JSON.
- Each agent's returned dict contains the outputs its `agent.json` declares.
- All 35 `agent.json` files are checked against the CLAUDE.md schema: field types, category equal to the folder,
  `module_path`, `doc`, registry key, known dependencies, `skills` equal to the `skills.py` SKILLS keys, and all 8 files
  present.
- The recorded inputs themselves validate.

What it found (all fixed):
- **TestDesignAgent** declares the output `skipped` but returned it only when it skipped. It now returns
  `skipped: False` on a normal run.
- **ReportingAgent `agent.json`** declared an output `traceability` that the agent never returns: traceability is a
  key inside the saved report. The manifest now lists what the agent really returns: `report_path` (with what it
  holds), `html_report_path`, `failures_log_path`, `index_path` and `quality_gates`.
- **Test isolation gap.** `tests/conftest.py` redirects every import-time alias of `PROJECTS_BASE` so that unit
  tests never write into the real `application_assets/projects/`. It was missing `agents/test_execution/triage/agent.py`,
  which writes `triage.json` and `defects.json`, and three discovery modules. They are added.
- `agent_quality_testing` is registered in `api/pipeline.py` (the evaluation pipeline's step table), not in
  `agents/registry_setup.py`. The check accepts both registries; CLAUDE.md names only the second.
- My first test project produced 0 selected cases: with no modules and no business scenarios, every case was cut as
  `no_scenario`. The fixture now includes both, and the test asserts that cases are selected and AC coverage is
  above 50%, so an empty pipeline cannot pass.

## 12.4 LLM-agent eval sets

`tools/selftest/llm_evals.py` with data in `tests/fixtures/llm_evals/<agent>/`:
- `cases/`: the fixed inputs;
- `recorded/`: raw replies plus the invariants each reply must violate;
- `prompt_hashes.json`: the prompt-file hashes at the last recording.

Modes:
- `--replay` feeds the recorded replies through each agent's real entry point using a fake `.generate()` LLM. The
  agent's own parsing and guards run, and the invariants are checked. Runs in CI with no LLM.
- `--live [--record]` calls `ConnectorRegistry(settings).get_llm()` and loads `.env` for `GOOGLE_API_KEY`.
- `--check-stale` exits 1 when a prompt file changed since the last recording.
- `--stamp` accepts the current prompt files after a review.

Invariants are checked on two levels:
- `raw.*`: the model's reply itself. A regressed prompt shows up here even when a guard repairs the output later.
- `out.*`: what the agent produced.

Every recording must violate exactly its `expect` set.

| Agent | Entry point | Invariants |
|---|---|---|
| Comprehension | `extract_requirements` | reply is JSON; every criterion quote is found by `BrdIndex.quote_match`; every declared AC kept; status ok |
| Comprehension | `generate_business_scenarios` | `validate_business_scenarios` keeps every scenario; AC ids are known; every given AC is exercised |
| TestData | `generate_test_data` | `validate_test_data` keeps it; no payload (`drop_security_payloads`, `detect_payload`); caps; scenario id |
| SemanticMap | `SemanticMapAgent._llm_map` | (new invariants) every `locator_id` is in `dom_elements`; scenario ids known and all mapped; 3–7 elements |
| ScriptGeneration | `_plan_via_llm` | `_validate_plan`; no test dropped by the agent's guards; `lint_plan` finds no weak test; `filter_plan` drops nothing |
| TestDesign | `interpret_module` | valid `DesignHints`; `sanitize` drops nothing |
| Healing | `healing_audit.jsonl` trajectory | applied heals ≥ identity threshold; refusals below it or ambiguous; patches pass `_structurally_valid_block`, add no sleep, keep the AC tag header; a revert follows an applied heal; approver matches the outcome |

**Recordings: 25/25 as expected.**
- **19 hand-written:** one good reply per agent, plus 12 bad replies, each proving its checker catches what it targets
  (invented quotes, a dropped declared AC, prose instead of JSON, unknown AC ids, a duplicate title, an over-cap
  variant with a path-traversal value, an invented locator, a fixed sleep, a weak oracle, an unknown locator key,
  invalid design references, an extra schema key, and an unsafe heal trajectory).
- **6 from one live run** (`--live --record`, `gemini-3.6-flash`, 6 calls): 5 agents clean on the first call.

Findings from the live run:
- **Model weakness, caught as designed.** In the plan, Gemini added a positive "submit valid product details" test
  with no backend evidence, and the Phase 5 linter scores it 65 (< 70). In the full pipeline, the linter-feedback
  regeneration round exists for exactly this; the eval measures the single call. The recording keeps
  `expect: ["out.assertions_strong"]`.
- **One of my checks was wrong.** Gemini returned a "Delete an existing product" scenario with no AC ids, and none of
  the three given ACs applies to deleting. The prompt asks for ids only "when any applies", so the check
  "every scenario is traced" was too strict. It became "every given AC is exercised by some scenario".

Healing is an ADK tool loop with no single prompt call, so `--live` skips it. Its eval reads a `healing_audit.jsonl`
trajectory. No recorded audit file existed, so the trajectories are hand-written in the exact Phase 6.9 row format.

## 12.5 Nightly benchmark regression gates

`tools/benchmark/regression_gate.py` takes the latest `benchmarks/results/*.json` of each kind and compares it with
`benchmarks/baselines.json`. Baselines were seeded from the current committed results; `--update` re-seeds them. It
exits 1 and names each failed metric; a metric the run did not measure is reported, not failed.

| Kind | Metrics (from the real result keys) |
|---|---|
| e2e (`tools.benchmark.run`, any label) | `seeded_bug_detection.rate` must not drop; `false_failure.rate` and `flaky.rate` must not rise; `ac_extraction_recall` must not drop; `heal_precision.precision` ≥ 0.95 when measured |
| phase6_healing | bugs detected / bugs; clean-run failure rate; heal precision (healed − wrong) / healed ≥ 0.95; `heal_success_pct` |
| phase7_nfr | detected / targets; clean failures / tests |
| phase8_whitebox | bugs caught / bugs; API clean failure rate; endpoint coverage %; mutation score % |
| phase10_ci | checks passed / total |

On the current results all 16 gate rows pass. The e2e heal precision is "not measured", because the final run applied
0 heals. `ci/github-actions.yml` has a new `nightly-benchmark` job, run on schedule or with `stage: benchmark`:
1. the healing, NFR, white-box (12 mutants) and CI benchmarks;
2. `regression_gate --require phase6_healing,phase7_nfr,phase8_whitebox,phase10_ci`;
3. `llm_evals --replay` and `--check-stale`;
4. property tests at 2000 examples;
5. upload of `benchmarks/results/`.

The full LLM-driven e2e benchmark (`tools.benchmark.run`) is not in the nightly job, because it spends LLM budget.

## 12.6 Mutation testing of MTA itself

`tools/selftest/mutate_mta.py` reuses the Phase 8 runner, `tools/whitebox/mutation.py`, which gained a `deadline`
(time box) and a `not_run` count. Each target maps to the unit tests that cover it:

| Target | Covering tests |
|---|---|
| `tools/test_design/bva.py` | `test_test_design_bva`, `_generators`, `_pipeline` |
| `tools/test_design/ep.py` | `test_test_design_generators`, `_pipeline` |
| `tools/triage/triage.py` | `test_triage_and_safe_healing`, `test_phase6_safe_healing` |
| `tools/test_creation/assertion_linter.py` | `test_assertion_linter`, `test_phase5_oracles` |

Flags:
- `--max-mutants`: per target, spread over the file;
- `--time-box`: minutes for all targets.

Before it starts, the tool checks that the targets have no uncommitted changes and that the covering tests pass. Tests
run with `PYTHONDONTWRITEBYTECODE=1`, so a stale `.pyc` can never stand in for a mutated file. At the end, `git diff`
must be empty.

**One run** (`python -m tools.selftest.mutate_mta`, 25 mutants per target, 30-minute time box;
`benchmarks/results/2026-10-15_mta_selftest_mutation.{json,md}`). **72/100 mutants killed (72.0%)** in 880 s, with
all 100 run inside the time box. Sources restored: `git diff` is empty and no backup file was left.

| Target | Mutants | Killed | Survived | Score |
|---|---|---|---|---|
| `tools/test_design/bva.py` | 25 | 19 | 6 | 76.0% |
| `tools/test_design/ep.py` | 25 | 13 | 12 | **52.0%** |
| `tools/triage/triage.py` | 25 | 21 | 4 | 84.0% |
| `tools/test_creation/assertion_linter.py` | 25 | 19 | 6 | 76.0% |

Survivors are faults the unit tests let through:
- **ep.py (12), the weakest module.** `invalid_classes` lines 35, 40, 44, 61, 65 (comparisons and the length offset);
  `_not_matching:80` (dropping a `not`); `valid_classes:95–96` (`or`↔`and`, a negated condition, `==`↔`!=`);
  `_level:104`; `valid_known:122`; `generate:131` (`and`↔`or`). Equivalence-partitioning classes are checked in
  aggregate by the pipeline tests, not class by class.
- **bva.py (6).** `numeric_points:52` (0→1), `date_points:81` (2→3), `_step_for:95` (negated condition),
  `fmt_number:103` (`<`→`<=`), `generate:199–200` (`==`↔`!=`, 0→1).
- **triage.py (4).** `_spec_key:66` (`>=`→`>`), `classify:171` (`or`→`and`), `classify:184` (3→4), and
  `_history_note:261` (negated condition).
- **assertion_linter.py (6).** `_is_submit:92` (`and`→`or`), `lint_test:111` (`or`→`and`), and four penalty constants
  (40→41, 35→36 twice, 0→1). The constant ones are near-equivalent, because the tests assert weak vs. strong, not
  exact scores; the two boolean ones are real gaps.

## Tests

| File | Tests |
|---|---|
| `test_phase12_properties.py` | 11 properties |
| `test_phase12_golden.py` | 7 |
| `test_phase12_contracts.py` | 45 |
| `test_phase12_llm_evals.py` | 7 (replay of every recording; every agent has a good and a caught bad reply; a bad reply marked good fails; staleness detection; committed hashes current; replay LLM refuses extra calls; `--live` with any `.generate()` object records) |
| `test_phase12_regression_gate.py` | 8 |
| `test_phase12_mutate_mta.py` | 3 |

Full unit suite: **2865 passed, 0 failed** (8 min 24 s). That includes the exported-schema check, which was stale before Phase 10 and was fixed in its own commit.

## Still open

- **Contract models** for `code_rules.json`, `triage.json`, `defects.json` and the report JSON. Today these get
  structural checks only; they are not registered in `contracts/artifacts`.
- **Recorded Healing trajectory.** Record a real `healing_audit.jsonl` from a healing benchmark run and add it to the
  Healing eval set; today it is hand-written.
- **More live recordings.** One live run was recorded, one case per agent. Re-record after any prompt change
  (`--check-stale` fails the nightly job until then), and add cases for other modules.
- **Mutation coverage.** Only a capped sample of mutants was run (100 of 514 possible mutants across the four files). The surviving mutants listed above
  are candidate unit tests. The mutation score is not gated because it is not comparable once the sources change.
- **e2e benchmark in the nightly job.** It needs LLM budget and a generated suite. Today its baseline only moves when
  someone runs `tools.benchmark.run`.
