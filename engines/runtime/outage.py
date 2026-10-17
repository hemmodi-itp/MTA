"""
outage.py — telling "the live app could not be reached" apart from "the app did the wrong thing".

    UNREACHABLE.search(error)    the browser never got an answer: connection refused / timed out / reset, DNS, the
                                 page's own fetch failed, or the host's gateway answered 502/503/504 (cold start,
                                 restarting container). Says nothing about any requirement.
    SERVER_ERROR.search(error)   the app answered with a server error (e.g. "Request failed (500)"): an app defect,
                                 unless it only happens while MTA runs tests in parallel.
    RATE_LIMITED.search(error)   the app's upstream refused for quota ("429 RESOURCE_EXHAUSTED" from its LLM provider):
                                 the deployment ran out of capacity; says nothing about the requirement under test.
    wait_until_up(url, ...)      polls the live URL until it answers again (any status below 500).

Used by the Playwright Executor (pause and retry instead of burning through the remaining tests during an outage)
and the Pass/Fail Engine (an unreachable app is inconclusive, never a refuted criterion).
"""

import re
import time
import urllib.error
import urllib.request
from typing import Optional

UNREACHABLE = re.compile(r"net::ERR_(?!ABORTED)|\bE(CONNREFUSED|CONNRESET|NOTFOUND|TIMEDOUT)\b|\bfailed to fetch\b|"
                         r"networkerror when attempting to fetch|\bHTTP 50[234] opening\b", re.I)
SERVER_ERROR = re.compile(r"\b(request failed|status|error|HTTP)\W{0,3}\(?5\d\d\b|\binternal server error\b|"
                          r"\b5\d\d\b \(?(internal|bad gateway|service unavailable)", re.I)
# the app's upstream (usually its LLM provider) refused for quota / rate: the deployment's capacity, not the feature
RATE_LIMITED = re.compile(r"\b429\b|resource[_ ]exhausted|\brate[ -]?limit(ed|s)?\b|\bquota\b.{0,40}\b(exceeded|exhausted)\b|"
                          r"too many requests", re.I)
RECOVERY_WAIT_S = 300
RATE_LIMIT_COOL_DOWN_S = 90  # per-minute LLM quotas refill within a minute
POLL_EVERY_S = 10


def wait_until_up(url: str, max_wait_s: int = RECOVERY_WAIT_S, cancel_event=None) -> Optional[float]:
    """Seconds until `url` answered again (0 if it already does), or None if it stayed down for `max_wait_s`."""
    t0 = time.monotonic()
    while True:
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                if r.status < 500:
                    return time.monotonic() - t0
        except urllib.error.HTTPError as e:
            if e.code < 500:
                return time.monotonic() - t0
        except Exception:
            pass
        if time.monotonic() - t0 > max_wait_s or (cancel_event is not None and cancel_event.is_set()):
            return None
        time.sleep(POLL_EVERY_S)
