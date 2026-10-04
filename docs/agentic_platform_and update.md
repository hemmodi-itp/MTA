# Agentic QA Platform V2 — Full Google ADK Migration (Epic/Story Backlog)

> First action on approval: persist this document to `docs/adk_migration_plan.md` in the repo so it lives with the codebase, not just in the local plan-file location.

## Context

The platform today is a deterministic, YAML-driven workflow engine. A human picks a workflow via
`main.py --workflow <name>`; `OrchestratorAgent.run()` dispatches a fixed step DAG across 14
registered agents, each of which implements a single `execute(request, state)` method with an
optional tiered fallback ladder (`agents/common/fallback_core.py` + `failure_classifier.py`).
Exactly one agent — `HealingAgent` — is already a real, production Google ADK agent (`LlmAgent`
wrapped in a `LoopAgent`, diagnose → repair → verify → escalate), proving the pattern works end to
end on this codebase's actual LLM backend (Bedrock/Claude via LiteLLM, since `connectors.llm: aws`
is the active setting and stays that way).

The user has decided to migrate the **entire platform** to this ADK-native shape — not additively,
with no backward-compatibility requirement. `BaseAgent`, the `--workflow` CLI flag, `agent.json`'s
schema, and the org's category mandate (CLAUDE.md) are all in scope to be replaced or rewritten
where the new architecture calls for it. Healing's existing ADK implementation is the reference
pattern to *extract and generalize*, not rebuild. A new, fully autonomous **Test Planner Agent**
becomes the new top-level entrypoint, replacing manual workflow selection — it decides what to run
and directly triggers execution, with no human checkpoint by explicit decision.

This doc is the complete epic/story backlog for that migration, grounded in a file-by-file reading
of all 14 existing agents, the orchestrator, the LLM connector layer, and `project_state.json`'s
real shape — not a hypothetical rewrite.

## Decisions locked in

| Question | Decision |
|---|---|
| Backward compatibility | **None required.** Replace `BaseAgent`, the CLI, `agent.json` schema, and CLAUDE.md's mandate language wherever the new design calls for it. |
| Test Planner Agent location | `agents/orchestrator/test_planner/`, alongside `OrchestratorAgent`. CLAUDE.md's "kept flat since it's already 1:1" line for `agents/orchestrator/` gets rewritten. |
| Planner authority | **Fully autonomous from day one** — the Planner directly constructs and calls `OrchestratorAgent.run()`, no human-in-the-loop gate. |
| LLM backend | Stays `aws`/Bedrock via the LiteLLM bridge already proven by Healing. ADK is adopted as the lifecycle/tool-calling framework, not a reason to move to Gemini. |
| Healing agent | Already ADK-native — treated as the **reference pattern to extract a shared base from**, not rebuilt. |

## What corrects prior assumptions

- HealingAgent's ADK loop is **already wired into `full_workflow.yaml`** (step 6, `depends_on: [ui_execution]`) and running in production today on Bedrock via LiteLLM — it is the working proof this migration generalizes, not a green-field integration.
- `google-adk>=1.0.0` (v2.3.0 installed) and `google-genai` are already real, installed dependencies — no new SDK to add.
- Only 3 workflow YAMLs exist today (`full_workflow`, `execution_only`, `ns_workflow`); the proposal's other named workflows don't exist yet — authoring them (Epic 16) is plain YAML, decoupled from the ADK work itself.
- "Confidence" today is a cosmetic literal (`0.75`/`0.95`) tagged onto synthesized scenarios in discovery — never computed from a real signal anywhere except Healing, which computes a genuine heal ratio (`tests_healed` / `remaining_total()`) and then **discards it**, reporting only a status enum. Surfacing that one number is the cheapest real win in the whole plan.
- `run_history[].workflow` in `project_state.json` is a pre-existing bug — always empty string, never populated.
- `agents/test_creation/artifact_generator/` is currently missing its `agent.json` entirely — a pre-existing mandate violation to fix during its migration, not caused by this plan.

---

## Target end-to-end flow (what "done" looks like)

User drops a new BRD into a project and runs the new entrypoint — no `--workflow` flag exists anymore:

```
python main.py --project myproject --goal "onboard new BRD for the checkout module"
```

1. **Observe** — `TestPlannerAgent` loads `project_state.json` (via the existing `psm.load()`) and `project.yaml`, detects the BRD fingerprint changed vs. `project_state["discovery"]["brd_fingerprint"]` — reusing the exact fingerprint machinery `OrchestratorAgent` already uses reactively, except checked proactively, before any workflow is chosen.
2. **Skill 1 — QA Strategy Generation** — one LLM call (via `resolve_adk_model()`, same Bedrock connector every agent uses) over the new BRD text + `project_state["gaps"]`, emitting `strategy.yaml` (new artifact, written adjacent to `project_state.json`, not inside it).
3. **Skill 2 — Workflow Resolution** — maps "new module, zero coverage, fingerprint changed" → `full_workflow` (chosen from the *named, pre-authored* DAGs in Epic 16 — the Planner selects among fixed workflows, it does not synthesize an ad hoc step list at runtime; safer and auditable, at the cost of not covering every possible need with a named workflow).
4. **Skill 3 — Execution Planning** — reads `test_cases`/`new_additions`/`gaps` to build the same `request_payload` shape (`module_filter`, `force_rediscover`, `suite`) `main.py` builds by hand today — pure reuse of existing `psm` gap-tracking.
5. **Complete → autonomous dispatch** — the Planner directly instantiates `OrchestratorAgent` and calls `.run(request_payload, full_workflow_definition)` — the one sanctioned direct agent-to-agent call in the whole platform, tagged `planner_invoked=True` on `WorkflowState` for audit.
6. **`OrchestratorAgent.run()` executes the 7-step DAG exactly as today's dispatch loop already does** — but now every step follows the shared Observe→Plan→Skill→Tool→Reflect→Confidence→Complete lifecycle (Epic 0), the Policy Engine (Epic 14) checks required-artifacts pre-step and real confidence thresholds post-step (able to halt *before* burning script-generation/execution cycles on a low-confidence discovery pass — something today's binary `status` field can't express), and results merge into `project_state.json` including new `confidence_history`/`strategy_history` entries (Epic 15), finally populating the long-broken `run_history[].workflow` field.
7. **Reporting** runs unconditionally (`always_run: true`) and produces the final report, unchanged in shape.

---

## Epic backlog

Numbered for reference; dependency graph and suggested execution waves follow at the end.

### EPIC 0 — Shared ADK Agent Lifecycle Base (replaces `BaseAgent` entirely)

Foundation for every other epic. Extracts Healing's proven pattern into a platform-wide contract.

- **0.1** — New `agents/adk_base.py::AdkAgentBase(ABC)` with named stage methods (`observe`, `plan`, `run_skills`, `run_tools`, `reflect`, `score_confidence`, `complete`), each with a sane no-op default so Python-first agents (Discovery, Reporting) can skip stages that don't apply. `complete()` returns the same `{"module","status",...}` shape `OrchestratorAgent` already consumes, plus a new required `confidence: float` field (Epic 17).
- **0.2** — Retire `execute_with_fallback`'s exception-routing (`agents/common/fallback_core.py`, `failure_classifier.py`, RETRY/NS_HTTP/ALT_MODEL/FALLBACK/HUMAN_REVIEW). In-agent retry/self-correction becomes `LoopAgent(max_iterations)` + an explicit escalate tool, exactly Healing's diagnose→repair→verify→escalate shape. Cross-agent fallback (NS_HTTP / python_stub) stays exactly where it already correctly lives — in `workflows/agent_registry.yaml`, dispatched by `OrchestratorAgent._try_with_fallbacks` — this separation already half-exists in the current code; 0.2 makes it total. **Decision: `HUMAN_REVIEW`/`flag_for_human_review()` (`agents/common/review_queue.py`, `human_review_queue.json`) is retired outright, not preserved via an escalate tool** — consistent with the platform-wide "fully autonomous, no human checkpoint" decision. Every escalate path (Healing's `mark_not_healable`, and any new agent's equivalent) now falls through to the Policy Engine's stop/degrade/retry policy (Epic 14) instead of a human queue. Remove `review_queue.py` and its call sites as part of this story rather than leaving dead code behind.
- **0.3** — Extract Healing's `_drive_loop`/`InMemoryRunner` boilerplate into a shared `agents/adk_runtime.py::run_llm_agent(agent_or_loop, kickoff_text, app_name)` so no future agent copy-pastes the asyncio bridge.
- **0.4** — Extract Healing's `tools.py::build_tools(ctx)` + `RunContext`-closure convention into a documented base shape other agents' `tools.py` follow *only when they actually have an LLM/tool-caller* — agents with zero LLM calls (Reporting, Locator) should NOT be forced into this shape just for consistency.
- **0.5** — Extend `agent.json` schema (new fields: `lifecycle_stages`, `confidence_method`, `memory_scope`, `loop_config`) and rewrite CLAUDE.md's schema block accordingly. Update `tools/scaffold_agent.py`, which currently emits the pre-ADK skeleton with zero ADK awareness, to generate the new shape.

**Depends on**: nothing. **Blocks**: every other epic.
**Pros**: makes a generic Policy Engine and generic confidence scoring possible at all; removes ~12 copies of bespoke retry code.
**Cons**: touching the base every agent inherits from is a big-bang-adjacent change — sequence per-agent migrations carefully behind it (see waves below) rather than flipping everything at once; collapsing `fc.classify`'s 5 distinct routes into "loop or escalate" is coarser and may lose a real signal (transient vs. model-quality vs. needs-human) if 0.2's open question isn't resolved deliberately.

---

### EPIC 1 — HealingAgent: integration & generalization (not a rebuild)

Healing is the reference implementation; this epic is purely extraction, no behavior change.

- **1.1** — Pull `_run_adk_healing`/`_drive_loop` into Epic 0.3's shared runtime; Healing becomes the first, not the only, caller.
- **1.2** — Generalize `HealingRunContext`/`build_tools(ctx)` into Epic 0.4's base `RunContext` shape (project_name/settings/logger + a `close()` hook for resources like the Playwright executor).
- **1.3** — Establish the `prompt.py` naming/structure convention from `SUPERVISOR_INSTRUCTION`'s shape (Workflow / Hard rules / termination condition) as the template other agents' prompts are diffed against.
- **1.4** — Add a `confidence` field to `_apply_patch`'s return, derived from which repair path resolved the failure (live-DOM-resolved locator = high, regex substitution = high, test-data mismatch = medium) — additive, no existing field changes.
- **1.5** — Surface the already-computed heal ratio as real confidence: `confidence = tests_healed / max(tests_healed + remaining_total(), 1)` added to the existing return dict — near-zero cost, the cheapest win in this whole plan (Epic 17 depends on this specifically, not on Epic 0).
- **1.6** — Write down `HealingAgent.tools.py::_run_tests`'s exact read contract on `UIExecutionAgent.execute()`'s return shape (`status`, `results[].{spec_file,test_title,status,errors,comment}`) as a literal regression check — this is the tightest coupling point in the whole migration and needs a concrete target before Epic 2 touches UIExecutionAgent.

**Depends on**: Epic 0 (for 1.1/1.2's extraction target), but 1.5 (confidence surfacing) has zero dependency and can ship immediately.
**Pros**: near-zero risk, unblocks every other agent's convergence, proven code shape.
**Cons**: extracting a base class from exactly one real example risks over-fitting to Healing's specific shape — don't over-generalize until a second real caller (Epic 12, ScriptGeneration) exists.

---

### EPIC 2 — UIExecutionAgent: Tool-only lifecycle wrapper, deliberately no LLM

- **2.1** — Map existing structure onto Observe→Execute Tool→Reflect→Complete with **no Plan/Skill stage**: suite/spec_files resolution = Observe; `_run_playwright`/`_run_pytest_compat` = Execute Tool; browser-close reclassification, headless-switch heuristic, interrupt-recovery = Reflect.
- **2.2** — Document explicitly in `agent.md` *why* no `LlmAgent`/`LoopAgent` is introduced here: Playwright's own engine resolves whatever locator is already hardcoded in the generated spec; the one place runtime locator-strategy reasoning already exists is `HealingAgent.propose_locator_fix`, which runs *after* a failure — injecting an LLM into this hot path puts a non-deterministic decision-maker in front of real, irreversible side effects (clicks, form submits, live navigation) for no documented benefit.
- **2.3** — Preserve Epic 1.6's output contract exactly — this is the actual regression gate for this epic.
- **2.4** — Extract the browser-close/headless-switch/interrupt-recovery heuristics (currently inline in `agent.py`) into `tools.py` as named, unit-testable Python functions — not because ADK needs `FunctionTool` here (there's no LLM calling them), but because Epic 0.4's "RunContext + tool module" shape should be the org convention for deterministic-heavy agents too.
- **2.5** — Mark `confidence: "not_applicable"` explicitly in `agent.json` rather than fabricate a number — Playwright pass/fail is already binary and authoritative.

**Depends on**: Epic 0 (lifecycle shape) and Epic 1.6 (contract to preserve).
**Pros**: lowest-risk epic in the whole plan — zero behavior change. **Cons**: high-consequence side effects (process-tree killing, live-login credential capture) mean any accidental contract drift silently breaks Healing's verify loop — needs a real regression test, not just doc discipline.

---

### EPIC 3 — LocatorAgent: Tool-only, confidence-scored DOM matching

- **3.1** — Observe→Execute Tool→Complete, no Plan/Skill/Reflect — there is no LLM call and no loop today.
- **3.2** — Make the existing 3-tier match order (exact → normalized → substring) an explicit confidence score (`1.0`/`0.8`/`0.5`) per patched intent instead of silently overwriting `locator_id` — gives the new `agent.json` confidence field real, grounded data.
- **3.3** — **Concrete dedup opportunity found while reading the code**: extract `HealingAgent.propose_locator_fix`'s DOM-ranking helpers (`_rank_candidate_elements`/`_element_text_blob`) into a shared `tools/dom_matching.py` both LocatorAgent and HealingAgent import — they independently solve "find the DOM element matching this named intent" today with two different algorithms.
- **3.4** — Only if 3.2 reveals real ambiguity (ties, or meaningful fraction of intents below 0.8 confidence) — consider a bounded, single-pass LLM Skill for tie-breaking. **Not committed** — nothing in the current code demonstrates this need; flagged as a candidate to resist building speculatively, per the platform's Python-first principle.
- **3.5** — Resolve whether LocatorAgent's absence from `full_workflow.yaml`'s step list (registered but not dispatched by default) is intentional or a gap — a one-line decision record, not a migration risk.

**Depends on**: Epic 0. **Independent of every other agent epic** (zero dependencies in its own `agent.json`) — freely parallelizable.
**Pros**: 3.3's dedup is a real quality win surfaced by this review, not speculative. **Cons**: 3.4 is the epic's scope-creep risk — resist adding an LLM without a demonstrated ambiguity problem.

---

### EPIC 4 — ReportingAgent: Tool-only terminal node, near-zero migration surface

- **4.1** — Observe→Execute Tool→Complete, explicitly `lifecycle_stages: ["observe","execute_tool","complete"]`, `confidence: not_applicable`, `memory: none` — this agent has no genuine ambiguity or iteration; adding Plan/Skill/Reflect/Confidence stages would be pure schema-filling with no behavioral grounding.
- **4.2** — Delete the stale `agent.md` reference to `fallback_core.fallback_report()`, which `reporting/agent.py` never actually calls and `agent_registry.yaml`'s `reporting:` entry never configures — confirm no other live caller exists before considering removing the function itself.
- **4.3** — Confirm Epic 0.4's "RunContext + tool module" convention is opt-in (only for agents with an LLM/tool-caller), not universal — Reporting's `tools.py` re-exports pure functions with zero context wiring, correctly, and shouldn't be forced into unnecessary boilerplate.

**Depends on**: Epic 0. **Independent** (no other-agent coupling).
**Pros**: essentially risk-free, mechanical. **Cons**: 4.2's cleanup needs a quick repo-wide grep to confirm zero other callers before removal — not a design risk, but shouldn't be skipped.

---

### EPIC 5 — ExecutionAgent: thin wrapper, real consolidation decision required

- **5.1** — Observe→Execute Tool→Complete: `_run_ui_execution` = Execute Tool; `_extract_failures`/`_classify_error`'s substring-based classification = a second deterministic Tool step, explicitly kept out of the LLM per the Python-first principle.
- **5.2** — **Real decision, not just a migration**: `ExecutionAgent` is dead in the default `full_workflow.yaml` (which calls `UIExecutionAgent` directly under the step name `ui_execution`, bypassing this wrapper entirely) — it exists only for `execution_only.yaml`. Given no-backward-compat, decide explicitly: (a) keep it as a documented alternate entrypoint for that one workflow, migrated per 5.1; or (b) fold `_classify_error`'s taxonomy into `UIExecutionAgent` or a shared `tools/execution/failure_classification.py` and retire `execution_only.yaml`'s dependency on a separate class. **Needs a stakeholder check on who actually runs `execution_only.yaml` today before deciding** — this is the one judgment-risk story in an otherwise mechanical epic.
- **5.3** — If kept: extract `_classify_error`'s 6-way taxonomy into `tools.py` (currently a stub) — and evaluate feeding its output into Healing's diagnosis prompt, which already hand-authors a parallel, less-precise taxonomy of failure types.

**Depends on**: Epic 0, and is sequence-coupled with Epic 2 (both touch the `UIExecutionAgent` call contract) — schedule in the same batch.
**Pros**: small mechanical surface. **Cons**: 5.2 is a real product decision, not a code-shape decision — don't silently carry the wrapper forward just because it exists.

---

### EPIC 6 — ComprehensionAgent: 2 real ADK Skills

- **6.1** — Wrap `extract_requirements(doc, llm)` as Skill 1 — genuine unstructured-text reasoning (BRD prose → Requirement/BusinessRule/Actor/Workflow), invoked once per document inside the existing per-document loop.
- **6.2** — Wrap `generate_business_scenarios(...)` as Skill 2 — batched synthesis from the day's extracted requirements, keeping the existing `existing_scenarios` de-dup hint as skill input.
- **6.3** — Move `parse_all_documents`/`validate_business_scenarios`/`export_scenarios`/`load_existing_titles_by_module` into `tools.py`'s Tool surface unchanged — already pure Python.
- **6.4** — Populate the currently-unused `skills.py` stub with the two real Skills above.
- **6.5** — Collapse `_execute_flat`/`_execute_modular` into one Observe→Plan structure where "Plan" is deterministic module-list resolution (driven by whether `request["modules"]` is present) — not an LLM call; the branch itself is unambiguous.
- **6.6** — Keep the current no-fallback-ladder design (bare `try/except`) — `DiscoveryAgent` one layer up already implements the real fallback (rule-based DOM synthesis); a second ladder here would duplicate that responsibility.

**LoopAgent verdict**: single-pass, no loop — extraction and generation are one-shot transforms with no verify/retry cycle.
**Depends on**: Epic 0. **Blocks**: Epic 7 (Discovery calls this agent directly via plain Python import, not registry — the two epics' `execute()` contracts must be co-migrated or the call site breaks).
**Pros**: one of only two agents in scope (with ScriptGeneration) doing real, irreducible reasoning over unstructured prose — a clean Skill candidate, not overhead. **Cons**: two serial LLM calls per document through ADK's full session/runner machinery adds asyncio-bridge overhead versus today's simple synchronous call — keep these as direct single-turn Skill invocations, not multi-turn tool-calling loops (there's nothing here for a model to call a *tool* for).

---

### EPIC 7 — DiscoveryAgent: stays Python-first, no invented LLM step

- **7.1** — Keep mode-selection (`has_url`/`has_brd`) as pure deterministic Python — do not invent an LLM "Plan" step just to satisfy the lifecycle shape; this is not an ambiguous judgment call.
- **7.2** — Formalize `_run_dom_scan`/`_run_comprehension`/`_save_intents_yaml`/`_check_mandatory_outputs` as Tools.
- **7.3** — **Explicitly reject** replacing the hand-rolled `threading.Thread`/timeout/checkpoint-promotion parallelism with ADK's `ParallelAgent` — ADK's primitive has no equivalent to the per-branch timeout + partial-checkpoint-promotion semantics that are load-bearing here; swapping it would be a regression, not a migration.
- **7.4** — `skills.py` stays an explicit, documented stub — this agent has no reasoning of its own to formalize.
- **7.5** — Add an `agent.json` marker (`"lifecycle": "python_first"`) so the org's own token-optimization principle is visible at a glance, not just tribal knowledge.

**LoopAgent verdict**: not applicable — DiscoveryAgent has no direct Skill calls; at most it becomes a plain Python orchestrator composing Epic 6's Skill-bearing ComprehensionAgent with DOM-scan Tools.
**Depends on**: Epic 6 (direct call site).
**Pros**: uniform lifecycle wrapper makes orchestrator-level introspection consistent even for a Python-only agent. **Cons**: this is the platform's best example of "resist ceremony" — forcing Observe/Plan/Skill/Tool/Reflect stages around an if/elif dispatcher for consistency's sake is exactly the anti-pattern the token-optimization principle warns against; keep this agent's lifecycle footprint minimal on purpose.

---

### EPIC 8 — TestDataAgent + SemanticMapAgent (grouped: near-identical structure)

- **8.1** — Wrap each agent's Tier-0 primary call as an ADK Skill: TestDataAgent keeps its existing `ThreadPoolExecutor` per-scenario fan-out (ADK doesn't need to own that parallelism); SemanticMapAgent keeps its single batched call over all scenarios (an explicit design goal in its own docstring, to avoid dumping all DOM elements into every downstream call).
- **8.2** — Keep Tiers 1/1b/2 (NS HTTP, alt-model, Python-only fallback) as plain Python, unchanged — ADK's model abstraction has no equivalent to "call a different HTTP microservice" or "regenerate with zero LLM calls," so these stay outside the Skill boundary by design. **Fallback decision: keep the 4-tier ladder for both** — it encodes real, tested domain routing knowledge (rate-limit → retry-then-NS, auth → NS immediately, bad JSON → retry-then-fallback) ADK's own retry semantics don't replicate.
- **8.3** — TestDataAgent: promote its existing `AgentSkill` metadata (currently just a prompt-header string) to be the real Skill's identity/instruction source.
- **8.4** — SemanticMapAgent: create a real Skill entry in its currently-stub `skills.py` — genuine reasoning here (mapping scenario intent → 3–7 relevant DOM elements) deserves the same formalization TestDataAgent already partially has.
- **8.5** — Keep SemanticMapAgent's post-hoc authoritative-locator overwrite (`_enrich_locator_exprs`) as a deterministic Tool that runs *after* the Skill call, unchanged — the existing "never trust the LLM's locator string" guardrail must not weaken.
- **8.6** — Confidence: TestDataAgent already computes `coverage_pct`/`coverage_warning` — promote directly to confidence rather than inventing a new metric. SemanticMapAgent derives confidence from the fraction of relevant elements that got a non-null authoritative locator from 8.5.

**LoopAgent verdict**: single-pass for both — no cross-iteration feedback in TestData's fan-out, and SemanticMap is by design exactly one call.
**Depends on**: Epic 0. **Blocks**: Epic 12 (ScriptGeneration reads both agents' output files).
**Pros**: both already have a clean primary/fallback boundary, so ADK-izing just the primary hop is low-risk and reuses Healing's model-resolution code directly. **Cons**: TestDataAgent's concurrent fan-out means multiple concurrent ADK sessions if each Skill call spins up its own runner like Healing does — confirm the shared runner (Epic 0.3) is safe under concurrency, or share one runner across the pool; this is new operational risk Healing's single-session pattern never faced.

---

### EPIC 9 — ArtifactGeneratorAgent: fix pre-existing gap + 2 Skills

- **9.1** — Create the currently-missing `agent.json` (pre-existing mandate violation, unrelated to this migration but fixed in the same pass) — recommend one manifest with a `"variants": ["intents","testcases"]` field rather than splitting folders, since the mandate's "no shared folder" rule concerns classes, and this remains one class with two constructor-bound registry keys via `functools.partial`.
- **9.2** — Wrap `generate_intents` and `generate_test_cases` as two Skills sharing the one existing `skills.py` entry as their instruction source — `mode` selects which Skill+Tool pair runs, mirroring today's branch.
- **9.3** — Formalize the already-mostly-re-exported deterministic functions (`_apply_dom_locators`, `enrich_with_testdata`, `validate_artifacts`, `generate_suite`, export functions) as the Tool surface.
- **9.4** — Accept "fail fast, no fallback ladder" as the intentional design for now, documented in `agent.json` — this agent is not in the default `full_workflow.yaml`; don't invest in new `fallback_core` machinery for an unwired path.

**LoopAgent verdict**: single-pass, both modes are one-shot batch generations.
**Depends on**: Epic 0; conceptually downstream of Epic 6, feeds Epic 11 — but since neither is in the active workflow, this is design-only ordering, not execution-critical.
**Pros**: the two-mode pattern maps cleanly onto "two Skills, one Tool module, one manifest" without restructuring folders. **Cons**: zero fallback today and currently dormant — real risk of over-investing ADK retry/loop machinery into a path nothing calls; keep this epic's ADK work to Skill-wrapping only until it's wired into a real workflow.

---

### EPIC 10 — BDDAgent: design-only, defer implementation

- **10.1** — Design-only: decide the target ADK shape (single-pass Skill: business scenario → Gherkin phrasing; Tool: deterministic `.feature` file writer; no loop) so that whenever real logic lands it drops into the same lifecycle as its siblings — do not fabricate business logic the code doesn't have (it's a literal stub today, `{"status": "stub"}`).
- **10.2** — Distinguish in `agent.json`'s `status` field between "stub, not yet migrated" and "stub, ADK-shape-defined-but-unimplemented" so this doesn't silently block a repo-wide "migration complete" checklist.

**Depends on**: nothing. **Pros**: cheapest agent to design correctly, no legacy behavior to preserve. **Cons**: without real product requirements, resist over-engineering a stub — schedule last.

---

### EPIC 11 — SemanticDedupAgent: the org's reference example, fixed in place

The org mandate (CLAUDE.md) names `dedup/` the canonical template — today it's structurally weak (stub `skills.py`/`tools.py`, bare `try/except` with no real tool-calling). This epic fixes the *template itself*, which matters beyond this one dormant agent.

- **11.1** — **Explicit recommendation: do NOT force a `LoopAgent`/tool-calling loop here.** There is nothing to call a tool for (the JSON-extraction regex already works deterministically) and nothing to verify/iterate on — the LLM's duplicate/new classification *is* the answer; unlike Healing, there's no ground-truth oracle in the same run to loop against. A loop would just re-ask the same question, burning tokens for zero signal.
- **11.2** — Wrap the single `generate()` call as one ADK Skill (single-turn `LlmAgent`, no tools, no loop) — real-izing the currently-unused `skills.py` stub.
- **11.3** — Extract `_format_tc_list`/`_parse_dedup_response` (currently inline module functions) into `tools.py` as real, testable functions.
- **11.4** — Formalize the deliberate fail-open behavior as an explicit Reflect/Confidence outcome: on Skill failure, emit `confidence=0.0`, `status="degraded"` (replacing the current bare `except Exception` → `status: "partial"`), while preserving the exact same fail-open guarantee (`approved=proposed`) — documented prose, not just code, since this agent's failure-mode doc is as important as its logic.

**LoopAgent verdict**: single-pass, explicitly not a loop — no oracle exists within a single run to check the LLM's own judgment against.
**Depends on**: Epic 0. **Independent** of every other agent (takes plain request-dict inputs).
**Pros**: because this is the mandate's chosen reference example, fixing it correctly sets the template every future scaffolded agent is compared against — the investment pays off repo-wide even though the agent itself is dormant. **Cons**: over-engineering it (retry ladders, memory, a loop) risks teaching future agent authors the wrong lesson — it should stay the *minimal* example (one ambiguous judgment call, otherwise deterministic), not the most elaborate one.

---

### EPIC 12 — ScriptGenerationAgent: the one genuine `LoopAgent` candidate besides Healing

Structurally the most complex of the non-Healing agents — it already implements a real
generate→live-verify→retry cycle today (static locator check → live Playwright dry-run → one
retry with a hint → deterministic Python fallback).

- **12.1** — Wrap the primary generation call as an ADK Skill (same shape as Epic 8's Tier-0).
- **12.2** — Formalize the existing verify-retry sub-flow as a **bounded `LoopAgent(max_iterations=2)`** — directly subsumes the hand-rolled "one retry with a hint" code into Healing's exact diagnose→repair→verify shape (diagnose = live locator check, repair = re-invoke Skill with retry hint, verify = live locator check again). **Cap at 2, matching current behavior — do not silently widen into an open-ended loop during migration.**
- **12.3** — Port the live-Playwright validation-page lifecycle (lazy per-module headless `Page`, explicit cleanup) into an ADK tool closure using the **same sync/async-bridge pattern Healing's `RunContext`/`pw_executor()` already solved** — flagged as real migration risk, not a trivial wrap, since Playwright's sync API cannot run inside the same event loop ADK's runner uses. Get this reviewed against Healing's solution specifically, not independently reinvented.
- **12.4** — Keep the outer "one spec per scenario" fan-out as a plain Python `for` loop — scenarios are independent and share no iterative state across each other.
- **12.5** — Keep the per-scenario tiered fallback classifier exactly as today; only the "no override" branch becomes "invoke the ADK Skill" — NS/alt-model/Python-fallback branches stay untouched Python.
- **12.6** — Migrate module-setup-injection and locator-regex enforcement logic into `tools.py` as deterministic Tools — none of it involves reasoning and it already lives at module level, ready to lift.

**LoopAgent verdict**: **yes** — the one clear `LoopAgent` candidate besides Healing, because unlike every other one-shot agent in scope, this one *already* implements a real verify-retry cycle; adopting `LoopAgent` formalizes existing, tested behavior rather than adding new ceremony.
**Depends on**: Epic 8 (reads TestData/SemanticMap output), Epic 1 (mirrors Healing's tool-closure pattern for the live-Playwright piece). **Downstream coupling**: its output format (spec files + `test_suite.json`) must stay byte-compatible with what Healing already parses.
**Pros**: of all agents in scope, adopting `LoopAgent` here is genuinely additive, not overhead — it already pays the cost of a verify-retry cycle in hand-rolled form. **Cons**: the live-browser validation-page state is the single riskiest piece of state to move into an ADK tool closure in this entire migration — do not treat 12.3 as routine.

---

### EPIC 13 — Test Planner Agent + new entrypoint

- **13.1** — Skill 1, QA Strategy Generation — reads BRD/module docs + `project_state.json`'s `summary`/`gaps`, emits `strategy.yaml` (new artifact, adjacent to `project_state.json`, one new `artifact_registry.json` entry per project).
- **13.2** — Skill 2, Workflow Resolution — maps strategy + fingerprint deltas to one of the *named* workflow YAMLs (existing 3 + Epic 16's new 5). Deliberately selects among pre-authored DAGs rather than synthesizing steps at runtime — safer and auditable, at the cost of not covering every possible need with a named workflow.
- **13.3** — Skill 3, Execution Planning — reads `test_cases`/`new_additions`/`gaps`/`run_history` to build the same `request_payload` shape `main.py` builds by hand today (`module_filter`, `force_rediscover`, `suite`, `force_execute`) — pure reuse of existing `psm` machinery, no new state-reading code.
- **13.4** — **Autonomous dispatch**: Planner's Complete stage directly instantiates `OrchestratorAgent` and calls `.run(request_payload, workflow_definition)` — the one sanctioned exception to "agents never call each other directly." Add `planner_invoked: bool` / `strategy_ref` to `WorkflowState` so this is always auditable.
- **13.5** — New top-level entrypoint replacing `--workflow` entirely: `--project` + freeform `--goal`, with override flags (`--force-rediscover`, `--module`) that Execution Planning must respect if present. Add `--dry-run`/`--explain` to print the Planner's chosen workflow + params *without* executing — necessary given full autonomy with zero human checkpoint.
- **13.6** — Rewrite CLAUDE.md's `agents/orchestrator/` description — it now holds two agent folders (`OrchestratorAgent`, still `registry_key: null`; `TestPlannerAgent`, likely also `registry_key: null` since it's constructed directly, not registry-dispatched).

**Depends on**: Epic 0 (Planner is itself ADK-native), Epic 16 (needs real workflow choices), loosely Epic 14 (autonomy is safer with a policy backstop downstream).
**Pros**: turns the platform from flag-driven to goal-driven; Execution Planning is nearly free since it reuses existing gap-tracking. **Cons — flagged explicitly, not hidden**: full autonomy with a direct `OrchestratorAgent.run()` call and zero human checkpoint means a bad Workflow Resolution call burns an entire discovery→execution cycle before anyone notices; the Policy Engine (Epic 14) only gates *within* a chosen run, not the choice itself; dropping `--workflow` is a breaking change for any CI/script invoking `main.py` directly today (acceptable per the no-backward-compat decision, but must be communicated to whoever owns CI).

---

### EPIC 14 — Policy Engine inside the Orchestrator

Deterministic, no-LLM gating, replacing today's hardcoded `if/else` branching in `OrchestratorAgent.run()` with declarative config.

- **14.1** — New `agents/orchestrator/policy_engine.py::PolicyEngine`, loaded from a new `workflows/policy.yaml`, consulted at two hook points: **pre-step** (verify declared `required_artifacts` exist — generalizing today's ad hoc discovery-fingerprint-skip and execution-narrowing checks into one mechanism) and **post-step** (read the step's real `confidence` against a per-step threshold, branch to retry/degrade/escalate/stop — replacing today's binary status-only branching).
- **14.2** — `policy.yaml` schema + loader, e.g.:
  ```yaml
  policies:
    script_generation:
      confidence_threshold: 0.7
      on_below_threshold: retry
      max_retries: 1
      required_artifacts: [scenario_element_map_path, test_data_path]
      on_missing_artifact: stop
    defaults:
      confidence_threshold: 0.5
      on_below_threshold: degrade
  ```
- **14.3** — Wire confidence-threshold gating to Epic 17's real per-step confidence values.
- **14.4** — Add a `policy_trace` list to `WorkflowState` (parallel to `execution_trace`) logging every policy decision — the critical safety net given Epic 13's fully-autonomous Planner has no other oversight mechanism.
- **14.5** — Watch for fit mismatches during extraction: discovery's fingerprint-based skip is a change-detection optimization, not really an "artifact missing" check — it may need its own policy category rather than being forced into the same `required_artifacts` shape as everything else.

**Depends on**: Epic 0 (uniform result shape) and Epic 17 (real confidence) to be more than an artifact-presence checker; matters most once Epic 13 exists.
**Pros**: makes branching data-driven and testable; gives the autonomous Planner a deterministic backstop between "workflow chosen" and "workflow ran unsupervised to completion." **Cons**: by design it's no-LLM — catches threshold/shape problems, not semantic ones (a confidently-wrong discovery output sails through); adds a *third* governing YAML alongside `agent_registry.yaml`/`agents.yaml` — real configuration-sprawl risk.

---

### EPIC 15 — Memory Layer

- **15.1** — **Working memory (new)**: add `working_memory: Dict[str, Any]` to `WorkflowState` — a per-run scratch space each agent's Observe stage reads and Reflect stage writes, discarded at end of run. Closes a real gap: agents today only see summarized `project_state`, losing intermediate reasoning within a single run.
- **15.2** — **Project memory (augment, don't replace)**: add `strategy_history` (past `strategy.yaml` snapshots + which workflow was chosen and why) and `confidence_history` (per-step, per-run confidence) as new top-level keys in `project_state.json` — additive only, existing `psm.merge_*` functions untouched. Fold in the `run_history[].workflow` bug fix here (start populating it from `WorkflowState.workflow_name`).
- **15.3** — Add a retention/pruning policy from day one — `project_state.json` is already 1300+ lines for one sample project; unbounded `confidence_history`/`run_history` growth is a real performance and diff-noise problem, not a someday concern, since the whole file is loaded/saved on every run.
- **15.4** — **Cross-project memory: explicitly not built in this migration.** Document as a separate future epic with open tenancy/privacy/retention questions (can patterns from one customer's project inform another's strategy?) rather than committing to a speculative shape now.

**Depends on**: Epic 13 (strategy_history needs strategy.yaml) and Epic 17 (confidence_history needs real confidence).
**Pros**: working memory is a genuine, low-risk gap-closer; project memory extension is additive to an already-proven structure. **Cons**: skipping 15.3 turns `project_state.json` into an ever-growing file loaded/saved every run — must ship with the retention cap, not after; cross-project memory is very likely throwaway work if anyone starts building against a speculative shape before real requirements land — hold the line on deferring it.

---

### EPIC 16 — Workflow YAML Expansion

New files in `workflows/`, using the existing generic loader (`steps:`/`depends_on`/`always_run`) — purely additive, zero loader code changes needed.

| File | Steps | Notes |
|---|---|---|
| `healing_only.yaml` | `healing`, `reporting(always_run)` | Mirrors `execution_only.yaml`'s 2-step shape. Fails today if no report exists yet — Epic 14's pre-step artifact check should catch this before dispatch. |
| `comprehension_only.yaml` | `discovery` (+ optional `artifact_generator_intents`) | BRD-ingestion-only, no test generation. |
| `bdd_only.yaml` | `discovery`/`comprehension`, `bdd` | `bdd` is registered but globally **disabled** in `agents.yaml` — needs a per-run enable override mechanism (16.3), not a global flag flip. |
| `testdata_only.yaml` | `testdata` | Assumes discovery already ran — a `required_artifacts` guard candidate. |
| `script_generation_only.yaml` | `semantic_map`, `script_generation` | Both needed — `script_generation` depends on both agents' outputs per `full_workflow.yaml`'s own documented dependency. |

- **16.1** — Author the 5 YAMLs following `full_workflow.yaml`'s comment-header convention.
- **16.2** — Confirm each new workflow's steps have `agents.yaml` enabled and `agent_registry.yaml` entries — all do already except `bdd`.
- **16.3** — Implement a per-run `agents_config` override mechanism so `bdd_only` can enable `bdd` for that one run without a global `agents.yaml` edit — this reveals that "Workflow Resolution" (Epic 13.2) sometimes also needs to emit config overrides, not just pick a filename.
- **16.4** — Feed all 8 workflow names + selection criteria into Epic 13.2's resolution decision table.

**Depends on**: Epic 13 (these exist *for* the Planner); for safety, sequence after Epic 14 exists so single-step workflows' prerequisite artifacts are guarded before they ship.
**Pros**: essentially zero-risk, purely additive. **Cons**: more named workflows = a larger space the Planner must get right; a too-narrow workflow choice surfaces as a downstream runtime failure unless Epic 14's pre-flight check lands first (real ordering risk).

---

### EPIC 17 — Real Confidence Scoring

Replaces the cosmetic `0.75`/`0.95` literals with genuinely computed self-assessment — **decentralized**, computed by each agent's own Reflect stage (Epic 0), not centralized in the Policy Engine, since only the producing agent has the domain signal to self-assess its own artifact.

- **17.1** — Extend Epic 0's `complete()` contract to structurally require `confidence: float` on every agent's return.
- **17.2** — **Healing (near-zero cost, no Epic 0 dependency)**: expose the already-computed `tests_healed / (tests_healed + remaining_total())` ratio as `confidence` — no new computation, just stop discarding a number that already exists.
- **17.3** — **Discovery**: derive confidence from the already-computed `summary.grounded_intents` ratio (DOM elements matched / BRD scenarios grounded) instead of the hardcoded `0.75`/`0.95` literals.
- **17.4** — **ScriptGeneration**: derive from TypeScript pre-execution compile success + ratio of DOM-element references matched vs. guessed.
- **17.5** — **Execution/UIExecution**: pass rate itself is the natural confidence signal.
- **17.6** — Wire every agent's `confidence` into `confidence_history` (Epic 15.2) and the Policy Engine's post-step gate (Epic 14.3).

**Depends on**: Epic 0 for every non-Healing agent; 17.2 has zero dependency and should ship first as a quick win.
**Pros**: turns "confidence" into an actionable signal instead of a label; 17.2 is nearly free. **Cons**: without a calibration pass — using Epic 15's `confidence_history` to backtest predicted vs. actual downstream success over many runs — self-reported confidence risks being just as arbitrary as the literals it replaces, only arbitrary with more steps in between; because each agent computes confidence via its own domain-specific formula, there's no single global meaning of "confidence = 0.6" across agents — `policy.yaml` must carry per-step thresholds, not one global number.

---

### EPIC 18 — Org mandate updates (CLAUDE.md, `agent.json` schema, scaffold script)

- **18.1** — Rewrite `agents/orchestrator/`'s "kept flat since it's already 1:1" line to reflect two agent folders.
- **18.2** — Formalize the new `agent.json` fields (`lifecycle_stages`, `confidence_method`, `memory_scope`, `loop_config`) in CLAUDE.md's schema block.
- **18.3** — Update the "skills.py/tools.py or explicit stub" mandate language — most agents now have real skills/tools content; the stub convention only applies where Epic-level analysis above concluded no reasoning/tooling exists (Reporting, Locator's skills.py, Discovery's skills.py, BDD until real logic lands).
- **18.4** — Update `tools/scaffold_agent.py` to emit the new ADK-shaped skeleton (RunContext subclass stub, `<AGENT>_INSTRUCTION` prompt stub, new agent.json fields) so every future new agent starts from the migrated shape, not the pre-ADK one.

**Depends on**: Epic 0 (schema exists to document) and should land alongside Epic 13 (category question) and Epic 1 (naming conventions extracted from Healing).
**Pros**: keeps the org mandate truthful instead of stale. **Cons**: none — pure documentation/tooling catch-up.

---

## Dependency graph & suggested execution waves

```
Wave 1 (foundation):        EPIC 0
Wave 2 (extract reference):  EPIC 1  (1.5 confidence win ships immediately, no wait)
Wave 3 (in-production path): EPIC 2 (UIExecution) ── EPIC 6 (Comprehension) ── EPIC 7 (Discovery)
                              [2 and 6 parallel; 7 waits on 6]
Wave 4:                      EPIC 8 (TestData+SemanticMap) ── EPIC 3 (Locator) ── EPIC 4 (Reporting)
                              ── EPIC 5 (Execution, pairs with Epic 2's contract)
                              [all four parallelizable]
Wave 5:                      EPIC 12 (ScriptGeneration, needs 8 + 1's pattern)
                              EPIC 16 (Workflow YAML expansion)
Wave 6:                      EPIC 17 (Confidence scoring, 17.2 already shipped in Wave 2)
                              EPIC 13 (Test Planner + entrypoint, needs 16)
Wave 7:                      EPIC 14 (Policy Engine, needs 17 to be more than artifact-checks)
                              EPIC 18 (org mandate updates, alongside 13)
Wave 8:                      EPIC 15 (Memory layer, needs 13 + 17)
Wave 9 (low-priority, dormant agents): EPIC 9 (ArtifactGenerator) ── EPIC 11 (Dedup) ── EPIC 10 (BDD, last)
```

Rationale for this order: migrate agents that are actually in the default `full_workflow.yaml` DAG
first (Waves 2–5), since that's where regressions would be immediately visible in production;
build the Planner/Policy/Memory "brain" once the workers it will orchestrate are already on the
new lifecycle (Waves 6–8); leave the three currently-dormant agents (ArtifactGenerator, Dedup, BDD)
for last since they carry zero production risk today and their migration is lower-value design
work, not urgent conversion.

---

## Platform-wide pros and cons of this migration

**Pros**
- Generalizes a pattern already proven in production (Healing) instead of inventing something untested.
- Closes real, confirmed gaps: no planner exists today (100% manual workflow selection); confidence is currently fake; several agents' `skills.py`/`tools.py` don't follow their own documented convention.
- `project_state.json` already has the substrate (gaps, new_additions, run_history) a planner needs — this isn't a green-field data problem.
- Several "migrations" are actually near-zero-cost wins once identified (Healing's discarded confidence ratio; the LocatorAgent/HealingAgent DOM-matching dedup opportunity).

**Cons / risks**
- This is a genuinely large migration (18 epics, ~14 agent folders, the orchestrator, the CLI, the org mandate) — sequencing matters more than any individual epic's design; the wave plan above exists specifically to avoid a big-bang cutover.
- Full Planner autonomy with no human checkpoint (explicit decision) means the Policy Engine (Epic 14) is the *only* safety net once a workflow is chosen, and it's deliberately no-LLM — a confidently-wrong discovery pass can still sail all the way through to a burned execution cycle if its self-reported confidence is miscalibrated.
- Self-reported, per-agent confidence has no cross-agent common scale — this needs the calibration discipline flagged in Epic 17, not just the plumbing.
- Dropping `--workflow` (no backward compat) breaks any external CI/script that invokes `main.py` directly today — needs explicit communication to whoever owns those call sites before Epic 13 ships, even though no code-level shim is being built.
- Several dormant agents (ArtifactGenerator, Dedup, BDD) risk being over-engineered with ADK ceremony they don't need — every relevant epic above includes an explicit "don't over-build this" call to counteract that.

---

## Verification approach (once implementation begins)

- Each epic that touches an agent already in `full_workflow.yaml`'s default path (Epics 1–8, 12) needs its pre-migration output contract captured as a literal regression fixture (per Epic 1.6/2.3's coupling-contract stories) *before* the rewrite starts, so the migration can be verified against real prior behavior, not re-derived expectations.
- Epic 13's `--dry-run`/`--explain` flag (13.5) should be the first thing built and used manually against several real project states before autonomy (13.4) is turned on for real runs — validates Workflow Resolution's choices are sane before they can execute unsupervised.
- Epic 14's `policy_trace` and Epic 15's `confidence_history` are the audit trail to review after the first several autonomous Planner runs — treat the first N runs as a supervised pilot even though the code path itself has no human gate, i.e. a human watches the trace after the fact rather than gating before.
- Run the existing test suite (if any exists under the current `BaseAgent`/`execute()` contract) before Epic 0 lands, to have a known-good baseline snapshot to diff against once agents move to the new lifecycle.
