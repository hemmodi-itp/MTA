# tools/agent_tests — testing AI agents and chatbots (Phase 9)

This package tests an agent with dimensions built for non-deterministic systems, not just "did it answer". Design:
`docs/phases/phase-9-design.md`. Report: `docs/phases/phase-9-report.md`.

```bash
python -m tools.agent_tests generate --agent buggy_bot --seed 7     # agent.yaml + catalogs → golden dataset
python -m tools.agent_tests list     --agent buggy_bot --unreviewed
python -m tools.agent_tests review   --agent buggy_bot --dimension scope --by "Jane QA"
python -m tools.agent_tests validate --agent buggy_bot
python -m tools.agent_tests run      --agent buggy_bot --url https://agent.example.com [--canary-sys TOKEN] [--k 1]
python -m tools.agent_tests bench    --seed 7 [--in-process] [--repeat 2]
```

## How it fits together

| Piece | Role |
|---|---|
| `eval_sets/<agent>/agent.yaml` | `AgentSpec` (`spec.py`): transport, acceptance criteria with examples, knowledge base, scope, policy, memory facts, formats, tools, budgets, thresholds, authorization. **Its presence is the opt-in.** |
| `catalog/*.yaml` | Curated, versioned red-team payloads and robustness rules. Generators never write attack text. |
| `generators/<dimension>.py` | One per dimension, pure and deterministic: `(spec, catalogs, seed) → cases + cut[reasons]`. |
| `eval_sets/<agent>/<dimension>.jsonl` | The golden dataset (`models.AgentTestCase`, schema in `schema/`), with `manifest.json` versions. |
| `checks/` | Deterministic oracles: canary (also base64 / hex / rot13 / obfuscated), refusal / don't-know / redirect, JSON schema, text, consistency, tool trace, latency budgets. |
| `transport.py` | Conversation transport: session id or client-side history, trace and usage paths. Goes through `net_guard` (public hosts only). |
| `runner.py` | Runs cases (k times), applies the checks, compares robustness variants with their base, and decides latency over the whole run. Outcomes: pass / fail / needs_judge / error / non_deterministic. |
| `bench.py` | buggy_bot with each weakness on and off: detection, false positives, determinism. |

## Dimensions

These are the minimum cases per agent from the plan. `generate` reports any shortfall.

| Dimension | Min | Judged by (deterministic) |
|---|---|---|
| task_success | 10 | contains / regex from the AC examples |
| groundedness | 5 | KB facts present and the right citation |
| hallucination | 5 | don't-know detector (hedged specifics → needs_judge) |
| consistency | 3 × 5 sends | key facts identical, and wording similarity ≥ 0.80 (else needs_judge) |
| robustness | 10 | same verdict as the base case. Empty / emoji-only inputs: a graceful reply |
| multi_turn | 3 | contains on the final turn (recall at turn 10, correction, topic switch) |
| instruction_format | 3 | JSON Schema, word limit |
| scope | 3 | redirect / refusal detector |
| prompt_injection_direct | 6 | run marker absent in any encoding |
| prompt_injection_indirect | 4 | run marker absent |
| data_leakage | 3 | system-prompt canary, PII and other users' data absent |
| harmful_refusal | 3 | refusal detector |
| tool_use | 3 | trace assertions (only when the agent exposes a trace) |
| session_isolation | 3 | session A's canaries never reach session B |
| latency_cost | budgets | p50 / p95 time and p95 tokens per turn against `budgets` |

## Safety rules

- Red-team dimensions need `authorization.owned_or_authorized: true` in `agent.yaml`.
- Canaries are unique per run and stored as placeholders (`{{RUN_MARKER}}` …) in the dataset. The system-prompt
  canary only applies where it was planted (the benchmark bot via `BOT_CANARY`, or an owner-declared marker).
- Harmful-request probes are retail and policy-shaped requests only (`catalog/harmful.yaml` header).
- No LLM call anywhere in this package yet. The LLM judge (9.3), Wilson statistics (9.4) and regression
  comparison (9.5) come next, together with the `agent_evaluation.yaml` integration.
