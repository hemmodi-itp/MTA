"""GeminiConnector guard rails (connectors/llm/call_policy.py) with a fake google-genai client: timeouts,
429 backoff honouring Retry-After / RetryInfo, no retry on 400, cache hit/miss/disable, truncation and safety
errors, limiter concurrency and requests/minute, model configuration, fence-safe JSON parsing."""

import threading
import time
from types import SimpleNamespace

import pytest

from connectors.llm import call_policy
from connectors.llm.base import LLMBlockedError, LLMTimeoutError, LLMTruncatedError
from connectors.llm.call_policy import RateLimiter, ResponseCache
from connectors.llm.gemini import GeminiConnector
from tools.agent_eval.llm_json import generate_json
from tools.shared.llm_response_validator import parse_llm_json

FENCE = "`" * 3


def chunk(text, finish=None, block=None):
    return SimpleNamespace(text=text, candidates=[SimpleNamespace(finish_reason=finish)] if finish else [],
                           prompt_feedback=SimpleNamespace(block_reason=block) if block else None)


class APIErr(Exception):
    def __init__(self, code, status="", headers=None, details=None):
        super().__init__(f"{code} {status}")
        self.code, self.status, self.details = code, status, details
        self.response = SimpleNamespace(headers=headers or {})


class FakeModels:
    def __init__(self, script):
        self.script = list(script)  # each item: exception to raise, or list of chunks
        self.calls = 0

    def generate_content_stream(self, model, contents, config=None):
        self.calls += 1
        step = self.script.pop(0) if self.script else [chunk('{"ok": true}', "STOP")]
        if isinstance(step, Exception):
            raise step
        return iter(step)

    def generate_content(self, model, contents, config=None):
        self.calls += 1
        step = self.script.pop(0) if self.script else [chunk("hello", "STOP")]
        if isinstance(step, Exception):
            raise step
        c = step[-1]
        return SimpleNamespace(text="".join(x.text for x in step), candidates=c.candidates, prompt_feedback=c.prompt_feedback)


def connector(script, **kw):
    conn = GeminiConnector(model="test-model", api_key="x", **kw)
    fake = SimpleNamespace(models=FakeModels(script))
    conn._client = lambda: fake
    return conn, fake.models


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    slept = []
    monkeypatch.setattr(call_policy, "_sleep", lambda s: slept.append(s))
    call_policy.set_limiter(RateLimiter(6, 100_000))
    call_policy.set_response_cache(ResponseCache(tmp_path / "cache", 3600, 10 * 2**20, enabled=True))
    call_policy._reset_stats()
    yield slept
    call_policy.set_limiter(None)
    call_policy.set_response_cache(None)


# ── retries ──────────────────────────────────────────────────────────────────

def test_429_backoff_honours_retry_after(isolated):
    conn, models = connector([APIErr(429, "RESOURCE_EXHAUSTED", headers={"retry-after": "7"}),
                              [chunk('{"a": 1}', "STOP")]])
    assert conn.generate_json("p") == '{"a": 1}'
    assert models.calls == 2
    assert isolated == [7.0]
    assert call_policy.llm_stats()["rate_limited"] == 1


def test_429_honours_retryinfo_in_error_body(isolated):
    details = {"error": {"details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "3s"}]}}
    conn, _ = connector([APIErr(429, "RESOURCE_EXHAUSTED", details=details), [chunk("{}", "STOP")]])
    conn.generate_json("p")
    assert isolated == [3.0]


def test_429_gives_up_when_rate_budget_exhausted(isolated, monkeypatch):
    monkeypatch.setenv("AQP_LLM_RATE_BUDGET_S", "10")
    conn, models = connector([APIErr(429, headers={"retry-after": "30"})] * 3)
    with pytest.raises(APIErr):
        conn.generate_json("p")
    assert models.calls == 1 and isolated == []


def test_400_is_not_retried(isolated):
    conn, models = connector([APIErr(400, "INVALID_ARGUMENT"), [chunk("{}", "STOP")]])
    with pytest.raises(APIErr):
        conn.generate_json("p")
    assert models.calls == 1 and isolated == []


def test_schema_rejected_is_resent_once_without_bounds(isolated):
    import connectors.llm.gemini as gem
    schema = {"type": "object", "properties": {"x": {"type": "array", "maxItems": 4, "items": {"type": "string",
                                                                                              "maxLength": 9}}}}
    gem._relaxed_ids.discard(gem._schema_id(schema))
    conn, models = connector([APIErr(400, "INVALID_ARGUMENT"), [chunk('{"x": []}', "STOP")]])
    seen = []
    orig = models.generate_content_stream
    models.generate_content_stream = lambda model, contents, config=None: (
        seen.append(config.response_json_schema), orig(model, contents, config))[1]
    assert conn.generate_json("p", schema=schema) == '{"x": []}'
    assert "maxItems" in str(seen[0]) and "maxItems" not in str(seen[1]) and "maxLength" not in str(seen[1])
    assert seen[1]["properties"]["x"]["items"]["type"] == "string"


def test_5xx_retried_with_jitter_within_cap(isolated):
    conn, models = connector([APIErr(503, "UNAVAILABLE"), APIErr(500), [chunk("{}", "STOP")]])
    assert conn.generate_json("p") == "{}"
    assert models.calls == 3
    assert len(isolated) == 2 and all(0 <= s <= 30 for s in isolated)


# ── timeouts ─────────────────────────────────────────────────────────────────

def test_streaming_overall_deadline(monkeypatch):
    monkeypatch.setenv("AQP_LLM_RETRY_BUDGET_S", "0.01")

    def slow():
        for i in range(5):
            time.sleep(0.05)
            yield chunk(f'"{i}"')

    conn, models = connector([slow()])
    conn.deadline_s = 0.03
    with pytest.raises(LLMTimeoutError):
        conn.generate_json("p")
    assert call_policy.llm_stats()["timeouts"] >= 1


def test_http_timeout_becomes_llm_timeout(monkeypatch):
    monkeypatch.setenv("AQP_LLM_RETRY_BUDGET_S", "0.01")
    ReadTimeout = type("ReadTimeout", (Exception,), {})
    conn, _ = connector([ReadTimeout("read timed out")])
    with pytest.raises(LLMTimeoutError):
        conn.generate_json("p")


def test_client_is_built_with_http_timeout(monkeypatch):
    from google import genai
    seen = {}

    class Client:
        def __init__(self, api_key, http_options):
            seen["timeout"] = http_options.timeout

    monkeypatch.setattr(genai, "Client", Client)
    monkeypatch.setattr("connectors.llm.gemini._clients", {})
    GeminiConnector(api_key="k", timeout_s=42)._client()
    assert seen["timeout"] == 42_000


# ── finish reasons ───────────────────────────────────────────────────────────

def test_max_tokens_raises_truncation_and_llm_json_does_not_resend():
    conn, models = connector([[chunk('{"a": "abc'), chunk("", "MAX_TOKENS")]])
    with pytest.raises(LLMTruncatedError):
        generate_json(conn, "p")
    assert models.calls == 1


def test_safety_block_raises_blocked():
    conn, models = connector([[chunk("", "SAFETY")]])
    with pytest.raises(LLMBlockedError):
        conn.generate_json("p")
    conn2, _ = connector([[chunk("", None, block="PROHIBITED_CONTENT")]])
    with pytest.raises(LLMBlockedError):
        conn2.generate_json("p")


def test_parse_error_retried_exactly_once():
    conn, models = connector([[chunk("not json", "STOP")], [chunk("still not", "STOP")], [chunk("{}", "STOP")]])
    with pytest.raises(ValueError):
        generate_json(conn, "p", retries=5)
    assert models.calls == 2


# ── cache ────────────────────────────────────────────────────────────────────

def test_cache_hit_and_miss():
    conn, models = connector([[chunk('{"n": 1}', "STOP")], [chunk('{"n": 2}', "STOP")]])
    assert conn.generate_json("same", schema={"type": "object"}) == '{"n": 1}'
    assert conn.generate_json("same", schema={"type": "object"}) == '{"n": 1}'   # hit
    assert models.calls == 1
    assert conn.generate_json("same", schema={"type": "object"}, temperature=0.0) == '{"n": 2}'  # different key
    assert models.calls == 2
    assert call_policy.llm_stats()["cache_hits"] == 1


def test_unparseable_reply_not_cached():
    conn, models = connector([[chunk("oops", "STOP")], [chunk("{}", "STOP")]])
    conn.generate_json("q")
    assert conn.generate_json("q") == "{}"
    assert models.calls == 2


def test_cache_disabled(tmp_path):
    call_policy.set_response_cache(ResponseCache(tmp_path / "off", 3600, 2**20, enabled=False))
    conn, models = connector([[chunk("{}", "STOP")], [chunk("{}", "STOP")]])
    conn.generate_json("x")
    conn.generate_json("x")
    assert models.calls == 2


def test_cache_env_switch(monkeypatch, tmp_path):
    call_policy.set_response_cache(None)
    monkeypatch.setenv("AQP_LLM_CACHE", "0")
    monkeypatch.setenv("AQP_LLM_CACHE_DIR", str(tmp_path / "c"))
    assert call_policy.response_cache().enabled is False


def test_cache_ttl_and_lru_cleanup(tmp_path):
    cache = ResponseCache(tmp_path / "lru", ttl_s=3600, max_bytes=400)
    keys = [cache.key("k", i) for i in range(6)]
    for i, k in enumerate(keys):
        cache.put(k, "x" * 100)
        p = cache._path(k)
        import os
        os.utime(p, (time.time() - 100 + i, time.time() - 100 + i))
    cache.cleanup()
    left = [k for k in keys if cache._path(k).exists()]
    assert left and len(left) < 6 and keys[-1] in left and keys[0] not in left
    old = cache.key("old")
    cache.put(old, "v")
    import os
    os.utime(cache._path(old), (time.time() - 7200, time.time() - 7200))
    assert cache.get(old) is None


def test_transcription_cached_by_document_hash():
    conn, models = connector([[chunk("T" * 300, "STOP")]])
    assert conn.transcribe_document(b"%PDF", "application/pdf", "do it") == "T" * 300
    assert conn.transcribe_document(b"%PDF", "application/pdf", "do it") == "T" * 300
    assert models.calls == 1


# ── limiter ──────────────────────────────────────────────────────────────────

def test_limiter_caps_concurrency():
    lim = RateLimiter(2, 100_000)
    live, peak, lock = [0], [0], threading.Lock()

    def work():
        with lim.slot():
            with lock:
                live[0] += 1
                peak[0] = max(peak[0], live[0])
            time.sleep(0.03)
            with lock:
                live[0] -= 1

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak[0] == 2


def test_token_bucket_paces_requests(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(call_policy, "_now", lambda: clock[0])
    slept = []

    def fake_sleep(s):
        slept.append(s)
        clock[0] += s

    monkeypatch.setattr(call_policy, "_sleep", fake_sleep)
    lim = RateLimiter(3, 60)  # burst 3, then one per second
    for _ in range(5):
        with lim.slot():
            pass
    assert round(sum(slept), 3) == 2.0


def test_limiter_slot_timeout():
    lim = RateLimiter(1, 100_000)
    with lim.slot():
        with pytest.raises(LLMTimeoutError):
            with lim.slot(deadline=call_policy._now() + 0.01):
                pass


# ── config / stats / parsing ─────────────────────────────────────────────────

def test_model_configuration(monkeypatch):
    from connectors.connector_registry import ConnectorRegistry
    monkeypatch.delenv("AQP_GEMINI_MODEL", raising=False)
    reg = ConnectorRegistry({"connectors": {"llm": "gemini"}, "llm": {"gemini_model": "gemini-from-settings"}})
    assert reg.get_llm().model == "gemini-from-settings"
    monkeypatch.setenv("AQP_GEMINI_MODEL", "gemini-from-env")
    assert reg.get_llm().model == "gemini-from-env"
    assert GeminiConnector().model == "gemini-from-env"
    assert GeminiConnector(model="explicit").model == "explicit"


def test_llm_stats_shape():
    conn, _ = connector([[chunk("{}", "STOP")]])
    conn.generate_json("s")
    stats = call_policy.llm_stats()
    assert stats["calls"] == 1 and stats["failures"] == 0 and stats["avg_latency_s"] is not None
    assert {"concurrency", "rpm"} <= set(stats["limits"]) and "enabled" in stats["cache"]


def test_parse_keeps_inner_fences():
    inner = f"# BRD\\n{FENCE}python\\nprint(1)\\n{FENCE}\\n"
    raw = f'{FENCE}json\n{{"brd_markdown": "{inner}"}}\n{FENCE}'
    assert parse_llm_json(raw)["brd_markdown"] == f"# BRD\n{FENCE}python\nprint(1)\n{FENCE}\n"
    assert parse_llm_json('{"a": 1}') == {"a": 1}
    assert parse_llm_json(f"{FENCE}\n[1, 2]\n{FENCE}") == [1, 2]
