export type RunStatus = "queued" | "cloning" | "installing" | "launching" | "running" | "completed" | "failed" | "cancelled";

export type PipelineStage =
  | "discovery"
  | "testdata"
  | "semantic_map"
  | "script_generation"
  | "ui_execution"
  | "healing"
  | "reporting"
  // Agent-evaluation pipeline
  | "repo_fetch"
  | "repo_analysis"
  | "brd"
  | "test_generation"
  | "static_review"
  | "live_execution"
  | "scoring"
  | "repo_intelligence"
  | "traceability"
  | "review"
  | "runtime_discovery"
  | "app_classification"
  | "action_generation"
  | "playwright_execution"
  | "evidence_collection"
  | "output_validation"
  | "pass_fail"
  | "brd_compliance"
  | "final_report";

/** What the user told us about their agent when submitting it. */
export type SubmissionMode = "brd_and_live" | "live_only" | "brd_only";

export type StepStatus = "pending" | "running" | "success" | "failed" | "skipped";

export type RequirementStatus = "implemented" | "partial" | "missing" | "unknown";

/** pending | passed | failed | inconclusive | not_executed are current; skipped and healed are legacy. */
export type TestStatus = "passed" | "failed" | "inconclusive" | "not_executed" | "pending" | "healed" | "skipped";

export type RiskLevel = "low" | "medium" | "high";

export type RecommendationCategory =
  | "failed_test"
  | "coverage_gap"
  | "weak_validation"
  | "missing_negative_case"
  | "flaky_behavior";

export type Severity = "critical" | "warning" | "info";

export interface Project {
  id: string;
  name: string;
  githubUrl: string;
  branch: string;
  mode: SubmissionMode;
  liveUrl: string | null;
  brdPath: string | null;
  lastRunStatus: RunStatus;
  lastQualityScore: number | null;
  updatedAt: string;
  /** Shared demo project, visible to every user and read-only. */
  isSample: boolean;
  /** A live-app test account is stored (encrypted); the credentials themselves are never sent to the browser. */
  hasLiveAuth: boolean;
}

export interface QualityBreakdown {
  label: string;
  score: number;
  max: number;
}

export interface RunStats {
  scenariosFound: number;
  testCasesGenerated: number;
  passed: number;
  failed: number;
  healed: number;
  skipped: number;
  coveragePct: number;
  qualityScore: number;
  riskLevel: RiskLevel;
  criticalDefects: number;
  duplicatesRejected: number;
}

export interface Run {
  id: string;
  projectId: string;
  projectName: string;
  status: RunStatus;
  currentStage: PipelineStage | null;
  startedAt: string;
  finishedAt: string | null;
  durationSec: number | null;
  stats: RunStats;
  qualityBreakdown: QualityBreakdown[];
  trend: number[];
  // Agent-evaluation runs only (null for legacy Playwright runs)
  mode: SubmissionMode | null;
  liveUrl: string | null;
  githubUrl: string;
  projectIsSample: boolean;
  commitRef: string | null;
  brdSource: BrdSource | null;
  summary: string | null;
  errorMessage: string | null;
  compliance: ComplianceResult | null;
  /** Last sign of life from the evaluation service (bumped every ~30 s while it works on the run). */
  heartbeatAt: string | null;
  /** The user asked to cancel; the service stops at its next checkpoint and sets status "cancelled". */
  cancelRequested: boolean;
}

export type GateLevel = "pass" | "warn" | "block";

export interface ComplianceResult {
  scoringVersion: string | null;
  scoreKind: "brd_compliance" | "inferred_conformance" | null;
  score: number | null;
  ciLow: number | null;
  ciHigh: number | null;
  verificationDepth: number | null;
  scorecard: Record<string, number> | null;
  gates: { gate: string; level: GateLevel; reason: string }[];
}

export type CriterionVerdict =
  | "verified_pass"
  | "verified_fail"
  | "implemented_static"
  | "partial"
  | "not_implemented"
  | "insufficient_evidence"
  | "not_technically_verifiable"
  | "contested";

export interface EvidenceItem {
  id: string;
  method: "static" | "structural" | "repo_test" | "runtime" | "doc_claim";
  strength: "E1" | "E2" | "E3" | "E4" | "E5";
  outcome: "supports" | "refutes" | "neutral";
  summary: string;
  validated: boolean;
  citation: {
    file?: string; start_line?: number; end_line?: number; symbol?: string; url?: string | null; check?: string;
    // runtime evidence: files in the run's artifact folder
    kind?: "runtime"; bundle_id?: string; screenshot?: string | null;
    documents?: { name: string; file: string; text_file?: string | null }[];
  } | null;
  testCaseId: string | null;
}

export interface Criterion {
  id: string;
  code: string;
  statement: string;
  oracleHint: string;
  verdict: CriterionVerdict | null;
  bestStrength: string | null;
  credit: number | null;
  agreement: number | null;
  rationale: string | null;
  evidence: EvidenceItem[];
}

export interface Finding {
  id: string;
  dimension: string;
  ruleId: string | null;
  severity: "critical" | "high" | "medium" | "low" | "info";
  title: string;
  filePath: string | null;
  startLine: number | null;
  rationale: string | null;
  fix: string | null;
  source: string;
}

export interface RunStep {
  key: PipelineStage;
  label: string;
  position: number;
  status: StepStatus;
  detail: string | null;
  startedAt: string | null;
  finishedAt: string | null;
}

export interface RunEvent {
  id: string;
  createdAt: string;
  level: "info" | "warning" | "error" | "success";
  stage: PipelineStage | null;
  message: string;
}

export interface RunProgress {
  status: RunStatus;
  currentStage: PipelineStage | null;
  startedAt?: string;
  finishedAt?: string | null;
  steps: RunStep[];
  events: RunEvent[];
  /** Typical seconds per step (median of recent completed runs), for the time-remaining estimate. */
  estimates?: Record<string, number>;
}

/** One line of the cross-run activity timeline (dashboard). */
export interface ActivityEvent {
  id: string;
  createdAt: string;
  level: "info" | "success" | "warning" | "error";
  stage: PipelineStage | null;
  message: string;
  runId: string;
  projectName: string;
}

/** The complete run log for the Logs tab. */
export interface RunLogs {
  status: RunStatus;
  startedAt: string;
  finishedAt: string | null;
  events: RunEvent[];
}

export interface Requirement {
  id: string;
  code: string;
  title: string;
  description: string;
  priority: "high" | "medium" | "low";
  kind: "functional" | "non_functional";
  acceptanceCriteria: string[];
  section: string | null;
  sourceQuote: string | null;
  status: RequirementStatus;
  evidence: string | null;
  verifiability: string;
  origin: "brd" | "inferred" | "descriptive";
  confidence: number;
  verdict: string | null;
  score: number | null;
  criteria: Criterion[];
}

export interface EndpointInfo {
  method?: string;
  path?: string;
  description?: string;
}

export interface AgentProfile {
  agent_name?: string | null;
  purpose?: string;
  domain?: string | null;
  target_users?: string[];
  capabilities?: string[];
  out_of_scope?: string[];
  tools_and_integrations?: string[];
  llm_providers?: string[];
  tech_stack?: string[];
  interface?: { type?: string; framework?: string; endpoints?: EndpointInfo[]; notes?: string };
  observed_risks?: string[];
  file_count?: number;
}

/** repository = the repo's own BRD; generated = written by Gemini from the code; generated_live = from the live app. */
export type BrdSource = "repository" | "generated" | "generated_live";

export interface RunArtifacts {
  brdSource: BrdSource | null;
  brdPath: string | null;
  brdContent: string | null;
  agentProfile: AgentProfile | null;
  requirements: Requirement[];
  findings: Finding[];
  runtimeProfile: RuntimeProfile | null;
  appClassification: AppClassification | null;
  actionPlan: ActionPlan | null;
  executionRun: ExecutionRun | null;
  evidenceCollection: EvidenceCollection | null;
  outputValidation: OutputValidation | null;
  passFail: PassFail | null;
  brdCompliance: BrdCompliance | null;
  /** Headline only; the full report is served by /api/runs/:runId/report. */
  finalReport: { outcome: string; compliance: number | null; generatedAt: string } | null;
}

export interface ComplianceDiscrepancy {
  kind: "broken_at_runtime" | "missed_by_code_review" | "mixed_runtime" | "runtime_only_unverified";
  severity: "high" | "warning" | "info";
  detail: string;
  criterion_code: string;
  requirement_code: string;
  requirement_title: string | null;
  priority: string | null;
}

export interface BrdCompliance {
  discrepancies: ComplianceDiscrepancy[];
  evidence_mix: {
    by_strength: Record<"E5" | "E4" | "E3" | "E2" | "E1" | "none", number>;
    runtime_share: number;
    credit_by_basis: { runtime: number; code: number };
  };
  counts: {
    requirements: number; criteria: number; criteria_runtime: number; criteria_code_only: number; criteria_without_evidence: number;
    broken_at_runtime: number; missed_by_code_review: number; mixed_runtime: number; runtime_only_unverified: number;
    requirement_verdicts: Record<string, number>;
  };
}

export interface TestVerdict {
  bundle_id: string;
  test_id: string | null;
  test_code: string | null;
  criterion_code: string | null;
  title: string | null;
  variant: string | null;
  kind: "brd_test" | "flow_check";
  scored: boolean;
  verdict: "passed" | "failed" | "inconclusive" | "not_executed";
  score: number | null;
  strength: "E5" | "E4" | null;
  decided_by: "deterministic" | "judge" | null;
  reasons: string[];
  supporting_issues: string[];
  actual_output: string | null;
  duration_ms: number;
}

export interface CriterionRuntimeVerdict {
  criterion_code: string;
  statement: string | null;
  tests: string[];
  passed: number;
  failed: number;
  inconclusive: number;
  not_executed: number;
  runtime_verdict: "supported" | "refuted" | "unverified";
  strength: "E5" | "E4" | null;
  mixed: boolean;
}

export interface PassFail {
  counts: { passed: number; failed: number; inconclusive: number; not_executed: number; tests: number; flow_checks: number;
    criteria_supported: number; criteria_refuted: number; criteria_unverified: number };
  pass_rate: number | null;
  tests: TestVerdict[];
  criteria: CriterionRuntimeVerdict[];
}

export interface ValidationCheck {
  id: string;
  name: string;
  oracle: "deterministic";
  result: "pass" | "fail" | "unknown";
  detail: string;
  weight: "core" | "supporting";
}

export interface OutputJudgement {
  oracle: "semantic";
  assessment: "meets" | "partially_meets" | "does_not_meet" | "cannot_tell";
  score: number;
  reasoning: string;
  criteria_results: { criterion: string; result: "met" | "not_met" | "cannot_tell"; quote: string | null; quote_verified: boolean; note?: string }[];
  ungrounded_quotes: number;
}

export interface OutputValidationResult {
  bundle_id: string;
  test_id: string | null;
  test_code: string | null;
  criterion_code: string | null;
  title: string | null;
  variant: string | null;
  kind: "brd_test" | "flow_check";
  scored: boolean;
  status: "validated" | "not_validatable";
  reason?: string;
  checks: ValidationCheck[];
  judge: OutputJudgement | null;
  judge_error?: string | null;
  core_failures?: string[];
  supporting_failures?: string[];
  summary: string;
}

export interface OutputValidation {
  counts: { bundles: number; validated: number; not_validatable: number; checks_passed: number; checks_failed: number;
    judged: number; meets: number; ungrounded_quotes: number };
  results: OutputValidationResult[];
}

export interface EvidenceDocument {
  file?: string;
  name: string;
  format?: string;
  readable: boolean;
  error?: string;
  words?: number;
  pages?: number;
  tables?: number;
  slides?: number;
  headings?: string[];
  text_file?: string;
  text_excerpt?: string;
  size?: number;
  sha256?: string;
}

export interface EvidenceBundle {
  bundle_id: string;
  plan_id: string | null;
  test_id: string | null;
  test_code: string | null;
  criterion_code: string | null;
  criterion_statement: string | null;
  requirement_ref: string | null;
  title: string | null;
  kind: "brd_test" | "flow_check";
  scored: boolean;
  test_input: string | null;
  expected_behavior: string | null;
  execution_status: "completed" | "failed" | "error" | "blocked" | "not_run" | "not_executed";
  failed_step: number | null;
  error: string | null;
  inputs: { step: number; action: string; field: string | null; value: string | null; synthetic: boolean }[];
  observed: {
    ui_output: string | null;
    page_change: "added" | "reordered" | "none" | null;
    page_text_excerpt: string | null;
    messages: string[];
    reply: string | null;
    documents: EvidenceDocument[];
    http_response: { status: number; ms: number; content_type?: string; excerpt: string } | null;
    final_url: string | null;
  };
  artifacts: { type: string; path: string; size: number; sha256: string }[];
  completeness: { output_captured: boolean; expected_output: string | null; missing: string[] };
}

export interface EvidenceCollection {
  status: "collected" | "empty";
  counts: { bundles: number; executed: number; with_output: number; documents: number; not_executed: number; criteria_covered: number };
  by_criterion: Record<string, string[]>;
  bundles: EvidenceBundle[];
}

export interface ExecutionStepResult {
  n: number;
  action: ActionStep["action"];
  status: "passed" | "failed" | "skipped" | "deferred";
  duration_ms: number;
  locator?: string;
  detail?: string;
  error?: string;
  screenshot?: string;
}

export interface ExecutionResult {
  plan_id: string;
  test_id: string | null;
  test_code: string | null;
  criterion_code: string | null;
  title: string;
  kind: "brd_test" | "flow_check";
  scored: boolean;
  status: "completed" | "failed" | "error" | "blocked" | "not_run";
  failed_step: number | null;
  error: string | null;
  duration_ms: number;
  final_url?: string;
  steps: ExecutionStepResult[];
  captures: {
    screenshot?: string | null;
    dom_text?: string | null;
    dom_excerpt?: string | null;
    reply?: string | null;
    downloads?: { file: string; name: string; size: number; sha256: string; kind: string }[];
    response?: { status: number; ms: number; excerpt: string; file: string } | null;
  };
  observations: {
    network?: { method: string; path: string; status: number; ms: number }[];
    console_errors?: string[];
    page_errors?: string[];
    http_errors?: number;
  };
}

export interface ExecutionRun {
  status: "completed" | "partial" | "blocked" | "skipped";
  reason: string | null;
  duration_s: number;
  login: { attempted: boolean; succeeded?: boolean; error?: string; landed_on?: string };
  counts: { plans: number; completed: number; failed: number; error: number; blocked: number; not_run: number; downloads: number };
  results: ExecutionResult[];
}

export interface ActionStep {
  n: number;
  action: "login" | "goto" | "fill" | "select" | "check" | "upload" | "click" | "send_message" | "wait_for" | "follow_up"
    | "expect_download" | "http" | "capture" | "assert";
  target?: { id?: string; kind?: string; page?: string; label?: string; name?: string; type?: string; text?: string;
    href?: string; role?: string; nth?: number; context?: string };
  value?: string;
  url?: string;
  kind?: string;
  method?: string;
  path?: string;
  timeout_ms?: number;
  what?: string[];
  expectation?: string;
  synthetic?: boolean;
}

export interface ActionPlanItem {
  plan_id: string;
  test_id: string | null;
  test_code: string | null;
  criterion_code: string | null;
  requirement_ref: string | null;
  title: string;
  variant: string | null;
  class: string;
  kind: "brd_test" | "flow_check";
  scored: boolean;
  status: "ready" | "unmappable";
  source: "llm" | "rules";
  reason: string | null;
  steps: ActionStep[];
}

export interface ActionPlan {
  app_type: string;
  status: "ready" | "partial" | "blocked";
  reason: string | null;
  requires_login: boolean;
  inventory_size: number;
  counts: { tests: number; ready: number; unmappable: number; blocked: number; flow_checks?: number;
    llm_mapped?: number; ungrounded_steps_dropped?: number };
  plans: ActionPlanItem[];
}

export interface AppClassification {
  /** Chatbot | Form Application | Dashboard | Document Generator | REST API | Workflow System | Static Website | Hybrid Application | Unknown */
  app_type: string;
  confidence: number;
  /** For a Hybrid Application: the classes it combines, strongest first. */
  components: string[];
  basis: "runtime + code" | "runtime" | "code" | "none";
  note: string | null;
  scores: Record<string, number>;
  evidence: { class: string; signal: string; source: "runtime" | "code"; points: number }[];
  testing_strategy: { class: string; strategy: string }[];
}

export interface RuntimePage {
  path: string;
  status: number | null;
  title: string;
  headings: string[];
  forms: { kind: string; field_count: number; required_fields: number; submit_button: string | null; is_login: boolean;
    fields: { label: string; name: string; type: string; required: boolean }[] }[];
  buttons: string[];
  downloads: { links: string[]; buttons: string[] };
  file_uploads: number;
  chat_interface: boolean;
}

export interface RuntimeProfile {
  app_type: string;
  forms: number;
  buttons: number;
  downloads: boolean;
  chat_interface: boolean;
  authentication: boolean;
  live_url: string;
  pages_inspected: number;
  gated_pages: string[];
  needs_credentials?: boolean;
  login?: { attempted: boolean; succeeded?: boolean; error?: string; landed_on?: string };
  classification_signals: string[];
  authentication_signals: string[];
  file_uploads: number;
  frameworks: string[];
  api_calls: { method: string; path: string; status: number }[];
  user_flows: { name: string; entry: string; steps: string[]; form_fields?: string[] }[];
  pages: RuntimePage[];
  duration_s: number;
}

export interface Scenario {
  id: string;
  runId: string;
  title: string;
  module: string;
  confidence: number;
}

export interface TestCase {
  id: string;
  runId: string;
  scenarioTitle: string;
  module: string;
  variantType: string;
  status: TestStatus;
  durationMs: number;
  healed: boolean;
  errorSummary?: string;
  specPreview?: string;
  category?: "agent_specific" | "general";
  requirementRef?: string;
  priority?: string;
  input?: string;
  expected?: string;
  actualOutput?: string;
  judgeReasoning?: string;
  judgeScore?: number;
  brdReference?: string;
  acceptanceCriterion?: string;
}

export type EvidenceType = "scenario" | "test_case";

export interface Recommendation {
  id: string;
  runId: string;
  category: RecommendationCategory;
  severity: Severity;
  summary: string;
  evidenceRef: string;
  evidenceType: EvidenceType;
}
