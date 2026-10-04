# LiveAgentExecutionAgent

Agent-evaluation pipeline step that **runs the generated tests against the deployed agent** and grades each
reply with Gemini. Skipped in `brd_only` mode.

## Inputs
| Key | Type | Required | Notes |
|---|---|---|---|
| `mode` | string | yes | Skips when `brd_only` |
| `live_url` | string | yes (live modes) | Deployed agent URL (API base, endpoint, or chat page) |
| `test_cases` | array | yes | From AgentTestGenerationAgent. Each must carry its DB `id` |
| `agent_profile` | object | yes | `interface` drives endpoint discovery; purpose drives judging |
| `on_test_update` | callable | no | `(test_id, fields)`, called as replies and verdicts arrive (camelCase DB fields) |
| `emit` | callable | no | Progress log |

## Outputs
`live_reachable`, `transport` (`http` \| `web_ui`), `connection_detail`, `live_error`, and
`execution_results`: `[{id, code, status: passed|failed|skipped, judge_score, judge_reasoning, duration_ms,
actual_output, error_summary, transport_error}]`.

## Behaviour
1. **Connect** (`tools/agent_eval/live_client.py`)
   - An HTTP JSON endpoint is tried first. Routes declared in the agent profile come first (with their example body and
     input/output field paths), then ~20 common routes (`/chat`, `/invoke`, `/v1/chat/completions` …) with
     ~10 body shapes. FastAPI 422 errors are parsed to learn the expected field name.
   - If no endpoint answers and the URL serves HTML, Playwright drives the chat box: Streamlit, Gradio or a
     generic textarea/input. When the profile says `web_chat_ui`, the order is reversed.
2. **Send**: HTTP runs 4 requests in parallel with a 90 s timeout each. The browser runs tests one at a time and reloads the
   page per test so conversations don't leak into each other.
3. **Judge**: Gemini grades replies in batches of 6 against the expected behaviour and pass criteria. A test passes
   when verdict = pass **and** score ≥ 70. Transport failures are `failed` with score 0 and are not judged.

## Failure mode
**Non-blocking.** Connection problems return `status: partial`, mark every test `not_executed`, and set `live_status`:
- `unreachable`: the URL doesn't respond (DNS/connection failure, timeout, 5xx). The deployment is down, so scoring
  gives 0 for the execution-based parts and adds a critical defect.
- `no_interface`: the URL responds but offers no chat box or message API, e.g. the marketing site or docs of a
  desktop/CLI agent. The run is scored like BRD-only (code review) with a warning recommendation, not a defect.
  Chat-box detection ignores read-only, disabled and search inputs, so decorative product mock-ups aren't mistaken for a chat UI.

A failed judge call marks only that batch `skipped`.
