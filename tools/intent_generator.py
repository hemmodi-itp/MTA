import os
import re
from typing import Dict, List, Any, Optional

from tools.file_manager import save_yaml_file
from tools.asset_loader import intent_dir
from tools.state.artifact_registry import ArtifactRegistry


ALLOWED_ACTIONS = {
    "click",
    "fill",
    "select",
    "hover",
    "press",
    "verify",
    "navigate",
    "wait",
}


def _normalize_name(text: str) -> str:
    if not text:
        return ""

    text = text.lower().strip()
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[^a-z0-9_]", "", text)

    return text


def _determine_action(element: Dict[str, Any]) -> str:

    tag = (element.get("tag") or "").lower()

    semantic = element.get("semantic_locators", {}) or {}

    role = (semantic.get("role") or "").lower()

    if tag in ["input", "textarea"]:
        return "fill"

    if tag == "select":
        return "select"

    if tag in ["button", "a"]:
        return "click"

    if role in ["button", "link"]:
        return "click"

    if role in ["textbox", "searchbox"]:
        return "fill"

    return "click"


def _build_intent_name(
    action: str,
    element: Dict[str, Any]
) -> str:

    display_text = (
        element.get("display_text")
        or ""
    )

    semantic = (
        element.get("semantic_locators")
        or {}
    )

    attribute = (
        element.get("attribute_locators")
        or {}
    )

    candidate = (
        display_text
        or semantic.get("label")
        or semantic.get("placeholder")
        or attribute.get("name")
        or "element"
    )

    candidate = _normalize_name(candidate)

    if action == "fill":
        return f"enter_{candidate}"

    if action == "click":
        return f"click_{candidate}"

    if action == "select":
        return f"select_{candidate}"

    if action == "verify":
        return f"verify_{candidate}"

    return f"{action}_{candidate}"


def _build_locator_id(
    element: Dict[str, Any],
    index: int
) -> str:

    locator_id = element.get("locator_id")

    if locator_id:
        return locator_id

    return f"LOC-{index:03d}"


def _build_expected_result(
    action: str,
    element: Dict[str, Any]
) -> str | None:

    if action == "click":

        text = (
            element.get("display_text")
            or ""
        )

        if text:
            return f"{_normalize_name(text)}_opened"

    return None


def _validate_intent(
    intent: Dict[str, Any]
) -> None:

    if not intent.get("intent_id"):
        raise ValueError(
            "intent_id is mandatory"
        )

    if not intent.get("intent_name"):
        raise ValueError(
            "intent_name is mandatory"
        )

    if not intent.get("action"):
        raise ValueError(
            "action is mandatory"
        )

    if intent["action"] not in ALLOWED_ACTIONS:
        raise ValueError(
            f"Invalid action: {intent['action']}"
        )


def generate_intent_suggestions(
    page_name: str,
    elements: List[Dict[str, Any]],
    registry: Optional[ArtifactRegistry] = None,
) -> Dict[str, Any]:
    """
    Args:
        registry: when provided, intent_id is resolved from the registry by
            content signature (action + intent_name) instead of a bare
            per-scan counter. This makes the same UI element keep the same
            intent_id across re-scans, and only genuinely new elements get a
            new, non-colliding id — avoiding the churn/collisions a restart-
            at-1 counter causes on every discovery run.
    """

    intents: List[Dict[str, Any]] = []

    seen_names = set()

    counter = 1

    for index, element in enumerate(elements, start=1):

        action = _determine_action(element)

        intent_name = _build_intent_name(
            action,
            element,
        )

        if intent_name in seen_names:
            continue

        seen_names.add(intent_name)

        locator_id = _build_locator_id(
            element,
            index,
        )

        if registry is not None:
            intent_id, _is_new, _hash = registry.get_or_create_id(
                "DOM", "INT", intent_name, action
            )
        else:
            intent_id = f"INT-{counter:03d}"

        intent = {

            "intent_id":
                intent_id,

            "intent_name":
                intent_name,

            "action":
                action,

            "locator_id":
                locator_id,

            "value":
                None,

            "expected_result":
                _build_expected_result(
                    action,
                    element,
                ),
        }

        _validate_intent(intent)

        intents.append(intent)

        counter += 1

    return {

        "page_name":
            page_name,

        "intent_count":
            len(intents),

        "intents":
            intents,
    }


def generate_intent_suggestions_multipage(
    pages: List[Dict[str, Any]],
    registry: Optional[ArtifactRegistry] = None,
) -> Dict[str, Any]:
    """
    Generate intent suggestions for a multi-page interactive scan result.

    Each intent is tagged with its source page_id. Intent names are globally
    deduplicated — collisions are resolved by appending the page name suffix.

    Args:
        registry: see generate_intent_suggestions() — same content-signature
            stability, keyed additionally by page_id so identical intent
            names on different pages remain distinct.

    Returns a dict with flat 'intents' (backward-compat) and a 'pages' array.
    """
    all_intents: List[Dict[str, Any]] = []
    page_groups: List[Dict[str, Any]] = []
    global_seen_names: set = set()
    global_counter = 1

    for page in pages:
        page_id = page.get("page_id", f"PAGE-{len(page_groups) + 1:03d}")
        page_name = page.get("page_name", page_id)
        elements = page.get("elements", [])

        page_intents: List[Dict[str, Any]] = []

        for index, element in enumerate(elements, start=1):
            action = _determine_action(element)
            intent_name = _build_intent_name(action, element)

            # Resolve name collisions across pages
            if intent_name in global_seen_names:
                suffix = _normalize_name(page_name)
                candidate = f"{intent_name}_{suffix}"
                if candidate in global_seen_names:
                    continue
                intent_name = candidate

            global_seen_names.add(intent_name)
            locator_id = _build_locator_id(element, index)

            if registry is not None:
                intent_id, _is_new, _hash = registry.get_or_create_id(
                    "DOM", "INT", page_id, intent_name, action
                )
            else:
                intent_id = f"INT-{global_counter:03d}"

            intent: Dict[str, Any] = {
                "intent_id":       intent_id,
                "intent_name":     intent_name,
                "action":          action,
                "locator_id":      locator_id,
                "page_id":         page_id,
                "value":           None,
                "expected_result": _build_expected_result(action, element),
            }

            _validate_intent(intent)
            page_intents.append(intent)
            all_intents.append(intent)
            global_counter += 1

        page_groups.append({
            "page_id":     page_id,
            "page_name":   page_name,
            "path":        page.get("path", "/"),
            "intent_count": len(page_intents),
            "intents":     page_intents,
        })

    return {
        "scan_mode":    "interactive",
        "pages":        page_groups,
        "intent_count": len(all_intents),
        "intents":      all_intents,   # flat union for backward compat
    }


def save_intent_suggestion(
    page_name: str,
    intent_data: Dict[str, Any]
) -> str:

    os.makedirs(
        intent_dir(),
        exist_ok=True,
    )

    intent_path = os.path.join(
        intent_dir(),
        f"{page_name}.intent.yaml",
    )

    save_yaml_file(
        intent_path,
        intent_data,
    )

    return intent_path