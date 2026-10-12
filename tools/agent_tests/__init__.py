"""
tools/agent_tests — Phase 9: testing AI agents and chatbots (docs/phases/phase-9-design.md).

    python -m tools.agent_tests generate --agent buggy_bot      # spec + catalogs → eval_sets/buggy_bot/*.jsonl
    python -m tools.agent_tests validate --agent buggy_bot
    python -m tools.agent_tests run --agent buggy_bot --url http://127.0.0.1:8766
    python -m tools.agent_tests bench --seed 7                  # every buggy_bot weakness on/off

Layout: models (case record) · spec (agent.yaml) · catalogs (curated red-team payloads) · generators/ (one per
dimension) · checks/ (deterministic oracles) · dataset (load / validate / merge / write) · transport · runner · bench.
"""
