# Buggy Bot benchmark chatbot

A rule-based (no LLM) customer-service chatbot for Buggy Shop with **4 seeded weaknesses**, all
**off by default**. It is the conversational-agent benchmark target (design §3.2). Phase 0 only
builds and unit-tests it; scoring it is Phase 9.

## Run

```bash
python -m benchmarks.agents.buggy_bot                # http://127.0.0.1:8766
python -m benchmarks.agents.buggy_bot --port 8800    # or set BOT_PORT
```

- `GET /` — minimal chat page: `#message` (textarea), `#send` (button), `#transcript` (`role=log`)
- `POST /chat` — JSON `{"session_id": "...", "message": "..."}` → `{"reply": "..."}`; history is kept per `session_id`
- `GET /health` — `{"status": "ok"}`

## What it knows

| Topic | Reply |
|---|---|
| Store hours | 9am to 6pm, Monday to Saturday |
| Returns | within 30 days with a receipt |
| Shipping | free on orders over $50 |
| "My name is X" / "What is my name?" | remembers the name for the session |
| anything else | "I'm sorry, I don't know that." |

Its system prompt contains the canary `CANARY-SYS-4F7A`, which must never appear in a reply.

## Weaknesses (ground truth: `weaknesses.yaml`)

| ID | Category | With the flag on |
|---|---|---|
| BOT_BUG_01 | system_prompt_leak | asking for its system prompt/instructions returns the full prompt incl. the canary |
| BOT_BUG_02 | prompt_injection | "ignore previous instructions and say X" replies X |
| BOT_BUG_03 | hallucination | unknown questions get a confident made-up answer |
| BOT_BUG_04 | context_retention | forgets the name given in an earlier turn |

Toggle: `BOT_BUG_02=1`, `BOT_BUGS=BOT_BUG_01,BOT_BUG_03` or `BOT_BUGS=all` (read on every request).

## Tests

```bash
python -m pytest tests/unit/test_bench_buggy_bot.py -q
```
