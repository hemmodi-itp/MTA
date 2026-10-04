"""
tools.py — tool surface for SemanticMapAgent.

Re-exports its DOM-locator-mapping helpers, plus the intent-clustering /
confidence-scoring / source_scenarios-backlink functions that give
scenario_element_map.json intent-level richness (action, expected_result,
functional cluster, confidence) instead of bare locator picks.

Kept as plain, unit-testable functions (no agent/LLM state) rather than
inlined into agent.py so this logic lifts directly into an ADK Skill/Tool
later without a rewrite (see docs/agentic_platform_and update.md Epic 8.4).
"""

import os
import re
from typing import Dict, List, Optional

import yaml

from tools.test_creation.script_generator.build_dom_locator_map import (
    build_element_summary,
    build_locator_map,
)

__all__ = [
    "build_element_summary",
    "build_locator_map",
    "build_intent_clusters",
    "apply_user_flow_clusters",
    "score_scenario_relevance",
    "enrich_relevant_elements",
    "backlink_source_scenarios",
]

_ACTION_PREFIXES = (
    "fill_", "click_", "enter_", "select_", "verify_", "navigate_", "hover_",
)
_STOPWORDS = {
    "the", "a", "an", "of", "and", "or", "to", "on", "in", "for", "with",
    "is", "opened", "element", "page",
}


def _tokenize(text: str) -> set:
    return {
        t for t in re.findall(r"[a-z0-9]+", (text or "").lower())
        if t not in _STOPWORDS and len(t) > 2
    }


def _intent_tokens(intent: dict) -> set:
    name = intent.get("intent_name", "") or ""
    for prefix in _ACTION_PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    return _tokenize(name.replace("_", " "))


def build_intent_clusters(intents: List[dict]) -> Dict[str, str]:
    """
    Group intents into functional buckets by normalized-name token overlap —
    e.g. enter_username / enter_password / click_forgot_password /
    click_forgot_username share the 'username'/'password' tokens and land in
    one cluster, so a "login" scenario can pull in the whole bucket instead
    of whatever 3-7 elements an LLM pass happened to name individually.

    Union-find over shared tokens (no embeddings, no LLM call — deterministic
    and free). Returns {intent_id: cluster_label}.
    """
    ids = [i.get("intent_id") for i in intents if i.get("intent_id")]
    tokens_by_id = {iid: _intent_tokens(i) for iid, i in zip(ids, intents)}
    parent = {iid: iid for iid in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for idx, a in enumerate(ids):
        for b in ids[idx + 1:]:
            if tokens_by_id[a] & tokens_by_id[b]:
                union(a, b)

    roots: Dict[str, List[str]] = {}
    for iid in ids:
        roots.setdefault(find(iid), []).append(iid)

    labels: Dict[str, str] = {}
    for root, members in roots.items():
        token_counts: Dict[str, int] = {}
        for m in members:
            for t in tokens_by_id[m]:
                token_counts[t] = token_counts.get(t, 0) + 1
        label = max(token_counts, key=token_counts.get) if token_counts else root
        for m in members:
            labels[m] = label
    return labels


def apply_user_flow_clusters(
    clusters: Dict[str, str],
    user_flows: List[dict],
    intent_id_by_locator: Dict[str, str],
) -> Dict[str, str]:
    """
    Recorded interactive-scan flows (comprehension/.../interactive/
    user_flows.json) are a stronger, ground-truth clustering signal than
    keyword overlap — e.g. sign in -> search mobile -> click add to cart,
    recorded as one flow. Every intent touched within the same flow is
    unioned into one flow-labelled cluster, overriding whatever
    keyword-based cluster it landed in from build_intent_clusters.
    """
    updated = dict(clusters)
    for flow in user_flows:
        flow_label = f"flow:{flow.get('inferred_name') or flow.get('flow_id') or 'unnamed'}"
        member_ids = [
            intent_id_by_locator[loc_id]
            for step in flow.get("steps", [])
            if (loc_id := step.get("locator_id")) and loc_id in intent_id_by_locator
        ]
        if len(member_ids) >= 2:
            for iid in member_ids:
                updated[iid] = flow_label
    return updated


def score_scenario_relevance(
    scenario: dict,
    intents: List[dict],
    clusters: Dict[str, str],
) -> Dict[str, float]:
    """
    Keyword-overlap confidence per intent_id for this scenario (mirrors
    fallback_core.fallback_semantic_map's keyword-overlap approach — reused
    here as a deterministic signal, not a second LLM call), then boosted so
    every intent sharing a cluster with a directly-matched intent inherits
    that match's confidence too. This is how "BRD mentions products" ends up
    boosting the whole products/search/pricing cluster even if a scenario's
    own step text only explicitly names one of them.
    """
    traceability_text = " ".join(
        f"{t.get('section') or ''} {t.get('requirement_id') or ''}"
        for t in (scenario.get("traceability") or [])
        if isinstance(t, dict)
    )
    steps = scenario.get("steps") or []
    steps_text = " ".join(s if isinstance(s, str) else str(s) for s in steps)
    scenario_tokens = _tokenize(" ".join(filter(None, [
        scenario.get("title", ""),
        scenario.get("business_objective", ""),
        steps_text,
        traceability_text,
    ])))

    direct_scores: Dict[str, float] = {}
    for intent in intents:
        iid = intent.get("intent_id")
        if not iid:
            continue
        overlap = scenario_tokens & _intent_tokens(intent)
        if overlap:
            direct_scores[iid] = min(1.0, 0.5 + 0.1 * len(overlap))

    cluster_best: Dict[str, float] = {}
    for iid, score in direct_scores.items():
        cluster = clusters.get(iid)
        if cluster:
            cluster_best[cluster] = max(cluster_best.get(cluster, 0.0), score)

    final: Dict[str, float] = {}
    for intent in intents:
        iid = intent.get("intent_id")
        if not iid:
            continue
        cluster = clusters.get(iid)
        score = direct_scores.get(iid, 0.0)
        if cluster in cluster_best:
            # Cluster-inherited relevance is real but slightly less certain
            # than an intent the scenario text named directly.
            score = max(score, cluster_best[cluster] * 0.9)
        if score:
            final[iid] = round(score, 2)
    return final


def enrich_relevant_elements(
    relevant_elements: List[dict],
    intents_by_locator: Dict[str, dict],
    clusters: Dict[str, str],
    confidences: Dict[str, float],
) -> List[dict]:
    """
    Attach intent_id/action/expected_result/cluster/confidence onto each
    scenario_element_map.json relevant_elements entry, matched by
    locator_id. Elements with no matching module intent (e.g. from a
    dom_elements.json-only fallback path) are passed through unchanged.
    """
    enriched = []
    for el in relevant_elements:
        el = dict(el)
        intent = intents_by_locator.get(el.get("locator_id", ""))
        if intent:
            iid = intent.get("intent_id")
            el["intent_id"] = iid
            el["action"] = intent.get("action")
            el["expected_result"] = intent.get("expected_result")
            el["cluster"] = clusters.get(iid)
            el["confidence"] = confidences.get(iid, 0.5)
        enriched.append(el)
    return enriched


def backlink_source_scenarios(
    intents_yaml_path: str,
    module_id: Optional[str],
    scenario_to_intent_ids: Dict[str, List[str]],
) -> bool:
    """
    Populate intents.yaml's per-intent source_scenarios for this module only
    — mirrors DiscoveryAgent._save_intents_yaml's "replace only this
    module_id's slice" merge rule, so other modules' entries (and any
    scenario mappings already recorded for them) are left untouched.

    Returns True if the file was rewritten, False if there was nothing to
    add (missing file, or every mapping already present).
    """
    if not scenario_to_intent_ids or not os.path.exists(intents_yaml_path):
        return False

    with open(intents_yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    intents = data.get("intents", [])

    intent_to_scenarios: Dict[str, set] = {}
    for sid, intent_ids in scenario_to_intent_ids.items():
        for iid in intent_ids:
            intent_to_scenarios.setdefault(iid, set()).add(sid)

    changed = False
    for intent in intents:
        if intent.get("module_id") != module_id:
            continue
        new_scenarios = intent_to_scenarios.get(intent.get("intent_id"))
        if not new_scenarios:
            continue
        existing = set(intent.get("source_scenarios") or [])
        merged = sorted(existing | new_scenarios)
        if merged != (intent.get("source_scenarios") or []):
            intent["source_scenarios"] = merged
            changed = True

    if changed:
        with open(intents_yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return changed
