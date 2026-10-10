"""
tools.requirements — the shared requirements & traceability core (Phase 1).

Imported by both pipelines: the legacy test pipeline (ComprehensionAgent, ScriptGenerationAgent,
UIExecutionAgent, ReportingAgent) and the Agent-Evaluation DAG (brd_builder uses brd_index + normalize).

  brd_index     quote / criterion grounding (BrdIndex)
  normalize     Agent-Eval requirement-row normaliser (+ deterministic enrichment)
  explicit      parser for document-declared REQ / AC ids
  atomicity     deterministic one-behaviour check
  classify      risk tags, priority precedence, testability
  extract       BRD text → quote-verified, classified, atomic requirements
  store         requirements.json per-module upsert
  service       project-level operations (extract a module, link scenarios)
  linking       scenario ↔ AC and test ↔ AC links
  tracing       annotate generated plans (tc_id, ac_ids, tags)
  traceability  traceability.json: build, apply results, report section
  build         CLI: python -m tools.requirements.build --project X

Submodules are imported explicitly (no eager imports here) so lightweight users — e.g. brd_index from the
evaluation service — do not load the comprehension or connector stacks.
"""
