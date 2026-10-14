"""
hosts.py — host allow-list parsing and matching for the P0 safety rails.

Pure functions, no I/O. An allow-list entry may be a bare host ("example.com"),
a host with port ("127.0.0.1:8765"), a wildcard suffix ("*.example.com", which
matches sub-domains but not the apex) or a full URL (its host[:port] is used).
"""

from typing import Iterable, List, Optional, Tuple
from urllib.parse import urlsplit

# Schemes a browser can be sent to without leaving the allow-list question open.
_NEUTRAL_SCHEMES = {"about", "data", "blob", "chrome-error"}   # chrome-error: the browser's failed-load page
_WEB_SCHEMES = {"http", "https"}


def parse_host_entry(entry: str) -> Optional[Tuple[str, Optional[int]]]:
    """'Example.com:8080' / 'https://x.y/z' / '*.x.y' -> (host_lower, port|None)."""
    if not isinstance(entry, str):
        return None
    text = entry.strip()
    if not text:
        return None
    if "://" not in text:
        text = "//" + text  # let urlsplit treat it as a netloc
    try:
        parts = urlsplit(text)
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError:
        return None
    if not host:
        return None
    return host, port


def host_of(url: str) -> Optional[str]:
    """Hostname (lower-case) of an absolute http(s) URL, else None."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme.lower() not in _WEB_SCHEMES:
        return None
    return (parts.hostname or "").lower() or None


def is_absolute_web_url(url: str) -> bool:
    return host_of(url) is not None


def host_matches(host: str, port: Optional[int], allowed: Iterable[str]) -> bool:
    host = (host or "").lower()
    for entry in allowed:
        parsed = parse_host_entry(entry)
        if not parsed:
            continue
        a_host, a_port = parsed
        if a_port is not None and port is not None and a_port != port:
            continue
        if a_port is not None and port is None:
            continue
        if a_host.startswith("*."):
            if host.endswith(a_host[1:]) and host != a_host[2:]:
                return True
        elif host == a_host:
            return True
    return False


def url_allowed(url: Optional[str], allowed: Iterable[str]) -> bool:
    """
    True when navigating to *url* stays inside *allowed*.

    Relative URLs (no scheme/host) resolve against the base URL, which is itself
    an allow-listed host, so they are allowed. about:/data:/blob: are neutral.
    Any other scheme (javascript:, file:, ftp:, ...) is refused.
    """
    if url is None:
        return True
    text = str(url).strip()
    if not text:
        return True
    try:
        parts = urlsplit(text)
    except ValueError:
        return False
    scheme = parts.scheme.lower()
    if not scheme and not parts.netloc:
        return True  # relative path / query / fragment
    if scheme in _NEUTRAL_SCHEMES:
        return True
    if scheme and scheme not in _WEB_SCHEMES:
        return False
    if not scheme and parts.netloc:  # protocol-relative //host/path
        text = "https:" + text
        parts = urlsplit(text)
    try:
        port = parts.port
    except ValueError:
        return False
    return host_matches(parts.hostname or "", port, allowed)


def normalize_hosts(entries: Iterable[str]) -> List[str]:
    """De-duplicated, lower-cased host[:port] entries in first-seen order."""
    seen: List[str] = []
    for entry in entries:
        parsed = parse_host_entry(entry)
        if not parsed:
            continue
        host, port = parsed
        value = f"{host}:{port}" if port is not None else host
        if value not in seen:
            seen.append(value)
    return seen
