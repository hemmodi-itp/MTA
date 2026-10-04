import type {
  Prisma,
  Project as DbProject,
  TestCase as DbTestCase,
  Recommendation as DbRecommendation,
  RunStep as DbRunStep,
  RunEvent as DbRunEvent,
  Requirement as DbRequirement,
  AcceptanceCriterion as DbCriterion,
  Evidence as DbEvidence,
  Finding as DbFinding,
} from "@prisma/client";
import type {
  Project,
  Run,
  QualityBreakdown,
  TestCase,
  Recommendation,
  RunStep,
  RunEvent,
  Requirement,
  Criterion,
  EvidenceItem,
  Finding,
  ComplianceResult,
} from "@/lib/types";

export function mapProject(row: DbProject): Project {
  return {
    id: row.id,
    name: row.name,
    githubUrl: row.githubUrl,
    branch: row.branch,
    mode: row.mode,
    liveUrl: row.liveUrl,
    brdPath: row.brdPath,
    lastRunStatus: row.lastRunStatus,
    // Older rows hold 0 for runs that were never scored; a 0 here is "not scored", not a score.
    lastQualityScore: row.lastQualityScore || null,
    updatedAt: row.updatedAt.toISOString(),
    isSample: row.isSample,
    hasLiveAuth: !!row.liveAuth,
  };
}

/**
 * Everything mapRun needs and nothing more. The run list, run detail and every poll go through this, so the heavy
 * per-run JSON (runtimeProfile, actionPlan, executionRun, evidenceCollection, outputValidation, passFail,
 * brdCompliance, finalReport) and text (brdContent, agentProfile) columns are never read here — only
 * /api/runs/[runId]/artifacts, /report and /api/copilot load them.
 */
export const RUN_SELECT = {
  id: true,
  projectId: true,
  status: true,
  currentStage: true,
  startedAt: true,
  finishedAt: true,
  durationSec: true,
  scenariosFound: true,
  testCasesGenerated: true,
  passed: true,
  failed: true,
  healed: true,
  skipped: true,
  coveragePct: true,
  qualityScore: true,
  riskLevel: true,
  criticalDefects: true,
  duplicatesRejected: true,
  qualityBreakdown: true,
  trend: true,
  mode: true,
  liveUrl: true,
  commitRef: true,
  brdSource: true,
  summary: true,
  errorMessage: true,
  heartbeatAt: true,
  cancelRequested: true,
  scoringVersion: true,
  scoreKind: true,
  complianceScore: true,
  ciLow: true,
  ciHigh: true,
  verificationDepth: true,
  scorecard: true, // {dimension: score}, a handful of keys
  gates: true, // a few {gate, level, reason} rows
  project: { select: { name: true, githubUrl: true, isSample: true } },
} as const satisfies Prisma.RunSelect;

export type RunRow = Prisma.RunGetPayload<{ select: typeof RUN_SELECT }>;

export function mapRun(row: RunRow): Run {
  return {
    id: row.id,
    projectId: row.projectId,
    projectName: row.project.name,
    githubUrl: row.project.githubUrl,
    projectIsSample: row.project.isSample,
    status: row.status,
    currentStage: row.currentStage,
    startedAt: row.startedAt.toISOString(),
    finishedAt: row.finishedAt ? row.finishedAt.toISOString() : null,
    durationSec: row.durationSec,
    stats: {
      scenariosFound: row.scenariosFound,
      testCasesGenerated: row.testCasesGenerated,
      passed: row.passed,
      failed: row.failed,
      healed: row.healed,
      skipped: row.skipped,
      coveragePct: row.coveragePct,
      qualityScore: row.qualityScore,
      riskLevel: row.riskLevel,
      criticalDefects: row.criticalDefects,
      duplicatesRejected: row.duplicatesRejected,
    },
    qualityBreakdown: (row.qualityBreakdown as unknown as QualityBreakdown[]) ?? [],
    trend: (row.trend as unknown as number[]) ?? [],
    mode: row.mode,
    liveUrl: row.liveUrl,
    commitRef: row.commitRef,
    brdSource: (row.brdSource as Run["brdSource"]) ?? null,
    summary: row.summary,
    errorMessage: row.errorMessage,
    compliance: row.scoringVersion
      ? {
          scoringVersion: row.scoringVersion,
          scoreKind: row.scoreKind as ComplianceResult["scoreKind"],
          score: row.complianceScore,
          ciLow: row.ciLow,
          ciHigh: row.ciHigh,
          verificationDepth: row.verificationDepth,
          scorecard: (row.scorecard as Record<string, number> | null) ?? null,
          gates: (row.gates as unknown as ComplianceResult["gates"]) ?? [],
        }
      : null,
    heartbeatAt: row.heartbeatAt ? row.heartbeatAt.toISOString() : null,
    cancelRequested: row.cancelRequested,
  };
}

export function mapTestCase(row: DbTestCase): TestCase {
  return {
    id: row.id,
    runId: row.runId,
    scenarioTitle: row.scenarioTitle,
    module: row.module,
    variantType: row.variantType,
    status: row.status,
    durationMs: row.durationMs,
    healed: row.healed,
    errorSummary: row.errorSummary ?? undefined,
    specPreview: row.specPreview ?? undefined,
    category: (row.category as TestCase["category"]) ?? undefined,
    requirementRef: row.requirementRef ?? undefined,
    priority: row.priority ?? undefined,
    input: row.input ?? undefined,
    expected: row.expected ?? undefined,
    actualOutput: row.actualOutput ?? undefined,
    judgeReasoning: row.judgeReasoning ?? undefined,
    judgeScore: row.judgeScore ?? undefined,
    brdReference: row.brdReference ?? undefined,
    acceptanceCriterion: row.acceptanceCriterion ?? undefined,
  };
}

export function mapRecommendation(row: DbRecommendation): Recommendation {
  return {
    id: row.id,
    runId: row.runId,
    category: row.category,
    severity: row.severity,
    summary: row.summary,
    evidenceRef: row.evidenceRef,
    evidenceType: row.evidenceType,
  };
}

export function mapRunStep(row: DbRunStep): RunStep {
  return {
    key: row.key,
    label: row.label,
    position: row.position,
    status: row.status,
    detail: row.detail,
    startedAt: row.startedAt ? row.startedAt.toISOString() : null,
    finishedAt: row.finishedAt ? row.finishedAt.toISOString() : null,
  };
}

export function mapRunEvent(row: DbRunEvent): RunEvent {
  return {
    id: row.id,
    createdAt: row.createdAt.toISOString(),
    level: row.level as RunEvent["level"],
    stage: row.stage,
    message: row.message,
  };
}

export function mapEvidence(row: DbEvidence): EvidenceItem {
  return {
    id: row.id,
    method: row.method as EvidenceItem["method"],
    strength: row.strength as EvidenceItem["strength"],
    outcome: row.outcome as EvidenceItem["outcome"],
    summary: row.summary,
    validated: row.validated,
    citation: (row.citation as EvidenceItem["citation"]) ?? null,
    testCaseId: row.testCaseId,
  };
}

export function mapCriterion(row: DbCriterion & { evidence?: DbEvidence[] }): Criterion {
  return {
    id: row.id,
    code: row.code,
    statement: row.statement,
    oracleHint: row.oracleHint,
    verdict: row.verdict as Criterion["verdict"],
    bestStrength: row.bestStrength,
    credit: row.credit,
    agreement: row.agreement,
    rationale: row.rationale,
    evidence: (row.evidence ?? []).map(mapEvidence),
  };
}

export function mapFinding(row: DbFinding): Finding {
  return {
    id: row.id,
    dimension: row.dimension,
    ruleId: row.ruleId,
    severity: row.severity as Finding["severity"],
    title: row.title,
    filePath: row.filePath,
    startLine: row.startLine,
    rationale: row.rationale,
    fix: row.fix,
    source: row.source,
  };
}

export function mapRequirement(row: DbRequirement & { criteria?: (DbCriterion & { evidence?: DbEvidence[] })[] }): Requirement {
  return {
    id: row.id,
    code: row.code,
    title: row.title,
    description: row.description,
    priority: row.priority as Requirement["priority"],
    kind: row.kind as Requirement["kind"],
    acceptanceCriteria: (row.acceptanceCriteria as unknown as string[]) ?? [],
    section: row.section,
    sourceQuote: row.sourceQuote,
    status: row.status,
    evidence: row.evidence,
    verifiability: row.verifiability,
    origin: row.origin as Requirement["origin"],
    confidence: row.confidence,
    verdict: row.verdict,
    score: row.score,
    criteria: (row.criteria ?? []).map(mapCriterion),
  };
}
