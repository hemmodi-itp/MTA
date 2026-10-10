"""Phase 0.3 — LLM token-usage recorder (connectors/llm/usage.py) and the Gemini hook."""

import json
from types import SimpleNamespace

import pytest

from connectors.llm import usage

pytestmark = pytest.mark.mta


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    usage.reset()
    monkeypatch.delenv(usage.ENV_LOG, raising=False)
    yield
    usage.reset()


def test_totals_and_cache_hits():
    usage.record("gemini", "m1", 100, 20)
    usage.record("gemini", "m1", "7", None)
    usage.record("gemini", "m1", 0, 0, cached=True)
    usage.record("claude", "c1", 5, 6)
    snap = usage.snapshot()
    assert snap["gemini/m1"] == {"calls": 3, "cache_hits": 1, "input_tokens": 107, "output_tokens": 20}
    assert snap["claude/c1"]["output_tokens"] == 6


def test_jsonl_sink_and_summary(tmp_path, monkeypatch):
    log = tmp_path / "usage" / "run.jsonl"
    monkeypatch.setenv(usage.ENV_LOG, str(log))
    usage.record("gemini", "m", 10, 2, source="Gemini JSON call")
    usage.record("gemini", "m", 0, 0, cached=True)
    lines = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()]
    assert lines[0]["source"] == "Gemini JSON call" and lines[1]["cached"] is True
    log.open("a", encoding="utf-8").write("not json\n")
    assert usage.summarize_log(str(log)) == {"gemini/m": {"calls": 2, "cache_hits": 1, "input_tokens": 10, "output_tokens": 2}}
    assert usage.summarize_log(str(tmp_path / "missing.jsonl")) == {}


def test_record_gemini_counts_thinking_tokens_as_output():
    usage.record_gemini("g", SimpleNamespace(prompt_token_count=50, candidates_token_count=10, thoughts_token_count=5))
    usage.record_gemini("g", {"prompt_token_count": 1, "candidates_token_count": 2})
    usage.record_gemini("g", None)
    assert usage.snapshot()["gemini/g"] == {"calls": 3, "cache_hits": 0, "input_tokens": 51, "output_tokens": 17}


def test_gemini_stream_records_last_usage_metadata():
    from connectors.llm.gemini import GeminiConnector

    conn = GeminiConnector.__new__(GeminiConnector)
    conn.model = "gemini-x"
    conn.deadline_s = 60
    conn.max_output_tokens = 1000
    chunks = [
        SimpleNamespace(text='{"a"', usage_metadata=None, candidates=[], prompt_feedback=None),
        SimpleNamespace(text=": 1}", candidates=[SimpleNamespace(finish_reason="STOP")], prompt_feedback=None,
                        usage_metadata=SimpleNamespace(prompt_token_count=30, candidates_token_count=4,
                                                       thoughts_token_count=0)),
    ]
    import time

    assert conn._stream_text(iter(chunks), time.monotonic() + 60, "test") == '{"a": 1}'
    assert usage.snapshot()["gemini/gemini-x"]["input_tokens"] == 30


def test_unwritable_sink_never_raises(monkeypatch, tmp_path):
    monkeypatch.setenv(usage.ENV_LOG, str(tmp_path))  # a directory, not a file
    usage.record("gemini", "m", 1, 1)
    assert usage.snapshot()["gemini/m"]["calls"] == 1
