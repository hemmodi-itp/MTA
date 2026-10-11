"""
urls.py — route templating.

normalise_route is Agent-Eval's original rule (moved from engines/runtime/discovery.py,
unchanged): it only templates segments that look like *record ids* — 3+ digits,
hex/uuid with a digit, long tokens. template_path (deep discovery) also templates
short numeric ids and UUIDs, so /products/3 and /products/42 are one page template.
"""

import re
import urllib.parse
from typing import Optional

ID_SEGMENT = re.compile(r"^(?=.*\d)[0-9a-f-]{8,}$|^\d{3,}$|^[A-Za-z0-9_-]{20,}$|^(?=(?:.*\d){6})[A-Za-z0-9_.-]{6,}$", re.I)

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_NUMERIC = re.compile(r"^\d+$")


def normalise_route(path: str) -> str:
    """A route template: path segments that look like record ids (numbers, hex/uuid, dated or long tokens) → {id}."""
    return "/".join("{id}" if seg and ID_SEGMENT.match(seg) else seg for seg in (path or "/").split("/")) or "/"


def _segment_template(seg: str) -> str:
    if not seg:
        return seg
    if _NUMERIC.match(seg) or _UUID.match(seg) or ID_SEGMENT.match(seg):
        return "{id}"
    return seg


def template_path(path: str) -> str:
    """Deep-discovery path template: any all-digit segment, UUID or id-like token → {id}.
    A trailing slash is dropped (except for the root); plain words are never templated."""
    path = path or "/"
    segs = path.split("/")
    out = "/".join(_segment_template(s) for s in segs)
    if len(out) > 1:
        out = out.rstrip("/")
    return out or "/"


def template_url(url: str) -> str:
    """`/path/{id}` plus sorted query-parameter *names* (values are dropped):
    http://h/products?page=2&q=x → /products?page&q. The host is not part of the template."""
    parts = urllib.parse.urlsplit(url or "")
    tmpl = template_path(parts.path or "/")
    names = sorted({k for k, _ in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)})
    return tmpl + ("?" + "&".join(names) if names else "")


def strip_fragment(url: str) -> str:
    return urllib.parse.urldefrag(url or "")[0]


def same_url(a: Optional[str], b: Optional[str]) -> bool:
    """Same scheme/host/path/query, ignoring a fragment and a trailing slash."""
    if not a or not b:
        return False
    pa, pb = urllib.parse.urlsplit(strip_fragment(a)), urllib.parse.urlsplit(strip_fragment(b))
    return (pa.scheme, pa.netloc, pa.path.rstrip("/") or "/", pa.query) == \
           (pb.scheme, pb.netloc, pb.path.rstrip("/") or "/", pb.query)
