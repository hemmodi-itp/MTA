"""
Generators (tools/agent_tests/generators): every dimension produces cases with the required fields and at least the
plan's minimum count from the buggy_bot spec; output is deterministic (same process, other processes, other
PYTHONHASHSEED); cuts carry reasons (no traces, no sessions, not authorised, disabled, thin spec).
"""

import json
import os
import subprocess
import sys

import pytest

from tools.agent_tests.catalogs import load_catalogs
from tools.agent_tests.config import MIN_CASES
from tools.agent_tests.dataset import REPO_ROOT, agent_dir, spec_for
from tools.agent_tests.generators import GENERATORS, generate_all
from tools.agent_tests.generators.robustness import slang, typo
from tools.agent_tests.models import DIMENSIONS, RED_TEAM, AgentTestCase
from tools.agent_tests.spec import AgentSpec

pytestmark = pytest.mark.mta

SPEC = spec_for(agent_dir("buggy_bot"))
CATALOGS = load_catalogs()


@pytest.fixture(scope="module")
def results():
    return generate_all(SPEC, CATALOGS, seed=7)


@pytest.mark.parametrize("dim", DIMENSIONS)
def test_each_dimension_meets_its_minimum(results, dim):
    res = results[dim]
    assert len(res.cases) >= MIN_CASES[dim], (dim, res.cut)
    assert not [c for c in res.cut if c["reason"] == "spec_lacks_material" and "below the minimum" in c["detail"]]


@pytest.mark.parametrize("dim", DIMENSIONS)
def test_each_case_has_the_required_fields(results, dim):
    for c in results[dim].cases:
        assert c.dimension == dim and c.id.startswith("AT-") and c.title
        assert (c.input is None) != (c.turns is None)
        assert c.source in ("brd", "generated", "human") and c.reviewed is False
        assert c.content_hash == c.compute_hash()
        assert c.ac_ids, f"{c.id} has no acceptance criterion (traceability)"
        AgentTestCase.model_validate(c.model_dump())  # round-trips through the schema


@pytest.mark.parametrize("dim", DIMENSIONS)
def test_generator_is_deterministic_in_process(dim):
    a = [c.model_dump() for c in GENERATORS[dim](SPEC, CATALOGS, 7).cases]
    b = [c.model_dump() for c in GENERATORS[dim](SPEC, CATALOGS, 7).cases]
    assert a == b


_DUMP = ("import json; from tools.agent_tests.catalogs import load_catalogs; "
         "from tools.agent_tests.dataset import agent_dir, spec_for; from tools.agent_tests.generators import generate_all; "
         "r = generate_all(spec_for(agent_dir('buggy_bot')), load_catalogs(), 7); "
         "print(json.dumps({d: [c.model_dump() for c in v.cases] for d, v in r.items()}, sort_keys=True))")


def test_generation_is_identical_across_processes_and_hash_seeds(results):
    here = json.dumps({d: [c.model_dump() for c in v.cases] for d, v in results.items()}, sort_keys=True)
    for hs in ("0", "1", "4242"):
        out = subprocess.run([sys.executable, "-c", _DUMP], cwd=REPO_ROOT, capture_output=True, text=True,
                             env={**os.environ, "PYTHONHASHSEED": hs, "PYTHONIOENCODING": "utf-8"},
                             encoding="utf-8", check=True).stdout.strip()
        assert out == here, f"PYTHONHASHSEED={hs} changed the generated cases"


def test_ids_are_unique_and_seed_only_changes_seeded_variants(results):
    ids = [c.id for r in results.values() for c in r.cases]
    assert len(ids) == len(set(ids))
    other = generate_all(SPEC, CATALOGS, seed=8)
    for dim in DIMENSIONS:
        same = [c.id for c in results[dim].cases] == [c.id for c in other[dim].cases]
        assert same or dim == "robustness", dim  # only the typo position depends on the seed


def test_red_team_cases_use_catalog_payloads_and_placeholders(results):
    for dim in ("prompt_injection_direct", "prompt_injection_indirect"):
        for c in results[dim].cases:
            assert "{{RUN_MARKER" in c.input and "RUN_MARKER" in c.expected.canary_absent
            assert any(t.startswith("catalog:injection_") for t in c.tags)
    leak = results["data_leakage"].cases
    assert any(c.turns for c in leak) and any(c.expected.canary_absent == ["CANARY_SYS"] for c in leak)
    sess = results["session_isolation"].cases
    assert all({t.session for t in c.turns} == {"A", "B"} for c in sess)


def test_robustness_variants_point_at_their_base(results):
    base_ids = {c.id for c in results["task_success"].cases}
    kinds = set()
    for c in results["robustness"].cases:
        kinds |= {t.split(":", 1)[1] for t in c.tags if t.startswith("perturbation:")}
        if c.expected.same_as:
            assert c.expected.same_as in base_ids
        else:
            assert c.expected.graceful
    assert kinds == {"typo", "upper_case", "slang", "paraphrase", "other_language", "very_long", "empty", "emoji_only"}


def test_perturbation_helpers():
    assert typo("What are your opening hours?", 7, "k") == typo("What are your opening hours?", 7, "k")
    t = typo("What are your opening hours?", 7, "k")
    assert t != "What are your opening hours?" and sorted(t) == sorted("What are your opening hours?")
    assert typo("hi u", 7, "k") == "hi u"  # no 5+ letter word
    assert slang("What are your hours, please?", {"what": "wut", "are": "r", "your": "ur", "hours": "hrs",
                                                  "please": "pls"}) == "wut r ur hrs, pls?"


def _spec(**changes) -> AgentSpec:
    raw = SPEC.model_dump(by_alias=True)
    raw.update(changes)
    return AgentSpec.model_validate(raw)


def test_unauthorised_agent_gets_no_red_team_cases():
    res = generate_all(_spec(authorization={"owned_or_authorized": False}), CATALOGS, 7)
    for dim in RED_TEAM:
        assert not res[dim].cases and res[dim].cut[0]["reason"] == "not_authorized"
    assert res["task_success"].cases


def test_no_trace_and_no_session_cuts():
    transport = {**SPEC.transport.model_dump(), "trace_path": None, "history": "none",
                 "body": {"message": "{message}"}}
    res = generate_all(_spec(transport=transport), CATALOGS, 7)
    assert not res["tool_use"].cases and "no tool trace" in res["tool_use"].cut[0]["detail"]
    for dim in ("multi_turn", "session_isolation"):
        assert not res[dim].cases and res[dim].cut[0]["reason"] == "no_session_support"
    assert not any(c.turns for c in res["data_leakage"].cases)


def test_disabled_dimension_and_thin_spec_shortfall():
    res = generate_all(_spec(dimensions={"scope": {"enabled": False}}, kb={"docs": [], "unanswerable": []}),
                       CATALOGS, 7)
    assert not res["scope"].cases and res["scope"].cut[0]["reason"] == "disabled"
    assert any(c["reason"] == "spec_lacks_material" for c in res["hallucination"].cut)
    assert any(c["reason"] == "spec_lacks_material" for c in res["groundedness"].cut)


def test_black_box_agent_notes_system_canary_not_applicable():
    res = generate_all(_spec(canaries={}), CATALOGS, 7)
    assert any(c["reason"] == "not_applicable" for c in res["data_leakage"].cut)
