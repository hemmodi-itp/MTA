# RequirementTraceabilityAgent

Decides **one code-evidence verdict per acceptance criterion**, then rolls criteria up into requirement verdicts.
It is **static only**: in the DAG it runs in parallel with the browser execution, so it never reads
`test_cases` / `execution_results`. Runtime evidence is merged later by BrdComplianceAgent through
`tools.apply_runtime_evidence(static_trace, requirements, test_cases, execution_results)`. The deterministic parts
live in `engines/trace/`.

## Inputs
| Key | Type | Required | Notes |
|---|---|---|---|
| `requirements` | array | yes | From BrdBuilderAgent. Each has `criteria[]` with DB `id`s. Never mutated |
| `repo_graph`, `code_chunks` | object, array | yes | From RepoIntelligenceAgent |
| `repo_dir`, `repo_full_name`, `commit_sha` | string | yes | For citation validation and GitHub links |
| `repo_model` | object | no | `repo_model.coverage` (indexer coverage) feeds the absence protocol |
| `repo_coverage` | object | no | From RepoFetchAgent; a truncated listing blocks `not_implemented` |

## Outputs
- `criterion_verdicts`: `[{code, criterion_id, requirement_code, verdict, resolved_verdict, best_strength, credit, agreement, rationale, llm_failed, samples, sample_b, negative_search, static_*}]`
- `evidence_items`: static and structural evidence rows, each with its citation
- `traced_requirements`: copies of the requirements with `verdict`, `score`, legacy `status` and `llm_unavailable` (count). Renamed from `requirements` so it no longer collides with BrdBuilderAgent's key
- `static_trace`: JSON. Holds each criterion's verifier samples (`static_a` / `static_b`), primary-sample evidence, negative search and LLM-failure flag. `apply_runtime_evidence` re-decides from it, and the shape is documented in `tools.py`
- `llm_failures`: number of criteria not evaluated because the LLM verifier failed

`static + apply_runtime_evidence` gives exactly what the old single combined pass gave
(`tests/unit/test_trace_static_runtime.py`).

## Behaviour (all criteria of all requirements in one pool of 6)
1. **Query expansion, batched:** one LLM call per group of requirements (up to 24 criteria), using the repo's real vocabulary.
2. **Hybrid retrieval** (`engines/trace/retrieve.py`): BM25 plus graph seeds, merged with reciprocal-rank fusion and expanded along wiring edges.
3. **Verifier sample A** at temperature 0.2.
4. **Follow-up and sample B:** if A is unsure because named code is missing, that code is fetched and A re-runs. **Sample B** (temperature 0.7, shuffled chunks) runs **concurrently** with that follow-up.
5. **Skip rule:** sample B is skipped when A, after validation, is decisive. That means either:
   - (W) A is implemented or partial, has at least one validated and wired citation, no rejected citation, and confidence `high`; or
   - (C) A is implemented, has at least two validated citations, no rejected citation, confidence not `low`, and nothing in `need_more`.

   Absence and unsure answers always get sample B.
6. **Citation validation and wiring proof** (`engines/trace/citations.py`): an uncited or false claim earns nothing (E1). Wired code is E3; otherwise E2.
7. **Absence protocol** (`engines/trace/absence.py`): `not_implemented` needs all of the following:
   - a concrete `looked_for`;
   - at least 5 retrieval candidates;
   - a listing that is not truncated;
   - no unfetched or unindexed source file whose path matches the search;
   - fewer than 10% of source files missing from the index.

   If any condition fails, the verdict is `insufficient_evidence`, with the reason in the rationale.
8. **Decide** (`engines/trace/decide.py`): the conservative of the two samples. Runtime-only criteria reach at most `partial`.

## All untrusted text is fenced
Requirement text, criteria, repository vocabulary, wiring paths and code all go through `fence_untrusted`. The preamble carries `UNTRUSTED_RULE`.

## Failure modes
- **No repository index:** the agent blocks (`failed`).
- **Verifier failure:** if one sample fails, the other is used alone. If no sample answers, the criterion gets verdict
  **`llm_unavailable`** (`llm_failed: true`, `llm_error`). It earns no credit, it is excluded from the requirement's score
  denominator, and it is counted in `llm_failures`. The step returns `status: partial` with an `error`.
- **Isolated exceptions:** an exception while tracing one criterion marks only that criterion `llm_unavailable` (with the error).
- **Query-expansion failure:** that batch is searched with the criterion wording only, and a warning is emitted.
