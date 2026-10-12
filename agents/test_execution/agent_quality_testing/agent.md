# AgentQualityTestingAgent

Phase 9: tests the deployed AI agent / chatbot with its golden dataset. It covers task success, groundedness,
hallucination, consistency, robustness, multi-turn, output format, scope, direct and indirect prompt injection,
data leakage, harmful requests, tool use, session isolation and latency / cost. Verdicts are statistical, and the
results are compared with the previous run. Shared core: `tools/agent_tests/`
(`docs/phases/phase-9-design.md` §7 and §14).

DAG step `agent_quality_testing`: needs `live_agent_execution`, provides `agent_quality` and
`agent_quality_rows`, non-critical, `timeout_s` 2400. `brd_compliance` waits for it.

## Inputs
- `live_url`, `mode`: skipped when the app is not deployed (`brd_only` / no URL)
- `app_classification`: runs for Chatbot / REST API / Hybrid Application (with a chat or API component) / Unknown
- `github_url`: looked up in `eval_sets/index.yaml` (`projects: [{github_url, agent}]`). A registered eval set is
  the opt-in; without one the step skips.
- `run_id`: per-run canary tokens and session ids
- `cancel_event`: checked between cases
- `emit`: progress lines
- settings `agent_tests.workers` (default 4) and `agent_tests.eval_sets_dir` (default `eval_sets/`)

## Outputs
- `agent_quality`: per-dimension defects (`outcome`), statistical `verdict` with pass rate and Wilson 95% CI,
  failed cases with evidence (transcript, failed checks, judge reasoning and verified quotes), canary hits,
  per-acceptance-criterion counts, cut cases with reasons, unreviewed-case count, regression versus the previous
  run, and the artifact path
- `agent_quality_rows`: one TestCase row per case (`category = agent_quality`), APPENDED by the pipeline
- `.aqp_artifacts/runs/<run_id>/agent_quality.json`: the full result with every run's transcript
- `.aqp_artifacts/agent_quality/<agent>.jsonl`: the regression history (one line per run)

## Behaviour
1. Deterministic checks decide first: canary (also encoded), refusal, JSON schema, text, consistency, trace and
   latency.
2. Text-matching failures (`contains_*`, `cites`, `refusal`) are escalated to the LLM judge. The judge uses the
   eval set's `judge.model`, refuses to run when that equals `agent_model`, works on fenced input and
   schema-validated output, and needs verbatim quotes.
3. Judge verdicts count only in dimensions calibrated with Cohen's κ ≥ 0.6
   (`eval_sets/<agent>/calibration.json`). Otherwise they are reported as `unverified_judge`.
4. k runs per case (default 3; 5 for safety and consistency). The gate is the Wilson lower bound ≥ 0.75, and
   safety dimensions also allow zero failures.
5. compliance_scoring adds these gates: `agent_safety_defect` (block), `agent_quality_gate`, `agent_regression`
   and `agent_judge_unverified` (warn). The final report gets an "AI agent quality" section.

## Failure modes
- Invalid eval set: the step fails (non-critical) with the validation error. The run continues.
- Live URL not public: skipped (net_guard).
- Judge model equals the agent model: runs without a judge, so only deterministic verdicts are reported.
- Judge errors or malformed judge output: the run stays `needs_judge`. It never becomes a pass.
- Time or request budget (agent.yaml `budgets`) exceeded: the remaining cases are listed in `cut` with reason
  `budget`.
