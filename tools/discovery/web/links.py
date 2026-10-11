"""links.py — URLs a crawler must never follow (moved from engines/runtime/discovery.py, unchanged):
static assets, logout / sign-out (would end the session), mailto/tel/javascript, and paths or
query actions that destroy something."""

import re

SKIP_LINK = re.compile(r"\.(png|jpe?g|gif|svg|webp|ico|pdf|zip|docx?|xlsx?|csv|css|js|map)(\?|$)|logout|log-out|sign-?out|"
                       r"mailto:|tel:|javascript:|/(delete|remove|destroy|deactivate|unsubscribe|reset|revoke|cancel)\b|"
                       r"[?&](action|op)=(delete|remove|destroy)", re.I)


def skip_link(url: str) -> bool:
    return bool(SKIP_LINK.search(url or ""))
