# FinalReportAgent

The **Final Evaluation Report** — the last step of the evaluation workflow. It assembles what Components 1–8 recorded into one
report per run and renders it as JSON, Markdown and a standalone, printable HTML page. It is deterministic and makes no LLM calls, so
nothing in the report is more confident than the evidence behind it. The logic is in `engines/report/final.py`.

## Inputs
It reads the pipeline request after every step:
- `score` (compliance scoring, required);
- `requirements`, `brd_compliance`, `pass_fail`, `app_classification`, `runtime_profile`;
- `findings`, `recommendations`;
- run metadata: `run_id`, `github_url`, `repo_full_name`, `branch`, `commit_sha`, `mode`, `live_url`, `brd_source`, `brd_path`,
  `agent_profile`.

The step is skipped without a compliance score.

## Output: `final_report`
`{"data": <report JSON>, "markdown": "...", "html": "<!doctype html>..."}` is stored in `Run.finalReport` and served by
`GET /api/runs/:runId/report?format=html|md|json`. The HTML is shown in the run's **Report** tab, sandboxed so no scripts run, and
can be printed or saved as PDF from the browser.

Report JSON sections:
| Section | Content |
|---|---|
| `meta` | Repository, branch, commit, mode, live URL, BRD source and path, agent name, scoring version |
| `decision` | `outcome`, reason, compliance, 90% interval, score kind, risk, verification depth, number of blocking and warning gates |
| `summary` | Executive summary sentences built only from the numbers |
| `application` | App type and components, classification basis, testing strategy, pages inspected, login, and whether credentials are needed |
| `requirements` | The compliance matrix: requirement verdict and score, and per criterion its verdict, strength, basis, discrepancy and runtime tests |
| `runtime` | Pass/fail counts and pass rate; failed and inconclusive tests with reasons and screenshot links; not-run tests grouped by reason; passed tests |
| `discrepancies` | Code vs runtime disagreements |
| `findings` | Critical and high repository-review findings (up to 15) |
| `gates`, `recommendations` | From compliance scoring (up to 15 recommendations) |
| `coverage` | Evidence mix, and the criteria without evidence |
| `limitations` | What the report could not establish: not deployed or behind a login, inconclusive or unexecuted tests, a low runtime share, an inferred BRD, unscored requirements, a wide interval |
| `method` | The evidence ladder and how the score is computed |

## Decision rules
| Condition | Outcome |
|---|---|
| No scorable requirements | Not assessable |
| Any blocking gate (critical security, a high-priority requirement failed at runtime) | Not compliant |
| Compliance ≥ 75, no warnings | Compliant |
| Compliance ≥ 75, with warning gates | Compliant with warnings |
| 50 ≤ compliance < 75 | Partially compliant |
| Compliance < 50 | Not compliant |

## Safety
- All text from the BRD, the code and the tested app is HTML-escaped by the renderer.
- The route serves the page with a `sandbox` CSP: no scripts, links open in a new tab.
- Markdown and JSON are served as downloads.
- Screenshot links point to `/api/runs/:runId/execution-files/…`, which checks that the viewer can see the run.
