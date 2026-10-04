"""
call_policy.py — process-wide guard rails for LLM calls: rate limiting, retries, response cache, metrics.

    limiter().slot(deadline)          context manager: max-concurrency semaphore + requests/minute token bucket
    retry_call(fn, what)              exponential backoff with full jitter; honours Retry-After / RetryInfo;
                                      longer budget for 429 / RESOURCE_EXHAUSTED than for 5xx; never retries 4xx
    response_cache()                  on-disk cache of successful results (sha256 key, TTL, size-bounded LRU)
    llm_stats()                       process counters for the service /health endpoint

Environment (all optional):
    AQP_LLM_CONCURRENCY      max concurrent LLM calls in this process          (default 6)
    AQP_LLM_RPM              max LLM requests per minute in this process       (default 120)
    AQP_LLM_RETRY_BUDGET_S   total time a transient (5xx / network) failure may be retried for   (default 45)
    AQP_LLM_RATE_BUDGET_S    total time a 429 / RESOURCE_EXHAUSTED failure may be retried for    (default 90)
    AQP_LLM_CACHE            0 disables the response cache                      (default on)
    AQP_LLM_CACHE_DIR        cache directory                                     (default <repo>/.aqp_cache/llm)
    AQP_LLM_CACHE_TTL_DAYS   entry lifetime                                      (default 14)
    AQP_LLM_CACHE_MAX_MB     size bound; least-recently-used entries go first   (default 256)
"""

import contextlib
import email.utils
import hashlib
import json
import logging
import os
import random
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from connectors.llm.base import LLMBlockedError, LLMTimeoutError, LLMTruncatedError

_log = logging.getLogger("connectors.llm.policy")
REPO_ROOT = Path(__file__).resolve().parents[2]

# Patched in unit tests.
_sleep = time.sleep
_now = time.monotonic


def _env_num(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, "") or default)
        return value if value > 0 else default
    except ValueError:
        return default


# ── metrics ──────────────────────────────────────────────────────────────────

_stats_lock = threading.Lock()
_STATS: Dict[str, float] = {}


def _reset_stats() -> None:
    with _stats_lock:
        _STATS.clear()
        _STATS.update(calls=0, failures=0, cache_hits=0, retries=0, rate_limited=0, timeouts=0,
                      truncated=0, blocked=0, total_latency_s=0.0, prompt_chars=0)


_reset_stats()


def record(**inc: float) -> None:
    with _stats_lock:
        for k, v in inc.items():
            _STATS[k] = _STATS.get(k, 0) + v


def llm_stats() -> Dict[str, Any]:
    """Process-wide LLM counters + effective configuration (safe to expose on /health: no secrets)."""
    with _stats_lock:
        s = dict(_STATS)
    calls = s.get("calls") or 0
    s["total_latency_s"] = round(s.get("total_latency_s", 0.0), 2)
    s["avg_latency_s"] = round(s["total_latency_s"] / calls, 2) if calls else None
    lim = limiter()
    s["limits"] = {"concurrency": lim.concurrency, "rpm": lim.rpm, "in_flight": lim.in_flight}
    cache = response_cache()
    s["cache"] = {"enabled": cache.enabled, "ttl_days": round(cache.ttl_s / 86400, 1),
                  "max_mb": round(cache.max_bytes / 2**20)}
    return s


# ── rate limiting ────────────────────────────────────────────────────────────

class RateLimiter:
    """Max-concurrency semaphore + token bucket (rpm requests/minute, burst = concurrency). Thread-safe."""

    def __init__(self, concurrency: int, rpm: float) -> None:
        self.concurrency = max(1, int(concurrency))
        self.rpm = max(1.0, float(rpm))
        self._sem = threading.BoundedSemaphore(self.concurrency)
        self._lock = threading.Lock()
        self._capacity = float(min(self.concurrency, self.rpm))
        self._tokens = self._capacity
        self._stamp = _now()
        self.in_flight = 0

    def _take_token(self, deadline: Optional[float]) -> None:
        rate = self.rpm / 60.0
        while True:
            with self._lock:
                now = _now()
                self._tokens = min(self._capacity, self._tokens + (now - self._stamp) * rate)
                self._stamp = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) / rate
            if deadline is not None and _now() + wait > deadline:
                raise LLMTimeoutError("LLM call timed out waiting for the requests-per-minute limit "
                                      f"(AQP_LLM_RPM={self.rpm:g}).")
            _sleep(min(wait, 5.0))

    @contextlib.contextmanager
    def slot(self, deadline: Optional[float] = None):
        timeout = None if deadline is None else max(0.0, deadline - _now())
        if not self._sem.acquire(timeout=timeout):
            raise LLMTimeoutError("LLM call timed out waiting for a free slot "
                                  f"(AQP_LLM_CONCURRENCY={self.concurrency}).")
        try:
            self._take_token(deadline)
            with self._lock:
                self.in_flight += 1
            try:
                yield
            finally:
                with self._lock:
                    self.in_flight -= 1
        finally:
            self._sem.release()


_limiter: Optional[RateLimiter] = None
_limiter_lock = threading.Lock()


def limiter() -> RateLimiter:
    global _limiter
    with _limiter_lock:
        if _limiter is None:
            _limiter = RateLimiter(int(_env_num("AQP_LLM_CONCURRENCY", 6)), _env_num("AQP_LLM_RPM", 120))
        return _limiter


def set_limiter(lim: Optional[RateLimiter]) -> None:
    """Replace the process limiter (tests; None = rebuild from env on next use)."""
    global _limiter
    with _limiter_lock:
        _limiter = lim


# ── retries ──────────────────────────────────────────────────────────────────

_TRANSIENT_NAMES = {
    "RemoteProtocolError", "ConnectError", "ReadError", "ReadTimeout", "ConnectTimeout", "WriteError",
    "WriteTimeout", "PoolTimeout", "TimeoutException", "ServerError", "ConnectionError", "ConnectionResetError",
    "TimeoutError", "LLMTimeoutError", "IncompleteRead",
}
_RATE_STATUSES = {"RESOURCE_EXHAUSTED"}
_TRANSIENT_STATUSES = {"UNAVAILABLE", "INTERNAL", "DEADLINE_EXCEEDED", "ABORTED"}


def _code(exc: BaseException) -> Optional[int]:
    code = getattr(exc, "code", None)
    if not isinstance(code, int):
        code = getattr(exc, "status_code", None)
    return code if isinstance(code, int) else None


def classify(exc: BaseException) -> str:
    """'rate' (429), 'transient' (5xx / network / timeout) or 'fatal' (4xx, invalid argument, truncation, safety)."""
    if isinstance(exc, (LLMTruncatedError, LLMBlockedError)):
        return "fatal"
    code, status = _code(exc), str(getattr(exc, "status", "") or "").upper()
    if code == 429 or status in _RATE_STATUSES:
        return "rate"
    if code is not None and (code in (408,) or 500 <= code < 600) or status in _TRANSIENT_STATUSES:
        return "transient"
    if code is not None and 400 <= code < 500:
        return "fatal"  # 400 INVALID_ARGUMENT, 401/403 auth, 404 model — re-sending can't help
    if isinstance(exc, (TimeoutError, ConnectionError)) or type(exc).__name__ in _TRANSIENT_NAMES:
        return "transient"
    return "fatal"


def _parse_seconds(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    m = re.fullmatch(r"(\d+(?:\.\d+)?)s?", text)
    if m:
        return float(m.group(1))
    try:  # HTTP-date form of Retry-After
        when = email.utils.parsedate_to_datetime(text)
        return max(0.0, when.timestamp() - time.time())
    except (TypeError, ValueError, IndexError):
        return None


def retry_after(exc: BaseException) -> Optional[float]:
    """Server-suggested wait: the Retry-After header, else a google.rpc.RetryInfo retryDelay in the error body."""
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if headers is not None:
        try:
            hit = _parse_seconds(headers.get("retry-after") or headers.get("Retry-After"))
            if hit is not None:
                return hit
        except Exception:
            pass
    details = getattr(exc, "details", None)
    blob = details if isinstance(details, (dict, list)) else None
    if blob is not None:
        for item in _walk(blob):
            if isinstance(item, dict) and "RetryInfo" in str(item.get("@type", "")):
                hit = _parse_seconds(item.get("retryDelay"))
                if hit is not None:
                    return hit
    m = re.search(r"retry(?:Delay| in)['\"]?\s*[:=]?\s*['\"]?(\d+(?:\.\d+)?)s", str(exc), re.I)
    return float(m.group(1)) if m else None


def _walk(node: Any):
    yield node
    if isinstance(node, dict):
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def retry_call(fn: Callable[[], Any], what: str = "LLM call", max_attempts: int = 6,
               base_delay: float = 2.0, max_delay: float = 30.0) -> Any:
    """Run fn(), retrying transient and rate-limit failures within a time budget; re-raise everything else."""
    started = _now()
    transient_budget = _env_num("AQP_LLM_RETRY_BUDGET_S", 45)
    rate_budget = _env_num("AQP_LLM_RATE_BUDGET_S", 90)
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as exc:
            kind = classify(exc)
            if isinstance(exc, LLMTimeoutError):
                record(timeouts=1)
            if kind == "rate":
                record(rate_limited=1)
            if kind == "fatal" or attempt == max_attempts - 1:
                raise
            hinted = retry_after(exc)
            # full jitter; rate limits never retry sooner than 1 s
            delay = hinted if hinted is not None else random.uniform(0, min(max_delay, base_delay * 2 ** attempt))
            if kind == "rate":
                delay = max(delay, 1.0)
            budget = rate_budget if kind == "rate" else transient_budget
            if _now() - started + delay > budget:
                _log.warning(f"{what} failed ({type(exc).__name__}) — retry budget of {budget:g}s exhausted")
                raise
            record(retries=1)
            _log.warning(f"{what} failed ({type(exc).__name__}: {str(exc)[:200]}) — retry {attempt + 1} in {delay:.1f}s")
            _sleep(delay)
    raise RuntimeError("unreachable")  # pragma: no cover


# ── response cache ───────────────────────────────────────────────────────────

class ResponseCache:
    """On-disk cache: one JSON file per key, atomic writes, TTL, size-bounded LRU (mtime = last use)."""

    def __init__(self, directory: Path, ttl_s: float, max_bytes: int, enabled: bool = True) -> None:
        self.dir = Path(directory)
        self.ttl_s = ttl_s
        self.max_bytes = max_bytes
        self.enabled = enabled
        self._lock = threading.Lock()
        self._writes = 0

    @staticmethod
    def key(*parts: Any) -> str:
        blob = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def _path(self, key: str) -> Path:
        return self.dir / key[:2] / f"{key}.json"

    def get(self, key: str) -> Optional[str]:
        if not self.enabled:
            return None
        path = self._path(key)
        try:
            st = path.stat()
            if time.time() - st.st_mtime > self.ttl_s:
                path.unlink(missing_ok=True)
                return None
            value = json.loads(path.read_text(encoding="utf-8")).get("value")
            os.utime(path)  # LRU: touch on use
            return value if isinstance(value, str) else None
        except (OSError, ValueError):
            return None

    def put(self, key: str, value: str, meta: Optional[Dict[str, Any]] = None) -> None:
        if not self.enabled or not isinstance(value, str):
            return
        path = self._path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
            tmp.write_text(json.dumps({"value": value, "meta": meta or {}, "stored_at": time.time()},
                                      ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)
        except OSError as exc:
            _log.debug(f"LLM cache write failed: {exc}")
            return
        with self._lock:
            self._writes += 1
            due = self._writes % 25 == 1
        if due:
            self.cleanup()

    def cleanup(self) -> None:
        """Drop expired entries, then least-recently-used ones until under max_bytes."""
        try:
            entries = []
            for p in self.dir.glob("*/*.json"):
                try:
                    st = p.stat()
                except OSError:
                    continue
                if time.time() - st.st_mtime > self.ttl_s:
                    p.unlink(missing_ok=True)
                else:
                    entries.append((st.st_mtime, st.st_size, p))
            total = sum(s for _, s, _ in entries)
            for _, size, p in sorted(entries):
                if total <= self.max_bytes:
                    break
                p.unlink(missing_ok=True)
                total -= size
            for p in self.dir.glob("*/*.tmp"):  # leftovers from a crash mid-write
                if time.time() - p.stat().st_mtime > 3600:
                    p.unlink(missing_ok=True)
        except OSError as exc:
            _log.debug(f"LLM cache cleanup failed: {exc}")


_cache: Optional[ResponseCache] = None
_cache_lock = threading.Lock()


def response_cache() -> ResponseCache:
    global _cache
    with _cache_lock:
        if _cache is None:
            enabled = os.environ.get("AQP_LLM_CACHE", "1").strip().lower() not in ("0", "false", "no", "off")
            directory = Path(os.environ.get("AQP_LLM_CACHE_DIR") or REPO_ROOT / ".aqp_cache" / "llm")
            _cache = ResponseCache(directory, _env_num("AQP_LLM_CACHE_TTL_DAYS", 14) * 86400,
                                   int(_env_num("AQP_LLM_CACHE_MAX_MB", 256) * 2**20), enabled)
        return _cache


def set_response_cache(cache: Optional[ResponseCache]) -> None:
    """Replace the process cache (tests; None = rebuild from env on next use)."""
    global _cache
    with _cache_lock:
        _cache = cache
