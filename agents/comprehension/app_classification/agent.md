# AppClassificationAgent

The **Application Classification Engine** of the evaluation workflow. It decides what kind of application the submission is, so
Action Generation can pick the right testing strategy. It runs right after Runtime Discovery and makes no LLM
calls; the logic is in `engines/runtime/classification.py`.

Classes: **Chatbot · Form Application · Dashboard · Document Generator · REST API · Workflow System · Static Website ·
Hybrid Application**. `Unknown` is returned only when there are no signals at all.

## Inputs
| Key | Type | Required | Notes |
|---|---|---|---|
| `runtime_profile` | object | no | Output of RuntimeDiscoveryAgent; ignored when it shows only a login wall or nothing |
| `repo_graph` | object | no | Knowledge graph from RepoIntelligenceAgent (routes, pages, forms, components, agents) |
| `code_chunks` | list | no | Code chunks used for code-pattern signals (docs and JSON are excluded) |
| `repo_model` | object | no | Repo model; `dependencies` drive the library signals |

At least one of `runtime_profile` or `repo_graph` must be present, otherwise the step is skipped.

## Output: `app_classification`
```json
{"app_type": "Document Generator", "confidence": 0.72, "components": [], "basis": "runtime + code",
 "note": null,
 "scores": {"Document Generator": 16.4, "Form Application": 8.0, "...": 0},
 "evidence": [{"class": "Document Generator", "signal": "download/export controls: Export DOCX", "source": "runtime", "points": 4.0}],
 "testing_strategy": [{"class": "Document Generator", "strategy": "Output testing: fill the input form, generate, download ..."}]}
```
For a `Hybrid Application`, `components` lists the classes it combines (winner first) and `testing_strategy` has one entry per component.

## Behaviour
1. **Signals.** Every signal adds points to one class and is recorded as evidence. Runtime signals count in full and code
   signals at 0.7, because the live app is what users actually get.
   - Runtime signals: input count, generate and download buttons (the example "25 inputs + Generate + Download →
     Document Generator"), chat box, charts and tables, step and approval buttons, an API-only root, content-only pages.
   - Code signals: document, chart, chat and job-queue dependencies; export, generation, chat and stats routes; frontend
     download code; forms parsed from the code; routes with no UI (REST API); pages with no backend (Static
     Website); chat, file-generation, charting and approval code patterns.
2. **Decision.** The highest score wins, except that Form Application and Static Website are generic: any specific class
   (Chatbot, Dashboard, Document Generator, REST API, Workflow System) with at least 4 points beats them. A second specific
   class scoring at least 75% of the winner makes the result a Hybrid Application.
3. **Basis.** `runtime + code`, `runtime` or `code`. When the live app was behind a login or not deployed, the
   classification is code-only and `note` says so.
4. **Confidence** is the winner's share of all points, plus 0.15 when runtime and code both contributed, capped at 0.98.

## Failure mode
Pure function, no I/O. With no profile and no graph, the step is skipped and later steps fall back to the Runtime Discovery `app_type`.
