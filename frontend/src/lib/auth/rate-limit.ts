/**
 * In-memory sliding-window rate limiter for the auth actions. Per process: good enough for one Next server; behind
 * several instances it limits per instance (move it to Postgres/Redis then).
 */
const buckets = new Map<string, number[]>();
let lastSweep = 0;

export interface LimitResult {
  ok: boolean;
  /** Seconds until the oldest attempt in the window expires (when blocked). */
  retryAfterSec: number;
}

/** Records one attempt for `key` and says whether it is within `max` attempts per `windowMs`. */
export function hit(key: string, max: number, windowMs: number, now = Date.now()): LimitResult {
  sweep(windowMs, now);
  const recent = (buckets.get(key) ?? []).filter((t) => now - t < windowMs);
  if (recent.length >= max) {
    buckets.set(key, recent);
    return { ok: false, retryAfterSec: Math.max(1, Math.ceil((recent[0] + windowMs - now) / 1000)) };
  }
  recent.push(now);
  buckets.set(key, recent);
  return { ok: true, retryAfterSec: 0 };
}

/** Drop buckets with no attempt inside the window, at most once a minute, so the map can't grow without bound. */
function sweep(windowMs: number, now: number) {
  if (now - lastSweep < 60_000) return;
  lastSweep = now;
  for (const [key, times] of buckets) {
    if (!times.length || now - times[times.length - 1] >= windowMs) buckets.delete(key);
  }
}
