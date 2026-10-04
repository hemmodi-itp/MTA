"""
net_guard.py — outbound-target policy for everything MTA opens on behalf of a user (SSRF protection).

    check_target(url)                -> None or raises BlockedTarget   (validate a user-supplied live URL)
    is_allowed_url(url)              -> bool                            (per-request check, cached DNS)
    install_browser_guard(context)   -> None                            (Playwright: abort requests to blocked hosts)
    same_origin(base, url)           -> bool

A live URL may only point at a public host: http(s), no user:pass@, and every address the name resolves to must be a
public unicast address (no loopback, private, link-local incl. cloud metadata 169.254.169.254, CGNAT, multicast,
unspecified, IPv6 ULA / link-local, IPv4-mapped forms of those). The browser guard re-checks every request the page
makes (redirects, sub-resources, XHR), so a public page cannot pivot the server-side browser into the internal network.

Local development against an app on this machine: set AQP_ALLOW_PRIVATE_TARGETS=1 (never in a shared deployment).
"""

import ipaddress
import os
import socket
import threading
import time
import urllib.parse
from typing import Dict, Optional, Tuple

_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".intranet", ".lan", ".home.arpa")
_DNS_TTL_S = 60
_dns_cache: Dict[str, Tuple[float, bool, str]] = {}
_dns_lock = threading.Lock()


class BlockedTarget(ValueError):
    """The URL points at a host MTA must not contact."""


def private_targets_allowed() -> bool:
    return os.environ.get("AQP_ALLOW_PRIVATE_TARGETS", "").strip().lower() in ("1", "true", "yes")


def _ip_blocked(ip: ipaddress._BaseAddress) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if isinstance(ip, ipaddress.IPv6Address) and ip.sixtofour:
        ip = ip.sixtofour
    return (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved
            or ip.is_unspecified or not ip.is_global
            or (isinstance(ip, ipaddress.IPv4Address) and ip in ipaddress.ip_network("100.64.0.0/10")))


def _host_verdict(host: str) -> Tuple[bool, str]:
    """(allowed, reason) for a hostname or IP literal; DNS answers cached briefly."""
    host = (host or "").strip().strip("[]").rstrip(".").lower()
    if not host:
        return False, "the URL has no host"
    if host == "localhost" or host.endswith(_BLOCKED_SUFFIXES):
        return False, f"{host} is a local or internal host name"
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        return (False, f"{host} is a private or reserved address") if _ip_blocked(literal) else (True, "")
    now = time.monotonic()
    with _dns_lock:
        hit = _dns_cache.get(host)
        if hit and now - hit[0] < _DNS_TTL_S:
            return hit[1], hit[2]
    try:
        infos = socket.getaddrinfo(host, None)
        addrs = {i[4][0].split("%")[0] for i in infos}
        bad = sorted(a for a in addrs if _ip_blocked(ipaddress.ip_address(a)))
        verdict = (False, f"{host} resolves to a private or reserved address ({bad[0]})") if bad else (True, "")
    except socket.gaierror:
        verdict = (False, f"{host} could not be resolved")
    with _dns_lock:
        _dns_cache[host] = (now, verdict[0], verdict[1])
    return verdict


def check_target(url: str) -> None:
    """Raise BlockedTarget unless `url` is an http(s) URL on a public host."""
    parts = urllib.parse.urlsplit((url or "").strip())
    if parts.scheme not in ("http", "https"):
        raise BlockedTarget("only http:// and https:// URLs can be tested")
    if parts.username or parts.password:
        raise BlockedTarget("the URL must not contain a user name or password; use the project's test account")
    if private_targets_allowed():
        return
    ok, reason = _host_verdict(parts.hostname or "")
    if not ok:
        raise BlockedTarget(f"{reason}; MTA only tests publicly reachable apps")


def is_allowed_url(url: str) -> bool:
    parts = urllib.parse.urlsplit(url or "")
    if parts.scheme in ("data", "blob", "about"):
        return True
    if parts.scheme not in ("http", "https", "ws", "wss"):
        return False
    if private_targets_allowed():
        return True
    return _host_verdict(parts.hostname or "")[0]


def install_browser_guard(context, log=None) -> None:
    """Abort every request a Playwright BrowserContext makes to a blocked host (redirects included)."""
    blocked: Dict[str, bool] = {}

    def handler(route):
        url = route.request.url
        if is_allowed_url(url):
            return route.continue_()
        host = urllib.parse.urlsplit(url).hostname or "?"
        if log and host not in blocked:
            blocked[host] = True
            try:
                log(f"Blocked a request to {host}: private or internal addresses are not reachable from MTA.", "warning")
            except TypeError:
                log(f"Blocked a request to {host}: private or internal addresses are not reachable from MTA.")
        return route.abort("blockedbyclient")

    if not private_targets_allowed():
        context.route("**/*", handler)


def same_origin(base: str, url: str) -> bool:
    a, b = urllib.parse.urlsplit(base), urllib.parse.urlsplit(url)
    return (a.scheme, a.hostname, a.port) == (b.scheme, b.hostname, b.port)


def join_same_origin(base: str, path: str) -> Optional[str]:
    """urljoin that refuses to leave the base origin (absolute or scheme-relative paths elsewhere → None)."""
    joined = urllib.parse.urljoin(base, path or "/")
    return joined if same_origin(base, joined) else None
