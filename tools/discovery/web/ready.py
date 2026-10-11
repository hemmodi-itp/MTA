"""ready.py — "has this client-rendered page finished drawing?" (moved from engines/runtime/discovery.py, unchanged)."""

import time
from typing import Any, Dict

RENDER_WAIT_S = 30                 # client-rendered pages: wait until the content has actually rendered

# Cheap per-poll readiness probe: [interactive controls in the main area, text length, busy indicator / wording].
READY_JS = r"""() => {
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const nav = el => !!el.closest('nav,aside,header,[role=navigation],[class*=sidebar i]');
  const controls = [...document.querySelectorAll('input:not([type=hidden]),textarea,select,[contenteditable=true],button,[role=button]')]
    .filter(el => vis(el) && !nav(el)).length;
  const text = (document.body && document.body.innerText) || '';
  const busy = [...document.querySelectorAll('[aria-busy=true],[role=progressbar],[class*=spinner i],[class*=loading i],[class*=skeleton i]')]
    .some(vis) || /^\s*(loading|please wait)/im.test(text);
  const headings = [...document.querySelectorAll('main h1,main h2,h1,h2')].filter(el => vis(el) && !nav(el)).length;
  return [controls, text.length, busy, headings];
}"""


def wait_for_render(page, max_s: float = RENDER_WAIT_S) -> Dict[str, Any]:
    """Wait until a client-rendered page shows its content: no busy indicator and the main area's controls / text
    unchanged across two polls. Pages that look empty (no controls, no headings) keep being polled until max_s,
    because SPAs fill the main area only after their API calls return (slow on a cold backend)."""
    t0 = time.monotonic()
    last, stable = None, 0
    probe = [0, 0, True, 0]
    while time.monotonic() - t0 < max_s:
        try:
            probe = page.evaluate(READY_JS)
        except Exception:
            probe = [0, 0, True, 0]
        controls, length, busy, headings = probe
        key = (controls, length // 50)
        stable = stable + 1 if key == last and not busy else 0
        last = key
        looks_empty = controls == 0 and headings == 0
        if stable >= 2 and (not looks_empty or time.monotonic() - t0 > max_s / 2):
            break
        page.wait_for_timeout(1_500)
    return {"waited_s": round(time.monotonic() - t0, 1), "controls": probe[0], "busy": bool(probe[2])}
