"""
gemini.py — Google Gemini via the google-genai SDK (GOOGLE_API_KEY from env).

Every call goes through connectors/llm/call_policy.py:
  * process-wide limiter (max concurrency + requests/minute), held per attempt, never while backing off;
  * retries with full-jitter exponential backoff, honouring Retry-After / RetryInfo; 429 gets a longer budget
    than 5xx; 4xx (invalid argument, auth, unknown model) is never retried;
  * an HTTP timeout on the client plus an overall deadline on streamed calls;
  * finish_reason checks — MAX_TOKENS raises LLMTruncatedError, safety blocks raise LLMBlockedError
    (neither is retried: the identical prompt would fail the same way);
  * an on-disk response cache for successful JSON results and document transcriptions, so re-evaluating
    the same commit / BRD is fast and reproducible;
  * DEBUG log per call (latency, prompt chars, cache hit) and counters exposed by llm_stats().

Environment (optional): AQP_GEMINI_MODEL, AQP_LLM_TIMEOUT_S (HTTP timeout, default 180),
AQP_LLM_DEADLINE_S (overall deadline of one streamed attempt, default 300), AQP_LLM_MAX_OUTPUT_TOKENS
(default 32768), plus the limiter / retry / cache variables documented in call_policy.py.
Model precedence: constructor arg > AQP_GEMINI_MODEL > workflows/settings.yaml `llm.gemini_model` > DEFAULT_MODEL.
"""

import hashlib
import logging
import os
import threading
import time
from typing import Any, Dict, Iterable, List, Optional

from connectors.llm import call_policy
from connectors.llm.base import LLMBlockedError, LLMConnector, LLMTimeoutError, LLMTruncatedError
from connectors.llm.call_policy import llm_stats  # noqa: F401 — re-exported for api /health

_log = logging.getLogger("connectors.gemini")

# One genai.Client per (API key, timeout) per process. Building a client creates an SSL context,
# which on some Windows machines (endpoint security scanning the CA bundle) takes minutes; a shared
# client also reuses keep-alive connections. The sync client is thread-safe.
_clients: Dict[Any, Any] = {}
_clients_lock = threading.Lock()

_BLOCK_REASONS = {"SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "RECITATION", "IMAGE_SAFETY",
                  "IMAGE_PROHIBITED_CONTENT", "IMAGE_RECITATION", "LANGUAGE"}
_settings_model: Optional[str] = None
_settings_loaded = False


def _env_num(name: str, default: float) -> float:
    return call_policy._env_num(name, default)


def configured_model(settings: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """AQP_GEMINI_MODEL, else `llm.gemini_model` from the given settings dict or workflows/settings.yaml."""
    global _settings_model, _settings_loaded
    env = (os.environ.get("AQP_GEMINI_MODEL") or "").strip()
    if env:
        return env
    if settings is not None:
        value = ((settings.get("llm") or {}) if isinstance(settings.get("llm"), dict) else {}).get("gemini_model")
        if value:
            return str(value).strip()
    if not _settings_loaded:
        _settings_loaded = True
        try:
            import yaml
            path = call_policy.REPO_ROOT / "workflows" / "settings.yaml"
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            value = (data.get("llm") or {}).get("gemini_model") if isinstance(data.get("llm"), dict) else None
            _settings_model = str(value).strip() if value else None
        except Exception:
            _settings_model = None
    return _settings_model


def _reason(value: Any) -> str:
    """Enum / string finish or block reason → upper-case name ('' when unset)."""
    if value is None:
        return ""
    return str(getattr(value, "name", None) or getattr(value, "value", None) or value).split(".")[-1].upper()


class GeminiConnector(LLMConnector):
    """Google Gemini via the google-genai SDK. Reads GOOGLE_API_KEY from env."""

    DEFAULT_MODEL = "gemini-3.6-flash"
    JSON_ATTEMPTS = 6  # upper bound; the time budgets in call_policy usually stop earlier

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
        timeout_s: Optional[float] = None,
        use_cache: bool = True,
    ) -> None:
        self.model = model or configured_model() or self.DEFAULT_MODEL
        self._api_key = api_key or os.environ.get("GOOGLE_API_KEY", "")
        self.max_output_tokens = int(max_output_tokens or _env_num("AQP_LLM_MAX_OUTPUT_TOKENS", 32768))
        self.timeout_s = float(timeout_s or _env_num("AQP_LLM_TIMEOUT_S", 180))
        self.deadline_s = max(self.timeout_s, _env_num("AQP_LLM_DEADLINE_S", 300))
        self.use_cache = use_cache

    # ── client ────────────────────────────────────────────────────────────

    def _client(self):
        try:
            from google import genai  # type: ignore
            from google.genai import types  # type: ignore
        except ImportError:
            raise ImportError(
                "google-genai SDK not installed. Run: pip install google-genai"
            )
        key = (self._api_key, int(self.timeout_s * 1000))
        with _clients_lock:
            client = _clients.get(key)
            if client is None:
                client = _clients[key] = genai.Client(
                    api_key=self._api_key, http_options=types.HttpOptions(timeout=int(self.timeout_s * 1000)))
            return client

    def _config(self, **kw):
        from google.genai import types  # type: ignore
        return types.GenerateContentConfig(max_output_tokens=self.max_output_tokens,
                                           **{k: v for k, v in kw.items() if v is not None})

    # ── one guarded call ──────────────────────────────────────────────────

    def _stream_text(self, chunks: Iterable[Any], deadline: float, what: str) -> str:
        """Join streamed chunks, enforcing the overall deadline and checking finish / block reasons."""
        parts: List[str] = []
        finish = block = ""
        try:
            for chunk in chunks:
                text = getattr(chunk, "text", None)
                if text:
                    parts.append(text)
                feedback = getattr(chunk, "prompt_feedback", None)
                block = _reason(getattr(feedback, "block_reason", None)) or block
                for cand in getattr(chunk, "candidates", None) or []:
                    finish = _reason(getattr(cand, "finish_reason", None)) or finish
                if time.monotonic() > deadline:
                    raise LLMTimeoutError(f"{what}: no complete reply within {self.deadline_s:g}s "
                                          f"({sum(map(len, parts)):,} chars received; AQP_LLM_DEADLINE_S).")
        finally:
            close = getattr(chunks, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
        text = "".join(parts)
        self._check_reasons(finish, block, len(text), what)
        return text

    def _check_reasons(self, finish: str, block: str, chars: int, what: str) -> None:
        if block and block != "BLOCKED_REASON_UNSPECIFIED":
            call_policy.record(blocked=1)
            raise LLMBlockedError(f"{what}: Gemini blocked the prompt ({block}).")
        if finish == "MAX_TOKENS":
            call_policy.record(truncated=1)
            raise LLMTruncatedError(
                f"{what}: Gemini stopped at the output limit of {self.max_output_tokens:,} tokens after {chars:,} chars — "
                "the reply is incomplete. Reduce the input/requested output or raise AQP_LLM_MAX_OUTPUT_TOKENS.")
        if finish in _BLOCK_REASONS:
            call_policy.record(blocked=1)
            raise LLMBlockedError(f"{what}: Gemini stopped the reply ({finish}).")

    def _guarded(self, what: str, prompt_chars: int, attempt_fn, cache_key: Optional[str] = None,
                 cacheable=lambda text: bool(text)) -> str:
        cache = call_policy.response_cache() if (self.use_cache and cache_key) else None
        started = time.monotonic()
        if cache is not None:
            hit = cache.get(cache_key)
            if hit is not None:
                call_policy.record(cache_hits=1)
                _log.debug(f"{what}: cache hit ({prompt_chars:,} prompt chars, model {self.model})")
                return hit

        def attempt() -> str:
            # waiting for a slot and generating get separate deadlines, so a queue doesn't eat the reply's time
            with call_policy.limiter().slot(time.monotonic() + self.deadline_s):
                try:
                    return attempt_fn(time.monotonic() + self.deadline_s)
                except Exception as exc:
                    if "Timeout" in type(exc).__name__ and not isinstance(exc, LLMTimeoutError):
                        raise LLMTimeoutError(f"{what}: no reply within {self.timeout_s:g}s "
                                              f"(AQP_LLM_TIMEOUT_S) — {type(exc).__name__}") from exc
                    raise

        call_policy.record(calls=1, prompt_chars=prompt_chars)
        try:
            text = call_policy.retry_call(attempt, what=what, max_attempts=self.JSON_ATTEMPTS)
        except Exception:
            call_policy.record(failures=1, total_latency_s=time.monotonic() - started)
            raise
        latency = time.monotonic() - started
        call_policy.record(total_latency_s=latency)
        _log.debug(f"{what}: {latency:.1f}s, {prompt_chars:,} prompt chars, {len(text or ''):,} reply chars, "
                   f"model {self.model}, cache miss")
        if cache is not None and cacheable(text):
            cache.put(cache_key, text, {"model": self.model, "what": what})
        return text

    # ── public API (signatures unchanged) ─────────────────────────────────

    def generate(self, prompt: str) -> str:
        client = self._client()

        def attempt(deadline: float) -> str:
            response = client.models.generate_content(model=self.model, contents=prompt, config=self._config())
            block = _reason(getattr(getattr(response, "prompt_feedback", None), "block_reason", None))
            cands = getattr(response, "candidates", None) or []
            finish = _reason(getattr(cands[0], "finish_reason", None)) if cands else ""
            text = response.text or ""
            self._check_reasons(finish, block, len(text), "Gemini generate")
            return text

        return self._guarded("Gemini generate", len(prompt), attempt)

    def transcribe_document(self, data: bytes, mime_type: str, instruction: str) -> str:
        """Multimodal read of a document (e.g. a PDF with no text layer) → text.

        Gemini renders the pages itself, so scanned or outlined-font PDFs that
        pdfplumber reads as empty still come back as text. Successful transcriptions are cached
        by document hash, so re-evaluating the same BRD doesn't pay for it again.
        """
        from google.genai import types  # type: ignore

        client = self._client()
        key = call_policy.ResponseCache.key("transcribe", self.model, hashlib.sha256(data).hexdigest(),
                                            mime_type, instruction)

        def attempt(deadline: float) -> str:
            stream = client.models.generate_content_stream(
                model=self.model, contents=[types.Part.from_bytes(data=data, mime_type=mime_type), instruction],
                config=self._config())
            return self._stream_text(stream, deadline, "Gemini document transcription")

        return self._guarded("Gemini document transcription", len(instruction) + len(data), attempt, cache_key=key,
                             cacheable=lambda text: len((text or "").strip()) >= 200)

    def generate_json(self, prompt: str, schema: Optional[Dict[str, Any]] = None,
                      temperature: Optional[float] = None) -> str:
        """JSON-only response, streamed, guarded (limiter, retries, deadline, finish-reason checks, cache).

        schema — optional JSON Schema; Gemini's structured output then guarantees
        the reply parses and matches it (plain JSON mode can still emit a stray
        syntax error on long outputs). Streaming keeps bytes flowing on long
        generations so intermediaries don't drop the connection as idle.
        Only replies that parse as JSON are cached.
        """
        from tools.shared.llm_response_validator import parse_llm_json

        client = self._client()
        key = call_policy.ResponseCache.key("json", self.model, temperature, schema, self.max_output_tokens, prompt)
        sent = {"schema": _relaxed_schema(schema) if schema and _schema_id(schema) in _relaxed_ids else schema}

        def attempt(deadline: float) -> str:
            config = self._config(response_mime_type="application/json", response_json_schema=sent["schema"] or None,
                                  temperature=temperature)
            stream = client.models.generate_content_stream(model=self.model, contents=prompt, config=config)
            return self._stream_text(stream, deadline, "Gemini JSON call")

        def parses(text: str) -> bool:
            try:
                parse_llm_json(text or "")
                return True
            except ValueError:
                return False

        try:
            return self._guarded("Gemini JSON call", len(prompt), attempt, cache_key=key, cacheable=parses)
        except Exception as exc:
            # The API rejects some JSON-Schema bounds (maxItems / maxLength / minimum / maximum) on some models or
            # schema sizes with a bare 400 INVALID_ARGUMENT. Re-send once without those bounds rather than fail the
            # step; the bounds are a safety net, the shape is what matters. Remembered per schema for the process.
            if not schema or sent["schema"] is not schema or not _invalid_argument(exc):
                raise
            _log.warning("Gemini rejected the response schema (400 INVALID_ARGUMENT) — retrying without "
                         "maxItems/maxLength/minimum/maximum bounds for this schema.")
            _relaxed_ids.add(_schema_id(schema))
            sent["schema"] = _relaxed_schema(schema)
            return self._guarded("Gemini JSON call", len(prompt), attempt, cache_key=key, cacheable=parses)


_BOUND_KEYS = {"maxItems", "minItems", "maxLength", "minLength", "minimum", "maximum"}
_relaxed_ids: set = set()


def _schema_id(schema: Dict[str, Any]) -> str:
    return call_policy.ResponseCache.key("schema", schema)


def _relaxed_schema(node: Any) -> Any:
    """The schema without size / range bounds (shape, types, enums and required fields kept)."""
    if isinstance(node, dict):
        return {k: _relaxed_schema(v) for k, v in node.items() if k not in _BOUND_KEYS}
    if isinstance(node, list):
        return [_relaxed_schema(v) for v in node]
    return node


def _invalid_argument(exc: BaseException) -> bool:
    return call_policy._code(exc) == 400 or str(getattr(exc, "status", "") or "").upper() == "INVALID_ARGUMENT"
