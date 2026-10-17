# AgentTestGenerationAgent

Fourth step of the agent-evaluation pipeline. Designs black-box **prompt → reply** acceptance tests
**strictly from the BRD**.

## Inputs
| Key | Type | Required | Notes |
|---|---|---|---|
| `requirements` | array | yes | From BrdBuilderAgent (each has a verified `source_quote`) |
| `brd_markdown` | string | yes | The BRD, the only source of test content |
| `agent_profile` | object | no | Only `interface` is used, so inputs match how the agent is called |
| `connector_mode` | string | no | LLM connector override |

## Outputs
`test_cases`: `[{code: "TC-001", title, category, variant_type, priority, requirement_ref, acceptance_criterion,
brd_reference, area, input, expected_behavior, pass_criteria[], status: "pending"}]`. Agent-specific tests come first.

## Behaviour
Two Gemini calls run in parallel, both schema-enforced. Neither is given a code-derived feature list.
- **Agent-specific:** tests per requirement (3/2/1 by priority, or 2/1/1 above 12 requirements, capped at 40). Each one
  verifies one of the requirement's acceptance criteria.
- **General:** only cross-cutting qualities the BRD itself states (NFRs, scope, security, privacy, error handling). If the
  BRD states none, there are none. There are no generic AI-safety tests.
- **Traceability check:** every test must carry a verbatim `brd_reference`. It is kept only if that quote is found in
  the BRD (`BrdIndex.grounded`), or if its criterion matches its requirement's own text. Agent-specific tests without a
  valid `requirement_ref` are discarded. Discard counts are reported in the run log.
- **Executable only:** a test that needs a failure injected (the app's LLM / API / network / server failing, a rate
  limit, a timeout, a revoked API key) or load (N concurrent users) is dropped — `engines.runtime.actions.needs_fault`.
  Its criterion goes to `static_only_criteria` with that reason, so it is judged from the code instead of ending
  "not executed".
- **No repeats:** one positive test per criterion; another test of a criterion must be a different variant, and at most
  2 negative / edge tests per criterion and variant, never two near-identical ones (title + expectation similarity
  ≥ 0.75). Agent-specific tests win over general ones. The general family keeps at most its share of the budget.
- **Top-up:** a runtime criterion still without a test (and not dropped as un-runnable) gets one targeted call asking
  for exactly one positive test per such criterion.
- **Clean inputs:** literal `\n` sequences in a test's input, title or expectation become real line breaks, so
  "Label: value" lines reach the fields they name.

## Failure mode
`status: failed, blocking: true` when there are no requirements, Gemini fails, or no test can be traced to the BRD.
