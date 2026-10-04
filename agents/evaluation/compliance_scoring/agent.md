# ComplianceScoringAgent

Final step. It turns criterion verdicts and review findings into the **BRD Compliance Score**, its 90% confidence band,
the **verification depth**, the **Quality Scorecard**, **gates** and recommendations. It makes no LLM calls. It uses `engines/scoring/v1.py`,
a pure, versioned function (`SCORING_VERSION` is stored with every score).

## Inputs
`requirements` (with `origin`, `confidence`, `priority`, `verifiability`, `criteria`), `criterion_verdicts`, `findings`,
`scorecard`, `test_cases`, `execution_results`, `mode`, `live_reachable`.

## Outputs
`score` (`compliance`, `ci_low`, `ci_high`, `verification_depth`, `score_kind`, `gates`, `scorecard`, `risk_level`,
legacy dashboard fields), `recommendations`, `summary`.

## Formula
- **Compliance** = 100 × Σ pᵣ·score(R) / Σ pᵣ, with p = 3/2/1 for high/medium/low priority.
- **score(R)** = Σ w·value·strength over its criteria. Value: implemented 1, partial 0.5, otherwise 0. Strength: E5 1.0, E4 0.9, E3 0.75, E2 0.55, E1 0.
- **Which requirements count:** only `brd` requirements, or `inferred` ones with confidence ≥ 0.5. Code-derived `descriptive` requirements are excluded, because their evaluation would be circular.
- **Insufficient evidence** stays in the denominator with 0 credit.
- **Confidence band:** 400-sample bootstrap over requirements with a fixed seed.

## Gates
- **BLOCK:** a critical scanner finding, or a high-priority requirement that failed at runtime.
- **WARN:** compliance under 60; verification depth under 30% when runtime was possible; more than 20% of requirements with insufficient evidence; an unapproved inferred BRD; no scorable requirements.

## Failure mode
Pure computation that never fails on missing data. With no scorable requirements, `compliance` is null and a gate says why.
