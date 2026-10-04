# BrdComplianceAgent

The **BRD Compliance Engine** of the evaluation workflow. It joins the two lines of evidence into one requirement → criterion → evidence →
verdict matrix:
- what requirement traceability decided per criterion (`engines/trace/decide.py`: runtime evidence first, then code evidence);
- what the Pass/Fail Engine observed at runtime.

It also reports where the code and the running app disagree. The score itself stays in `engines/scoring/v1.py` (compliance-v1.1), which
reads this agent's discrepancies and the runtime counts for its gates and recommendations. It makes no LLM calls; the logic is in
`engines/compliance/matrix.py`.

## Inputs
| Key | Type | Required | Notes |
|---|---|---|---|
| `requirements` | list | yes | After traceability: verdict, score, priority, origin, verifiability, criteria |
| `criterion_verdicts` | list | yes | Traceability output, including `static_verdict` / `static_strength` (the code-review verdict, kept even when runtime decided) |
| `pass_fail` | object | no | Runtime verdicts per criterion and test, with artifact links |
| `mode`, `live_url` | string | no | Whether runtime testing was possible, for the runtime-only rule |

## Output: `brd_compliance`
- `matrix[]`: one row per requirement (code, title, priority, origin, verifiability, scored, verdict, score), each with `criteria[]`:
  - final `verdict` / `resolved_verdict`, `strength`, `credit`, `rationale`;
  - `basis`: `runtime` (E5 or E4 verified), `code` (E3 or E2) or `none`;
  - `static`: the code-review verdict, strength and rationale;
  - `runtime`: verdict (supported, refuted or unverified), strength, `mixed`, and `tests[]` (verdict, score, strength, reason,
    screenshot and document paths);
  - `discrepancy`.
- `discrepancies[]`: `kind`, `severity`, `detail`, `criterion_code`, `requirement_code`, `requirement_title`, `priority`. Most severe first.
- `evidence_mix`:
  - `by_strength` (E5…E1 and none, over scored criteria);
  - `runtime_share`;
  - `credit_by_basis` (the share of earned credit from runtime versus code evidence).
- `counts`: requirement and criterion totals, and one count per discrepancy kind.

## Discrepancy kinds
| kind | When | Severity |
|---|---|---|
| `broken_at_runtime` | The final verdict is `verified_fail` but the code review found it implemented or partial. The code is there, but the behaviour is wrong. | high |
| `mixed_runtime` | The criterion's runtime tests disagree: some pass, some fail. | warning |
| `runtime_only_unverified` | The app was deployed, the requirement can only be proven at runtime (latency, output quality), and no runtime verdict was reached. | warning |
| `missed_by_code_review` | It works at runtime, but the code review judged it not implemented or could not find it. | info |

Only scored requirements produce discrepancies: `brd` origin, or `inferred` with confidence of at least 0.5.

## Effect on scoring (compliance-v1.1)
The formula is unchanged, so re-scoring an older run gives the same number. The changes are new gates and recommendations:
- **`runtime_not_executed`** (warn): no runtime test executed, and the app is not behind a login.
- **`runtime_inconclusive`** (warn): more than 30% of the attempted runtime tests were inconclusive.
- **`broken_at_runtime`** (warn): for medium and low priority. High-priority runtime failures already block through `high_priority_failed`.
- **Recommendations:**
  - "implemented in code but broken at runtime" (`failed_test`);
  - inconsistent at runtime (`flaky_behavior`);
  - runtime-only, not reached (`coverage_gap`);
  - works live but not found in code (`weak_validation`).

## Failure modes
Without traced requirements, the step is skipped. Runs traced before this change have no `static_verdict`, so they produce no
`broken_at_runtime` or `missed_by_code_review` entries. Everything else still works.
