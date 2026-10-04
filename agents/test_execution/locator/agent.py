"""
LocatorAgent — step 5 gap-filler.

When DiscoveryAgent ran with a URL (modes: both / url_only), most intents
already have locator_id set. This agent only assigns selectors to those
that are still null — it does NOT re-scan intents that already have a locator.

If DiscoveryAgent ran in brd_only mode (no URL available at discovery time),
this agent runs a full DOM scan and assigns locators to all intents.

Reads:   application_assets/{project}/artifacts/intents.yaml
Writes:  application_assets/{project}/locators/locators.json
"""

import json
import os
from typing import Any, Dict, List

import yaml

from agents.base_agent import BaseAgent
from agents.test_execution.locator.tools import generate_intent_suggestions, PlaywrightScanner
from tools.shared import get_logger

from tools.constants import PROJECTS_BASE as _ASSETS_BASE


class LocatorAgent(BaseAgent):
    def __init__(self, provider=None, settings: Dict[str, str] = None):
        self.settings = settings or {}
        self.logger = get_logger("agent.execution.locator")

    def execute(self, request: dict, state: dict) -> Dict[str, Any]:
        project_name = request.get("project_name") or request.get("message", "project")
        safe = _safe_name(project_name)
        url = request.get("url", "")
        browser = request.get("browser", "chromium")
        headless = request.get("headless", True)

        self.logger.info(f"[LocatorAgent] Starting — project='{project_name}' url={url or '(none)'}")

        if not url:
            self.logger.warning("[LocatorAgent] No URL — skipping locator assignment")
            return {"module": "locator", "status": "skipped", "reason": "no URL in request"}

        intents_path = os.path.join(_ASSETS_BASE, safe, "test_creation", "intents.yaml")
        locators_path = os.path.join(_ASSETS_BASE, safe, "test_creation", "locators.json")

        if not os.path.exists(intents_path):
            self.logger.warning(f"[LocatorAgent] intents.yaml not found at '{intents_path}'")
            return {
                "module": "locator",
                "status": "skipped",
                "reason": f"intents.yaml not found at '{intents_path}'",
            }

        # Load current intents
        with open(intents_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        all_intents = raw.get("intents", [])

        # Find which intents still need a locator
        missing = [i for i in all_intents if not i.get("locator_id")]
        already_set = len(all_intents) - len(missing)

        if not missing:
            self.logger.info(
                f"[LocatorAgent] All {len(all_intents)} intents already grounded — nothing to do"
            )
            return {
                "module": "locator",
                "status": "skipped",
                "reason": "all intents already grounded by DiscoveryAgent",
                "intents_already_grounded": already_set,
            }

        self.logger.info(
            f"[LocatorAgent] {already_set} already grounded, {len(missing)} need locators — scanning"
        )

        # Scan DOM
        try:
            runner = PlaywrightScanner(browser_name=browser, headless=headless)
            scan_result = runner.scan_page(url)
            elements: List[Dict] = scan_result.get("elements", [])
        except Exception as exc:
            self.logger.error(f"[LocatorAgent] DOM scan failed: {exc}")
            return {"module": "locator", "status": "failed", "error": str(exc)}

        dom_suggestions = generate_intent_suggestions(project_name, elements)
        dom_intents = dom_suggestions.get("intents", [])

        # Build lookup from DOM
        by_exact: Dict[str, str] = {}
        by_norm: Dict[str, str] = {}
        for d in dom_intents:
            dname = d.get("intent_name", "")
            locator = d.get("locator_id", "")
            if locator:
                by_exact[dname] = locator
                by_norm[_strip_prefix(dname)] = locator

        # Assign locators to missing intents
        patched = 0
        for intent in missing:
            iname = intent.get("intent_name", "")
            inorm = _strip_prefix(iname)
            locator = (
                by_exact.get(iname)
                or by_norm.get(inorm)
                or _substr_match(inorm, by_exact)
            )
            if locator:
                intent["locator_id"] = locator
                patched += 1

        # Write back updated intents.yaml
        with open(intents_path, "w", encoding="utf-8") as f:
            yaml.dump({"intents": all_intents}, f, allow_unicode=True, sort_keys=False)

        # Write locators.json — resolve LOC-IDs to actual CSS selectors
        os.makedirs(os.path.dirname(locators_path), exist_ok=True)
        loc_to_css = _build_loc_to_css_map(elements)
        locators_out = [
            {
                "intent_id": i["intent_id"],
                "intent_name": i["intent_name"],
                "selector": loc_to_css.get(i.get("locator_id", ""), i.get("locator_id", "")),
            }
            for i in all_intents if i.get("locator_id")
        ]
        with open(locators_path, "w", encoding="utf-8") as f:
            json.dump({"locators": locators_out}, f, indent=2, ensure_ascii=False)

        total_grounded = already_set + patched
        self.logger.info(f"[LocatorAgent] Written: {intents_path}")
        self.logger.info(f"[LocatorAgent] Written: {locators_path}")
        self.logger.info(
            f"[LocatorAgent] Done — {patched} new, {total_grounded}/{len(all_intents)} total grounded"
        )
        return {
            "module": "locator",
            "status": "success",
            "intents_already_grounded": already_set,
            "intents_newly_grounded": patched,
            "intents_total": len(all_intents),
            "locators_path": locators_path,
        }


# ── helpers ───────────────────────────────────────────────────────────

_PREFIXES = ("fill_", "click_", "enter_", "select_", "verify_", "navigate_", "hover_")


def _strip_prefix(name: str) -> str:
    for p in _PREFIXES:
        if name.startswith(p):
            return name[len(p):]
    return name


def _substr_match(norm: str, by_exact: Dict[str, str]) -> str:
    for dname, locator in by_exact.items():
        dnorm = _strip_prefix(dname)
        if dnorm in norm or norm in dnorm:
            return locator
    return ""


def _build_loc_to_css_map(elements: List[Dict]) -> Dict[str, str]:
    """Build {LOC-0001: '#hero-email', ...} from a DOM element list."""
    result: Dict[str, str] = {}
    for el in elements:
        loc_id = el.get("locator_id")
        if not loc_id:
            continue
        rec = el.get("recommended_locator") or {}
        t = rec.get("type", "")
        v = rec.get("value") or {}
        css = ""
        if t == "id" and v.get("id"):
            css = f'#{v["id"]}'
        elif t == "name" and v.get("name"):
            css = f'[name="{v["name"]}"]'
        elif t == "css" and v.get("css"):
            css = v["css"]
        elif t == "testid" and v.get("testid"):
            css = f'[data-testid="{v["testid"]}"]'
        elif t == "placeholder" and v.get("placeholder"):
            css = f'[placeholder="{v["placeholder"]}"]'
        if not css:
            css = (el.get("technical_locators") or {}).get("css", "")
        if css:
            result[loc_id] = css
    return result


def _safe_name(name: str) -> str:
    sanitised = "".join(
        c if (c.isalnum() or c in "-_") else "_" for c in name
    ).strip("_")
    return sanitised or "project"
