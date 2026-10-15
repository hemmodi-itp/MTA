"""
llm_evals.py — Phase 12.4: eval sets for the LLM agents — fixed inputs, invariant checks.

    python -m tools.selftest.llm_evals --replay                     # CI: invariants on recorded replies, no LLM
    python -m tools.selftest.llm_evals --live [--record] [--agent X] # the real LLM (connectors.llm in settings.yaml;
                                                                      # gemini needs GOOGLE_API_KEY, read from .env too)
    python -m tools.selftest.llm_evals --check-stale                # exit 1: a prompt file changed since the last
                                                                      # recorded eval (re-run --live --record)
    python -m tools.selftest.llm_evals --stamp                      # accept the current prompt files (after review)

Layout (tests/fixtures/llm_evals/):
    <agent>/cases/<case>.json             the fixed input: {"task": <task>, ...}
    <agent>/recorded/<case>__<label>.json {"case", "replies": [raw LLM text, in call order], "expect": [invariants this
                                          reply must violate — [] for a good one], "source": "live <model> <date>" |
                                          "hand-written: <why>"}  (healing: "audit" rows instead of "replies")
    prompt_hashes.json                    {agent: {prompt file: sha256}} when the recordings were last made / accepted

A replay feeds the recorded replies to the agent's real entry point through a fake LLM — the agent's own parsing and
guards run — and checks invariants at two levels:
    raw.*   the model's reply itself: a regressed prompt or model shows here even when a guard repairs it later
    out.*   what the agent produced from that reply
Every recording must violate exactly its `expect` set: good replies pass everything, and each bad reply proves that
its checker catches what it was written for.

Agents and invariants:
    comprehension     requirements: reply is JSON; every criterion's source quote is found in the BRD
                      (BrdIndex.quote_match); every declared AC id kept; extraction status ok.
                      scenarios: validate_business_scenarios keeps every scenario; every ac_id is a given AC; every
                      scenario is traced to at least one AC.
    test_data         validate_test_data keeps the dataset; no security payload (drop_security_payloads,
                      detect_payload); variant / iteration caps respected; scenario id kept.
    semantic_map      every locator_id exists in dom_elements; every scenario id exists and every scenario is mapped;
                      3-7 elements per scenario.
    script_generation _validate_plan (allowed actions and locator keys only, no fixed sleeps); no test dropped by the
                      agent's guards; assertion_linter.lint_plan finds no weak test; plan_filter.filter_plan drops nothing.
    test_design       interpret_module returns valid DesignHints; sanitize drops nothing (every reference valid).
    healing           (ADK tool loop, no single prompt call — its healing_audit.jsonl trajectory) applied/proposed
                      locator heals pass the identity threshold, refusals are below it or ambiguous; spec patches pass
                      _structurally_valid_block, add no fixed sleep, keep the traceability header; a revert follows
                      an applied heal; approver matches the outcome.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[2]
EVALS = ROOT / "tests" / "fixtures" / "llm_evals"
RECORDED_INPUTS = ROOT / "tests" / "fixtures" / "recorded" / "buggy_shop"
HASHES = EVALS / "prompt_hashes.json"

Violation = Tuple[str, str]          # (invariant, detail)


# ── fake / recording LLMs ────────────────────────────────────────────────────

class ReplayLLM:
    """Returns the recorded replies in order (`.generate(prompt) -> str`; nothing is cached)."""

    def __init__(self, replies: List[str]):
        self.replies, self.prompts = list(replies), []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self.replies:
            raise RuntimeError("replay: the agent asked for more LLM replies than were recorded")
        return self.replies.pop(0)


class RecordingLLM:
    def __init__(self, inner):
        self.inner, self.replies = inner, []

    def generate(self, prompt: str) -> str:
        reply = self.inner.generate(prompt)
        self.replies.append(reply)
        return reply


# ── helpers ──────────────────────────────────────────────────────────────────

def _json(text: str) -> Tuple[Optional[Any], Optional[str]]:
    from tools.shared.llm_response_validator import parse_llm_json
    try:
        return parse_llm_json(text), None
    except Exception as exc:                 # noqa: BLE001 — any parse failure is the violation
        return None, f"{type(exc).__name__}: {str(exc)[:200]}"


def _first_json(replies: List[str]) -> Tuple[Optional[Any], List[Violation]]:
    if not replies:
        return None, [("raw.json", "no reply recorded")]
    data, err = _json(replies[0])
    return data, ([("raw.json", err)] if err else [])


@contextlib.contextmanager
def _temp_project(files: Dict[str, Any], project_yaml: Optional[dict] = None,
                  patch_modules: Tuple[str, ...] = ()) -> Iterator[Path]:
    """A throwaway project dir (name "llmeval") under a temp PROJECTS_BASE; `files` maps relative path -> JSON
    payload or a source Path. `patch_modules` alias PROJECTS_BASE at import time (`_ASSETS_BASE`)."""
    import importlib
    import tools.constants as constants
    base = Path(tempfile.mkdtemp(prefix="mta_llmeval_"))
    pdir = base / "llmeval"
    try:
        for rel, content in files.items():
            p = pdir / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, Path):
                shutil.copy(content, p)
            else:
                p.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
        if project_yaml is not None:
            (pdir / "project.yaml").write_text(yaml.safe_dump(project_yaml, sort_keys=False), encoding="utf-8")
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(constants, "PROJECTS_BASE", str(base)))
            for name in patch_modules:
                stack.enter_context(mock.patch.object(importlib.import_module(name), "_ASSETS_BASE", str(base)))
            yield pdir
    finally:
        shutil.rmtree(base, ignore_errors=True)


# buggy_shop's modules, for the agents that read them from project.yaml (test design)
BUGGY_SHOP_YAML = {
    "project": {"name": "llmeval"}, "environment": "local", "requirements": {"enabled": True},
    "modules": [{"id": mid, "name": name, "url": f"http://127.0.0.1:8765{path}"} for mid, name, path in (
        ("M01", "Login", "/login"), ("M02", "Products", "/products"), ("M03", "Product Form", "/products/new"),
        ("M04", "Cart & Checkout", "/cart"), ("M05", "Upload", "/upload"), ("M06", "Admin", "/admin"))],
}


# ── comprehension: requirements ──────────────────────────────────────────────

def _quote_ok(index, quote: Optional[str]) -> bool:
    return bool(quote) and index.quote_match(quote) != "none"


def run_requirements(case: dict, llm) -> Tuple[Any, List[Violation]]:
    from tools.requirements.extract import extract_requirements
    from tools.requirements.ids import IdAllocator
    from tools.state.artifact_registry import ArtifactRegistry
    with tempfile.TemporaryDirectory() as d:
        res = extract_requirements(case["brd"], llm, allocator=IdAllocator(ArtifactRegistry(d)),
                                   module_id=case.get("module_id"), module_label=case.get("module_label", ""))
    return res, []


def check_requirements(case: dict, replies: List[str], res) -> List[Violation]:
    from tools.requirements import explicit
    from tools.requirements.brd_index import BrdIndex
    index = BrdIndex(case["brd"])
    declared = {c.id for r in explicit.parse(case["brd"]) for c in r.criteria}      # the document's own AC ids
    v: List[Violation] = []
    data, v_raw = _first_json(replies)
    v += v_raw
    if isinstance(data, dict):
        crits = [c for r in data.get("requirements") or [] for c in r.get("acceptance_criteria") or []]
        bad = [c.get("id") or c.get("statement", "")[:40] for c in crits if not _quote_ok(index, c.get("source_quote"))]
        if bad:
            v.append(("raw.quotes_grounded", f"{len(bad)} criterion quote(s) not found in the BRD: {bad[:4]}"))
        missing = sorted(declared - {c.get("id") for c in crits})
        if missing:
            v.append(("raw.declared_kept", f"declared AC id(s) missing from the reply: {missing}"))
    if res.status != "ok":
        v.append(("out.status_ok", f"extraction status {res.status}: {res.limitations[:2]}"))
    acs = [ac for r in res.requirements for ac in r.acceptance_criteria]
    bad = [ac.id for ac in acs if not _quote_ok(index, ac.source_quote)]
    if bad:
        v.append(("out.quotes_grounded", f"AC(s) without a BRD-grounded quote: {bad[:5]}"))
    missing = sorted(declared - {ac.doc_id or ac.id for ac in acs})
    if missing:
        v.append(("out.declared_kept", f"declared AC id(s) lost: {missing}"))
    return v


# ── comprehension: business scenarios ────────────────────────────────────────

def run_scenarios(case: dict, llm) -> Tuple[Any, List[Violation]]:
    from tools.comprehension.generate_business_scenarios import generate_business_scenarios
    from tools.comprehension.models import Requirement
    try:
        out = generate_business_scenarios(
            "Buggy Shop", [Requirement(**r) for r in case["requirements"]], [], [], [], llm,
            module_id=case.get("module_id"), module_name=case.get("module_name"),
            acceptance_criteria=case["acceptance_criteria"])
    except ValueError as exc:
        return [], [("out.parsed", str(exc)[:200])]
    return out, []


def check_scenarios(case: dict, replies: List[str], scenarios) -> List[Violation]:
    from tools.comprehension.validate_business_scenarios import validate_business_scenarios
    v: List[Violation] = []
    _data, v_raw = _first_json(replies)
    v += v_raw
    if not scenarios:
        return v + [("out.non_empty", "no scenarios")]
    valid, warnings = validate_business_scenarios(scenarios)
    if len(valid) != len(scenarios):
        v.append(("out.scenarios_valid", f"{len(scenarios) - len(valid)} scenario(s) rejected: "
                                         f"{[w for w in warnings if 'non-fatal' not in w and 'confidence' not in w][:3]}"))
    known = {a["id"] for a in case["acceptance_criteria"]}
    unknown = sorted({a for s in scenarios for a in s.ac_ids} - known)
    if unknown:
        v.append(("out.ac_ids_known", f"scenarios cite AC ids that were not given: {unknown}"))
    # not "every scenario has an AC": the prompt asks for ids only "when any applies" (a delete scenario may match
    # none of the given criteria) — but every given criterion must be exercised by some scenario
    uncovered = sorted(known - {a for s in scenarios for a in s.ac_ids})
    if uncovered:
        v.append(("out.acs_covered", f"AC(s) no scenario exercises: {uncovered}"))
    return v


# ── test data ────────────────────────────────────────────────────────────────

def run_test_data(case: dict, llm) -> Tuple[Any, List[Violation]]:
    from agents.test_creation.testdata.prompt import TEST_DATA_GENERATION_PROMPT
    from agents.test_creation.testdata.skills import SKILLS
    from tools.comprehension.models import BusinessScenario
    from tools.test_creation.testdata.generate_test_data import generate_test_data
    try:
        ds = generate_test_data(BusinessScenario(**case["scenario"]), llm, TEST_DATA_GENERATION_PROMPT,
                                SKILLS["test_data_generation"].header(), 1,
                                max_negative_cases=case["max_negative_cases"],
                                max_boundary_cases=case["max_boundary_cases"],
                                max_data_iterations=case["max_data_iterations"])
    except (ValueError, RuntimeError) as exc:
        return None, [("out.parsed", str(exc)[:200])]
    return ds, []


def check_test_data(case: dict, replies: List[str], ds) -> List[Violation]:
    from tools.safety.payloads import detect_payload
    from tools.safety.testdata_filter import drop_security_payloads
    from tools.test_creation.testdata.validate_test_data import validate_test_data
    v: List[Violation] = []
    data, v_raw = _first_json(replies)
    v += v_raw
    if isinstance(data, dict):
        variants = data.get("negative_variants") or []
        for kind, cap in (("negative", case["max_negative_cases"]), ("boundary", case["max_boundary_cases"])):
            n = sum(1 for x in variants if x.get("variant_type") == kind)
            if n > cap:
                v.append(("raw.caps", f"{n} {kind} variant(s) > cap {cap}"))
        over = [x.get("variant_type") for x in variants if len(x.get("iterations") or []) > case["max_data_iterations"]]
        if over:
            v.append(("raw.caps", f"variant(s) with > {case['max_data_iterations']} iterations: {over}"))
    if ds is None:
        return v
    valid, warnings = validate_test_data([ds])
    if not valid:
        v.append(("out.valid", "; ".join(warnings)[:300]))
    _kept, dropped = drop_security_payloads([ds])
    positive = [f.field_name for f in ds.positive_dataset if detect_payload(f.value)]
    if dropped or positive:
        v.append(("out.no_security_payloads", f"payload(s) in generated data: {dropped[:3]} {positive}"))
    if ds.scenario_id != case["scenario"]["scenario_id"]:
        v.append(("out.scenario_id", f"{ds.scenario_id} != {case['scenario']['scenario_id']}"))
    return v


# ── semantic map ─────────────────────────────────────────────────────────────

def run_semantic_map(case: dict, llm) -> Tuple[Any, List[Violation]]:
    from contracts.artifacts import load_payload
    dom = EVALS / "semantic_map" / case["dom_elements"]
    files = {"test_comprehension/business_scenarios.json": {"scenarios": case["scenarios"]},
             "test_comprehension/dom_elements.json": dom}
    with _temp_project(files, patch_modules=("agents.test_creation.semantic_map.agent",)) as pdir:
        from agents.test_creation.semantic_map.agent import SemanticMapAgent
        try:
            SemanticMapAgent(settings={})._llm_map({"project_name": "llmeval"}, {}, llm)
        except Exception as exc:              # noqa: BLE001 — the agent's own validation error
            return {}, [("out.parsed", f"{type(exc).__name__}: {str(exc)[:200]}")]
        out = load_payload("scenario_element_map", str(pdir / "test_creation" / "scenario_element_map.json"))
    return out, []


def check_semantic_map(case: dict, replies: List[str], smap: dict) -> List[Violation]:
    from tools.test_creation.script_generator.build_dom_locator_map import build_locator_map
    v: List[Violation] = []
    _data, v_raw = _first_json(replies)
    v += v_raw
    locators = set(build_locator_map(str(EVALS / "semantic_map" / case["dom_elements"])))
    wanted = {s["scenario_id"] for s in case["scenarios"]}
    unknown = sorted(set(smap) - wanted)
    if unknown:
        v.append(("out.scenarios_known", f"unknown scenario id(s): {unknown}"))
    missing = sorted(wanted - set(smap))
    if missing:
        v.append(("out.all_scenarios_mapped", f"scenario(s) not mapped: {missing}"))
    for sid, data in smap.items():
        els = (data or {}).get("relevant_elements") or []
        bad = [e.get("locator_id") for e in els if e.get("locator_id") not in locators]
        if bad:
            v.append(("out.locators_exist", f"{sid}: locator_id(s) not in dom_elements: {bad}"))
        if not 3 <= len(els) <= 7:
            v.append(("out.element_count", f"{sid}: {len(els)} element(s), want 3-7"))
    return v


# ── script generation ────────────────────────────────────────────────────────

def run_plan(case: dict, llm) -> Tuple[Any, List[Violation]]:
    from agents.common.failure_classifier import LLMResponseValidationError
    from agents.test_creation.script_generation.agent import ScriptGenerationAgent
    agent = ScriptGenerationAgent(settings={})
    agent._tracer, agent._oracles_on = None, True
    try:
        plan = agent._plan_via_llm(case["scenario"], case["allowed_locators"], case["test_data"], case["base_url"],
                                   case.get("flows") or {}, llm, locator_map=case.get("locator_map") or {})
    except LLMResponseValidationError as exc:
        return None, [("out.plan_valid", str(exc)[:300])]
    return plan, []


def check_plan(case: dict, replies: List[str], plan) -> List[Violation]:
    from tools.safety.plan_filter import filter_plan
    from tools.safety.policy import SafetyPolicy
    from tools.test_creation.assertion_linter import lint_plan
    v: List[Violation] = []
    data, v_raw = _first_json(replies)
    v += v_raw
    if plan is None:
        return v
    if isinstance(data, dict) and len(data.get("tests") or []) != len(plan.get("tests") or []):
        v.append(("raw.tests_kept", f"{len(data.get('tests') or [])} test(s) in the reply, "
                                    f"{len(plan.get('tests') or [])} survived the agent's guards"))
    weak = lint_plan(plan)["weak"]
    if weak:
        v.append(("out.assertions_strong", "; ".join(f"{w['name']} ({w['score']}): {w['issues'][:2]}" for w in weak)[:300]))
    policy = SafetyPolicy.from_project_config(case.get("project") or {"environment": "local"})
    _kept, dropped = filter_plan(plan, policy, case.get("locator_map") or {}, case.get("flows") or {})
    if dropped:
        v.append(("out.safe", f"{len(dropped)} test(s) dropped for safety: {[d.get('reason') for d in dropped][:3]}"))
    return v


# ── test design (LLM interpretation) ─────────────────────────────────────────

def run_design(case: dict, llm) -> Tuple[Any, List[Violation]]:
    from pydantic import ValidationError
    from tools.test_design.inputs import DesignInputs
    from tools.test_design.llm import interpret_module, sanitize
    files = {f"test_comprehension/{n}.json": RECORDED_INPUTS / f"{n}.json"
             for n in ("requirements", "business_scenarios", "app_map", "form_model", "api_inventory")}
    with _temp_project(files, BUGGY_SHOP_YAML) as pdir:
        inp = DesignInputs.load(str(pdir), "llmeval")
    try:
        hints = interpret_module(llm, inp, case["module_id"], case["unlinked"])
    except (ValidationError, ValueError, RuntimeError) as exc:
        return None, [("out.schema", f"{type(exc).__name__}: {str(exc)[:200]}")]
    return (hints, sanitize(hints, inp, case["module_id"], [u["id"] for u in case["unlinked"]])), []


def check_design(case: dict, replies: List[str], out) -> List[Violation]:
    v: List[Violation] = []
    _data, v_raw = _first_json(replies)
    v += v_raw
    if out is None:
        return v
    hints, clean = out
    for part in ("decision_tables", "negative_paths", "ac_links", "extra_cases"):
        before, after = len(getattr(hints, part)), len(clean[part])
        if before != after:
            v.append(("out.nothing_dropped", f"sanitize dropped {before - after} of {before} {part}"))
    return v


# ── healing (ADK trajectory from healing_audit.jsonl) ────────────────────────

def check_healing(case: dict, rows: List[dict]) -> List[Violation]:
    from agents.test_execution.healing.tools import _fixed_sleeps, _header_details, _structurally_valid_block
    from tools.healing import identity
    v: List[Violation] = []
    applied: set = set()
    for i, r in enumerate(rows):
        outcome, kind, conf = r.get("outcome"), r.get("kind"), r.get("confidence")
        where = f"row {i} ({kind} {r.get('target')})"
        if kind == "locator_map" and outcome in ("applied", "proposed"):
            if conf is None or conf < identity.THRESHOLD:
                v.append(("traj.identity_applied", f"{where}: {outcome} with identity {conf} < {identity.THRESHOLD}"))
        if outcome == "refused" and conf is not None and conf >= identity.THRESHOLD \
                and "ambiguous" not in str(r.get("evidence", "")).lower():
            v.append(("traj.identity_refused", f"{where}: refused although identity {conf} >= {identity.THRESHOLD} "
                                               "and not ambiguous"))
        if kind == "spec_patch" and outcome in ("applied", "proposed"):
            before, after = r.get("before") or "", r.get("after") or ""
            if not _structurally_valid_block(after):
                v.append(("traj.patch_valid", f"{where}: patched block is not a structurally valid test"))
            if _fixed_sleeps(after) > _fixed_sleeps(before):
                v.append(("traj.no_fixed_sleep", f"{where}: the patch adds a fixed sleep"))
            if _header_details(before) is not None and _header_details(after) != _header_details(before):
                v.append(("traj.trace_header_kept", f"{where}: the test's tag/annotation header changed"))
        if outcome == "reverted" and r.get("target") not in applied:
            v.append(("traj.revert_follows_apply", f"{where}: reverted without an earlier applied heal"))
        if outcome == "applied":
            applied.add(r.get("target"))
        want = "auto" if outcome in ("applied", "verified", "reverted") else "pending"
        if r.get("approver", want) != want:
            v.append(("traj.approver", f"{where}: approver {r.get('approver')!r} for outcome {outcome}"))
    return v


# ── registry ─────────────────────────────────────────────────────────────────

@dataclass
class Task:
    agent: str
    run: Optional[Callable[[dict, Any], Tuple[Any, List[Violation]]]]
    check: Callable[..., List[Violation]]


TASKS: Dict[str, Task] = {
    "requirements": Task("comprehension", run_requirements, check_requirements),
    "scenarios": Task("comprehension", run_scenarios, check_scenarios),
    "test_data": Task("test_data", run_test_data, check_test_data),
    "semantic_map": Task("semantic_map", run_semantic_map, check_semantic_map),
    "plan": Task("script_generation", run_plan, check_plan),
    "design_hints": Task("test_design", run_design, check_design),
    "healing_trajectory": Task("healing", None, check_healing),
}

PROMPT_FILES: Dict[str, List[str]] = {
    "comprehension": ["tools/requirements/prompts.py", "tools/comprehension/prompts.py"],
    "test_data": ["agents/test_creation/testdata/prompt.py", "agents/test_creation/testdata/skills.py"],
    "semantic_map": ["agents/test_creation/semantic_map/prompt.py"],
    "script_generation": ["agents/test_creation/script_generation/prompt.py"],
    "test_design": ["tools/test_design/prompts.py"],
    "healing": ["agents/test_execution/healing/prompt.py"],
}


def evaluate(case: dict, replies: Optional[List[str]] = None, rows: Optional[List[dict]] = None,
             llm=None) -> Tuple[List[Violation], List[str]]:
    """(violations, replies used). With `llm` the agent calls it (live); otherwise the recorded replies are replayed."""
    task = TASKS[case["task"]]
    if task.run is None:
        return task.check(case, rows or []), []
    llm = llm or ReplayLLM(replies or [])
    try:
        out, v = task.run(case, llm)
    except Exception as exc:               # noqa: BLE001 — an eval never crashes the runner
        out, v = None, [("out.crash", f"{type(exc).__name__}: {str(exc)[:200]}")]
    used = llm.replies if isinstance(llm, RecordingLLM) else (replies or [])
    if out is None and not v:
        v = [("out.none", "the agent produced nothing")]
    return v + (task.check(case, used, out) if out is not None or used else []), used


# ── fixtures ─────────────────────────────────────────────────────────────────

@dataclass
class Recording:
    path: Path
    agent: str
    case_name: str
    data: dict = field(default_factory=dict)


def load_case(agent: str, name: str, root: Path = EVALS) -> dict:
    return json.loads((root / agent / "cases" / f"{name}.json").read_text(encoding="utf-8"))


def recordings(root: Path = EVALS, agent: Optional[str] = None) -> List[Recording]:
    out = []
    for p in sorted(root.glob("*/recorded/*.json")):
        a = p.parent.parent.name
        if agent and a != agent:
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        out.append(Recording(p, a, data["case"], data))
    return out


def prompt_hashes(root: Path = ROOT) -> Dict[str, Dict[str, str]]:
    return {a: {f: hashlib.sha256((root / f).read_bytes()).hexdigest() for f in files}
            for a, files in PROMPT_FILES.items()}


def stale(recorded: Dict[str, Dict[str, str]], current: Dict[str, Dict[str, str]]) -> List[str]:
    return [f"{a}: {f}" for a, files in current.items() for f, h in files.items()
            if (recorded.get(a) or {}).get(f) != h]


# ── modes ────────────────────────────────────────────────────────────────────

def replay(root: Path = EVALS, agent: Optional[str] = None, out=print) -> int:
    failed = 0
    for rec in recordings(root, agent):
        case = load_case(rec.agent, rec.case_name, root)
        found, _ = evaluate(case, rec.data.get("replies"), rec.data.get("audit"))
        got, want = {name for name, _ in found}, set(rec.data.get("expect") or [])
        ok = got == want
        failed += not ok
        label = "good" if not want else f"bad, caught {sorted(want)}"
        out(f"[{'ok' if ok else 'FAIL'}] {rec.agent}/{rec.path.stem} ({label})")
        if not ok:
            for name, detail in found:
                out(f"    {name}: {detail}")
            if want - got:
                out(f"    expected but not found: {sorted(want - got)}")
    out(f"{len(recordings(root, agent)) - failed}/{len(recordings(root, agent))} recordings as expected")
    return 1 if failed else 0


def live(agent: Optional[str] = None, record: bool = False, root: Path = EVALS, out=print) -> int:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    from connectors.connector_registry import ConnectorRegistry
    settings = yaml.safe_load((ROOT / "workflows" / "settings.yaml").read_text(encoding="utf-8")) or {}
    llm = ConnectorRegistry(settings).get_llm()
    model = getattr(llm, "model", None) or type(llm).__name__
    violations = 0
    for case_path in sorted(root.glob("*/cases/*.json")):
        a = case_path.parent.parent.name
        if agent and a != agent:
            continue
        case = json.loads(case_path.read_text(encoding="utf-8"))
        if TASKS[case["task"]].run is None:
            out(f"[skip] {a}/{case_path.stem}: the ADK tool loop has no single prompt call — record its "
                "healing_audit.jsonl with the healing benchmark and add it under recorded/")
            continue
        rec_llm = RecordingLLM(llm)
        found, used = evaluate(case, llm=rec_llm)
        violations += len(found)
        out(f"[{'ok' if not found else 'FAIL'}] {a}/{case_path.stem} ({len(used)} call(s))")
        for name, detail in found:
            out(f"    {name}: {detail}")
        if record:
            dest = root / a / "recorded" / f"{case_path.stem}__live.json"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps({"case": case_path.stem, "replies": used, "expect": sorted({n for n, _ in found}),
                                        "source": f"live {model} {date.today().isoformat()}"}, indent=2,
                                       ensure_ascii=False) + "\n", encoding="utf-8")
    if record:
        stamp(root)
    return 1 if violations else 0


def stamp(root: Path = EVALS) -> None:
    (root / "prompt_hashes.json").write_text(json.dumps(prompt_hashes(), indent=2) + "\n", encoding="utf-8")


def check_stale(root: Path = EVALS, out=print) -> int:
    try:
        recorded = json.loads((root / "prompt_hashes.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        recorded = {}
    changed = stale(recorded, prompt_hashes())
    for c in changed:
        out(f"prompt changed since the last recorded eval: {c}")
    if changed:
        out("re-run: python -m tools.selftest.llm_evals --live --record  (or --stamp after reviewing the replays)")
    return 1 if changed else 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip())
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--replay", action="store_true")
    mode.add_argument("--live", action="store_true")
    mode.add_argument("--check-stale", action="store_true")
    mode.add_argument("--stamp", action="store_true")
    ap.add_argument("--agent", choices=sorted(PROMPT_FILES))
    ap.add_argument("--record", action="store_true", help="--live: save the replies under recorded/ and re-stamp")
    args = ap.parse_args(argv)
    os.chdir(ROOT)
    if args.replay:
        return replay(agent=args.agent)
    if args.live:
        return live(args.agent, args.record)
    if args.stamp:
        stamp()
        print(f"stamped {HASHES}")
        return 0
    return check_stale()


if __name__ == "__main__":
    sys.exit(main())
