import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, Page


def _is_browser_closed_error(exc: Exception) -> bool:
    phrases = (
        "target page, context or browser has been closed",
        "connection closed",
        "browser has been closed",
        "page has been closed",
    )
    return any(p in str(exc).lower() for p in phrases)


def write_scan_checkpoint(checkpoint_path: str, url: str, title: str, elements: list) -> None:
    """Atomically dump whatever elements have been collected so far.

    Called periodically during the (potentially minutes-long) element
    collection phase so a caller-side timeout that abandons this thread
    still has real, partial locator data on disk to promote instead of
    nothing — see DiscoveryAgent._promote_dom_checkpoint.
    """
    tmp_path = checkpoint_path + ".tmp"
    doc = {
        "url": url,
        "title": title,
        "elements": elements,
        "element_count": len(elements),
        "partial": True,
    }
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    os.replace(tmp_path, checkpoint_path)


def _resolve_display_name(text: str, aria_label: str, label: str, title: str) -> str:
    """Best available human-readable name for an element — visible inner
    text wins, but icon-only controls (mic/send/menu buttons etc.) have none,
    so this falls back through aria-label, an associated <label>, then the
    title attribute rather than leaving callers with a blank name."""
    return text or aria_label or label or title or ""


def _demote_duplicate_role_candidates(elements: List[Dict[str, Any]]) -> None:
    """Mutates *elements* in place. Two elements can legitimately share the
    same accessible (role, name) pair (e.g. a text "Sign in" button and an
    icon "Sign in" button shown responsively) — a get_by_role locator built
    from just that pair is then ambiguous and fails at runtime with a
    Playwright strict-mode violation, even though each element looked fine
    in isolation during per-element scoring. Re-ranks any such element's
    candidates so a durable, unique alternative (testid/id) or the CSS
    fallback is recommended instead of the ambiguous role locator."""
    role_name_counts: Dict[tuple, int] = {}
    for el in elements:
        role_locator = (el.get("playwright_locators") or {}).get("get_by_role")
        if role_locator:
            pair = (role_locator.get("role"), role_locator.get("name"))
            role_name_counts[pair] = role_name_counts.get(pair, 0) + 1

    for el in elements:
        role_locator = (el.get("playwright_locators") or {}).get("get_by_role")
        if not role_locator:
            continue
        pair = (role_locator.get("role"), role_locator.get("name"))
        match_count = role_name_counts.get(pair, 0)
        if match_count <= 1:
            continue
        candidates = el.get("locator_candidates") or []
        changed = False
        for candidate in candidates:
            if candidate.get("type") == "role":
                candidate["unique"] = False
                candidate["match_count"] = match_count
                candidate["score"] -= 50  # undo the uniqueness bonus it was given
                changed = True
        if changed:
            candidates.sort(key=lambda c: c["score"], reverse=True)
            el["locator_candidates"] = candidates
            if candidates:
                el["recommended_locator"] = candidates[0]


def _same_page(current_url: str, target_url: str) -> bool:
    """True if current_url is already effectively the target page (ignoring
    query string / hash fragment and a trailing slash) — used to skip a
    redundant re-navigation when setup steps (e.g. a login redirect) already
    landed on the scan target."""
    try:
        a, b = urlsplit(current_url), urlsplit(target_url)
    except ValueError:
        return False
    return (a.scheme, a.netloc, a.path.rstrip("/")) == (b.scheme, b.netloc, b.path.rstrip("/"))


class PlaywrightScanner:
    def __init__(self, browser_name: str = "chromium", headless: bool = True):
        self.browser_name = browser_name
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.context = None
        self.page: Optional[Page] = None
        self.logger = logging.getLogger("workflow.playwright")

    def _build_css_selector(self, element_handle: Any) -> str:
        selector = self.page.evaluate(
            "element => {\n"
            "  if (element.id) return '#' + element.id;\n"
            "  let path = '';\n"
            "  while (element && element.nodeType === Node.ELEMENT_NODE) {\n"
            "    let name = element.nodeName.toLowerCase();\n"
            "    let index = 1;\n"
            "    let sibling = element.previousElementSibling;\n"
            "    while (sibling) {\n"
            "      if (sibling.nodeName === element.nodeName) index += 1;\n"
            "      sibling = sibling.previousElementSibling;\n"
            "    }\n"
            "    path = name + (index > 1 ? ':' + 'nth-of-type(' + index + ')' : '') + (path ? '>' + path : '');\n"
            "    if (element.id) break;\n"
            "    element = element.parentElement;\n"
            "  }\n"
            "  return path;\n"
            "}",
            element_handle,
        )
        return selector or ""

    def _get_element_data(self, element_handle: Any) -> Dict[str, Any]:

        attributes = [
            "id",
            "name",
            "role",
            "placeholder",
            "aria-label",
            "aria-labelledby",
            "data-testid",
            "data-test",
            "data-qa",
            "type",
            "value",
            "title",
        ]

        values = {
            attr: element_handle.get_attribute(attr)
            for attr in attributes
        }

        text = ""

        try:
            text = element_handle.inner_text().strip()
        except Exception:
            pass

        label = self._get_associated_label(element_handle)

        visible = False
        enabled = False

        try:
            visible = element_handle.is_visible()
            enabled = element_handle.is_enabled()
        except Exception:
            pass

        semantic_locators = {
            "role": values.get("role"),
            "label": label,
            "placeholder": values.get("placeholder"),
            "aria_label": (
                values.get("aria-label")
                or values.get("aria-labelledby")
            ),
            "title": values.get("title"),
        }

        tag_name = element_handle.evaluate(
            "el => el.tagName.toLowerCase()"
        )

        display_name = _resolve_display_name(
            text, semantic_locators["aria_label"] or "", label, semantic_locators["title"] or ""
        )

        if not semantic_locators["role"]:

            if tag_name == "button":
                semantic_locators["role"] = "button"

            elif tag_name == "a":
                semantic_locators["role"] = "link"

            elif tag_name in ["input", "textarea"]:
                semantic_locators["role"] = "textbox"

            elif tag_name == "select":
                semantic_locators["role"] = "combobox"

        attribute_locators = {
            "testid": (
                values.get("data-testid")
                or values.get("data-test")
                or values.get("data-qa")
            ),
            "id": values.get("id"),
            "name": values.get("name"),
            "type": values.get("type"),
        }

        playwright_locators = {}

        if semantic_locators["role"] and display_name:
            playwright_locators["get_by_role"] = {
                "role": semantic_locators["role"],
                "name": display_name,
            }

        if semantic_locators["label"]:
            playwright_locators["get_by_label"] = {
                "label": semantic_locators["label"],
            }

        if semantic_locators["placeholder"]:
            playwright_locators["get_by_placeholder"] = {
                "placeholder": semantic_locators["placeholder"],
            }

        if text:
            playwright_locators["get_by_text"] = {
                "text": text,
            }

        if attribute_locators["testid"]:
            playwright_locators["get_by_testid"] = {
                "testid": attribute_locators["testid"],
            }

        locator_candidates = self._build_locator_candidates(
            attribute_locators,
            playwright_locators
        )

        locator_candidates = self._rank_locator_candidates(
            locator_candidates
        )

        if locator_candidates:

            recommended_locator = locator_candidates[0]

        else:

            recommended_locator = {
                "type": "css",
                "value": {
                    "css": self._build_css_selector(
                        element_handle
                    )
                },
                "score": 0,
                "unique": True,
                "match_count": 1
            }
        intent_hints = []

        text_lower = display_name.lower()

        if "login" in text_lower:
            intent_hints.append("login")

        if "search" in text_lower:
            intent_hints.append("search")

        if "cart" in text_lower:
            intent_hints.append("add_to_cart")

        if "buy" in text_lower:
            intent_hints.append("purchase")

        if "product" in text_lower:
            intent_hints.append("navigate_products")

        return {

            "display_text": display_name,

            "semantic_locators": semantic_locators,

            "attribute_locators": attribute_locators,

            "playwright_locators": playwright_locators,

            "technical_locators": {
                "css": self._build_css_selector(element_handle),
                "xpath": self._build_xpath_selector(element_handle),
            },

            "recommended_locator": recommended_locator,
            "locator_candidates": locator_candidates,

            "quality": {
                "visible": visible,
                "enabled": enabled,
            },

            "intent_hints": intent_hints,
        }
    

    def _get_associated_label(self, element_handle: Any) -> str:
        try:
            return self.page.evaluate(
                """
                element => {

                    if (element.id) {

                        const label =
                            document.querySelector(
                                `label[for="${element.id}"]`
                            );

                        if (label)
                            return label.innerText.trim();
                    }

                    const parentLabel =
                        element.closest('label');

                    if (parentLabel)
                        return parentLabel.innerText.trim();

                    return '';
                }
                """,
                element_handle,
            )
        except Exception:
            return ""
        

    def _build_xpath_selector(self, element_handle: Any) -> str:
        return self.page.evaluate(
            """
            element => {
                if (element.id)
                    return `//*[@id="${element.id}"]`;

                const getPath = (el) => {
                    if (!el || el.nodeType !== Node.ELEMENT_NODE)
                        return '';

                    let index = 1;
                    let sibling = el.previousElementSibling;

                    while (sibling) {
                        if (sibling.nodeName === el.nodeName)
                            index++;
                        sibling = sibling.previousElementSibling;
                    }

                    return getPath(el.parentElement)
                        + '/'
                        + el.nodeName.toLowerCase()
                        + '[' + index + ']';
                };

                return getPath(element);
            }
            """,
            element_handle,
    )

    

    def launch(self, storage_state_path: Optional[str] = None, auth_config: Optional[dict] = None) -> Page:
        self.playwright = sync_playwright().start()
        self.browser = getattr(self.playwright, self.browser_name).launch(headless=self.headless)
        ctx_kwargs = {}
        if storage_state_path and os.path.exists(storage_state_path):
            ctx_kwargs["storage_state"] = storage_state_path
            self.logger.info(f"  Browser context loading auth state from '{storage_state_path}'")
        self.context = self.browser.new_context(**ctx_kwargs)
        self.page = self.context.new_page()
        if auth_config and auth_config.get("strategy") == "live_login":
            from tools.auth.live_login import perform_login
            self.logger.info("  live_login: executing browser login before scan")
            perform_login(self.page, auth_config)
        return self.page

    def close(self) -> None:
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def _poll_page_ready(self, page: Page, max_wait_s: int, poll_s: float = 3.0) -> bool:
        """Poll document.readyState every poll_s seconds up to max_wait_s. Returns True when ready."""
        elapsed = 0.0
        while elapsed < max_wait_s:
            try:
                state = page.evaluate("document.readyState")
                if state in ("interactive", "complete"):
                    return True
            except Exception:
                pass
            time.sleep(poll_s)
            elapsed += poll_s
        return False

    def _execute_setup_steps(self, page, steps: list) -> None:
        total = len(steps)
        for i, step in enumerate(steps, 1):
            if not isinstance(step, dict):
                self.logger.warning(f"  Setup [{i}/{total}]: skipping non-dict step: {step!r}")
                continue
            action = next(iter(step))
            self.logger.info(f"  Setup [{i}/{total}]: {action} → {step[action]!r}")
            try:
                if action == "goto":
                    page.goto(step["goto"], wait_until="domcontentloaded", timeout=30000)
                    self.logger.info(f"  Setup [{i}/{total}]: navigated to {page.url!r}")
                elif action == "fill":
                    spec = step["fill"]
                    if "value_env" in spec:
                        value = os.environ.get(spec["value_env"], "")
                        if not value:
                            self.logger.warning(
                                f"  Setup [{i}/{total}]: env var '{spec['value_env']}' is not set or empty"
                            )
                    else:
                        value = spec.get("value", "")
                    page.locator(spec["selector"]).fill(value)
                    self.logger.info(f"  Setup [{i}/{total}]: filled '{spec['selector']}'")
                elif action == "click":
                    page.locator(step["click"]).click()
                    try:
                        page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        pass
                    self.logger.info(f"  Setup [{i}/{total}]: clicked '{step['click']}' — now at {page.url!r}")
                elif action == "wait":
                    ms = int(step["wait"])
                    page.wait_for_timeout(ms)
                    self.logger.info(f"  Setup [{i}/{total}]: waited {ms}ms")
                else:
                    self.logger.warning(f"  Setup [{i}/{total}]: unknown action '{action}' — skipping")
            except Exception as exc:
                self.logger.error(f"  Setup [{i}/{total}]: FAILED — {exc}")

    def scan_page(self, url: str, storage_state_path: Optional[str] = None, auth_config: Optional[dict] = None, setup_steps: Optional[list] = None, checkpoint_path: Optional[str] = None, checkpoint_interval_s: float = 10.0) -> Dict[str, Any]:
        # Bounds the "wait for the page to actually load" phase only — a page
        # that never reaches readyState=complete/network-idle can't be scanned
        # productively, so this stays finite. It does NOT bound how many
        # elements get collected once loaded (see _SCAN_SAFETY_S below).
        _TOTAL_S = 30
        _POLL_S = 3
        # Safety ceiling for the element-collection phase itself — exists only
        # to stop a genuinely hung page (e.g. an infinite-scroll trap) from
        # blocking the pipeline forever. It is NOT a coverage cap: every
        # selector is queried in full and every matching element is kept
        # unless this ceiling is actually hit. Set generously (10 min) because
        # per-element extraction does ~15+ separate synchronous round-trips
        # to the browser (get_attribute × 12, inner_text, is_visible,
        # is_enabled, tagName evaluate, ...) — a page with a few hundred
        # interactive elements (the exact case this cap removal targets,
        # e.g. a dashboard full of cards) can legitimately take minutes.
        _SCAN_SAFETY_S = 600

        page = self.launch(storage_state_path=storage_state_path, auth_config=auth_config)
        try:
            if setup_steps:
                self.logger.info(f"  Running {len(setup_steps)} setup step(s) before scan")
                self._execute_setup_steps(page, setup_steps)
                self.logger.info("  Setup steps complete — navigating to scan target")

            # Budget starts only once setup (e.g. a multi-step login) is done —
            # a slow login sequence must not eat into the time available to
            # actually wait for the target page to load and scan it.
            scan_start = time.monotonic()

            def _remaining() -> float:
                return _TOTAL_S - (time.monotonic() - scan_start)

            already_there = False
            try:
                already_there = _same_page(page.url, url)
            except Exception:
                pass

            if already_there:
                self.logger.info(f"  Already at target URL after setup steps ({page.url!r}) — skipping re-navigation")
            else:
                nav_timeout_ms = max(1000, _remaining() * 1000)
                try:
                    page.goto(url, wait_until="commit", timeout=nav_timeout_ms)
                except Exception as exc:
                    self.logger.warning(f"  Navigation did not commit: {exc}")

            dom_ready = False
            while _remaining() > 0:
                try:
                    ready_state = page.evaluate("document.readyState")
                except Exception:
                    ready_state = "unknown"
                elapsed = _TOTAL_S - _remaining()
                self.logger.info(
                    f"  DOM [{elapsed:.0f}s/{_TOTAL_S}s] readyState={ready_state}"
                )
                if ready_state in ("interactive", "complete"):
                    dom_ready = True
                    self.logger.info(f"  DOM loaded at {elapsed:.0f}s — waiting for network idle")
                    # Wait for dynamic content to finish loading so element set is stable
                    try:
                        idle_timeout = max(1000, min(8000, _remaining() * 1000 * 0.4))
                        page.wait_for_load_state("networkidle", timeout=idle_timeout)
                        self.logger.info("  Network idle — starting element scan")
                    except Exception:
                        self.logger.info("  Network idle timeout — starting element scan anyway")
                    break
                if _remaining() > _POLL_S:
                    time.sleep(_POLL_S)
                else:
                    break

            if not dom_ready:
                self.logger.warning(
                    f"  {_TOTAL_S}s timeout reached — force-closing after partial DOM capture"
                )

            page_title = ""
            try:
                page_title = page.title()
            except Exception:
                pass

            selectors = [
                "input",
                "button",
                "select",
                "textarea",
                "a",
                "[role=combobox]",
            ]
            elements = []
            seen = set()
            locator_counter = 1
            scan_truncated = False
            scan_start_ts = time.monotonic()
            last_checkpoint_ts = scan_start_ts

            def _scan_remaining() -> float:
                return _SCAN_SAFETY_S - (time.monotonic() - scan_start_ts)

            def _maybe_checkpoint(force: bool = False) -> None:
                nonlocal last_checkpoint_ts
                if not checkpoint_path:
                    return
                now = time.monotonic()
                if not force and (now - last_checkpoint_ts) < checkpoint_interval_s:
                    return
                try:
                    write_scan_checkpoint(checkpoint_path, url, page_title, elements)
                except Exception as exc:
                    self.logger.warning(f"  Scan checkpoint write failed: {exc}")
                last_checkpoint_ts = now

            for selector in selectors:
                if _scan_remaining() <= 0:
                    scan_truncated = True
                    break
                handles = page.query_selector_all(selector)
                for handle in handles:
                    if _scan_remaining() <= 0:
                        scan_truncated = True
                        break
                    data = self._get_element_data(handle)
                    css_selector = (
                        data.get("technical_locators", {}).get("css")
                        or ""
                    )
                    if not css_selector or css_selector in seen:
                        continue
                    seen.add(css_selector)
                    elements.append(
                        {
                            "locator_id": f"LOC-{locator_counter:04d}",
                            "tag": selector.replace("[role=combobox]", "combobox"),
                            **data,
                        }
                    )
                    locator_counter += 1
                    _maybe_checkpoint()
                if scan_truncated:
                    break
                _maybe_checkpoint(force=True)

            if scan_truncated:
                self.logger.warning(
                    f"  Scan safety ceiling hit — {len(elements)} element(s) collected "
                    f"(ceiling: {_SCAN_SAFETY_S}s) — page may have an unusually large or "
                    f"never-settling element set"
                )
            _demote_duplicate_role_candidates(elements)

            self.logger.info(
                f"  Element scan complete — {len(elements)} element(s) found — closing browser"
            )
            return {
                "url": url,
                "title": page_title,
                "element_count": len(elements),
                "elements": elements,
            }
        finally:
            self.close()

    def _build_locator_candidates(
            self,
            attribute_locators,
            playwright_locators
        ):

            candidates = []

            if attribute_locators.get("testid"):

                candidates.append(
                    {
                        "type": "testid",
                        "value": {
                            "testid":
                                attribute_locators["testid"]
                        },
                        "score": 100,
                        "unique": None,
                        "match_count": None,
                    }
                )

            if attribute_locators.get("id"):

                candidates.append(
                    {
                        "type": "id",
                        "value": {
                            "id":
                                attribute_locators["id"]
                        },
                        "score": 90,
                        "unique": None,
                        "match_count": None,
                    }
                )

            if playwright_locators.get("get_by_label"):

                candidates.append(
                    {
                        "type": "label",
                        "value":
                            playwright_locators[
                                "get_by_label"
                            ],
                        "score": 80,
                        "unique": None,
                        "match_count": None,
                    }
                )

            if playwright_locators.get("get_by_placeholder"):

                candidates.append(
                    {
                        "type": "placeholder",
                        "value":
                            playwright_locators[
                                "get_by_placeholder"
                            ],
                        "score": 70,
                        "unique": None,
                        "match_count": None,
                    }
                )

            if playwright_locators.get("get_by_role"):

                candidates.append(
                    {
                        "type": "role",
                        "value":
                            playwright_locators[
                                "get_by_role"
                            ],
                        "score": 60,
                        "unique": None,
                        "match_count": None,
                    }
                )

            if attribute_locators.get("name"):

                candidates.append(
                    {
                        "type": "name",
                        "value": {
                            "name":
                                attribute_locators["name"]
                        },
                        "score": 50,
                        "unique": None,
                        "match_count": None,
                    }
                )

            return candidates
        
    def _rank_locator_candidates(
            self,
            candidates
        ):

            for candidate in candidates:

                candidate["match_count"] = 1

                candidate["unique"] = True

                if candidate["unique"]:

                    candidate["score"] += 50

            candidates.sort(
                key=lambda x: x["score"],
                reverse=True
            )

            return candidates       
