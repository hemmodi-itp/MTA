"""
pdf.py — the Final Evaluation Report (render_html in final.py) as a PDF, for the web app's "Download PDF".

    pdf_bytes = html_to_pdf(report_html)

The HTML is our own, already escaped, but it is laid out offline anyway: JavaScript off and every request the
page makes is aborted (links stay clickable in the PDF; nothing is fetched while rendering). Uses the sync
Playwright API, so call it from a worker thread — never from inside a running asyncio loop.
"""

import threading

from engines.runtime.browser import launch_chromium, new_context

# Chromium is heavy: at most this many renders at once; the rest wait their turn.
_slots = threading.BoundedSemaphore(2)
RENDER_TIMEOUT_MS = 60_000


def html_to_pdf(html: str) -> bytes:
    from playwright.sync_api import sync_playwright

    with _slots, sync_playwright() as pw:
        browser = launch_chromium(pw)
        try:
            ctx = new_context(browser, java_script_enabled=False)
            ctx.route("**/*", lambda route: route.abort())
            page = ctx.new_page()
            page.set_default_timeout(RENDER_TIMEOUT_MS)
            page.set_content(html, wait_until="load")
            page.emulate_media(media="print")
            return page.pdf(format="A4", print_background=True,
                            margin={"top": "14mm", "bottom": "14mm", "left": "12mm", "right": "12mm"})
        finally:
            browser.close()
