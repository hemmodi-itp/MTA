-- CreateSchema
CREATE SCHEMA IF NOT EXISTS "public";

-- CreateEnum
CREATE TYPE "RunStatus" AS ENUM ('queued', 'cloning', 'installing', 'launching', 'running', 'completed', 'failed');

-- CreateEnum
CREATE TYPE "PipelineStage" AS ENUM ('discovery', 'testdata', 'semantic_map', 'script_generation', 'ui_execution', 'healing', 'reporting', 'repo_fetch', 'repo_analysis', 'brd', 'test_generation', 'static_review', 'live_execution', 'scoring', 'repo_intelligence', 'traceability', 'review', 'runtime_discovery', 'app_classification', 'action_generation', 'playwright_execution', 'evidence_collection', 'output_validation', 'pass_fail', 'brd_compliance', 'final_report');

-- CreateEnum
CREATE TYPE "SubmissionMode" AS ENUM ('brd_and_live', 'live_only', 'brd_only');

-- CreateEnum
CREATE TYPE "StepStatus" AS ENUM ('pending', 'running', 'success', 'failed', 'skipped');

-- CreateEnum
CREATE TYPE "RequirementStatus" AS ENUM ('implemented', 'partial', 'missing', 'unknown');

-- CreateEnum
CREATE TYPE "TestStatus" AS ENUM ('passed', 'failed', 'healed', 'skipped', 'pending', 'not_executed');

-- CreateEnum
CREATE TYPE "RiskLevel" AS ENUM ('low', 'medium', 'high');

-- CreateEnum
CREATE TYPE "RecommendationCategory" AS ENUM ('failed_test', 'coverage_gap', 'weak_validation', 'missing_negative_case', 'flaky_behavior');

-- CreateEnum
CREATE TYPE "Severity" AS ENUM ('critical', 'warning', 'info');

-- CreateEnum
CREATE TYPE "EvidenceType" AS ENUM ('scenario', 'test_case');

-- CreateTable
CREATE TABLE "User" (
    "id" TEXT NOT NULL,
    "email" TEXT NOT NULL,
    "name" TEXT,
    "passwordHash" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "User_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Session" (
    "id" TEXT NOT NULL,
    "tokenHash" TEXT NOT NULL,
    "expiresAt" TIMESTAMP(3) NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "userId" TEXT NOT NULL,

    CONSTRAINT "Session_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Project" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "githubUrl" TEXT NOT NULL,
    "branch" TEXT NOT NULL DEFAULT 'main',
    "mode" "SubmissionMode" NOT NULL DEFAULT 'brd_and_live',
    "liveUrl" TEXT,
    "brdPath" TEXT,
    "liveAuth" TEXT,
    "lastRunStatus" "RunStatus" NOT NULL DEFAULT 'queued',
    "lastQualityScore" INTEGER,
    "isSample" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    "userId" TEXT,

    CONSTRAINT "Project_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Run" (
    "id" TEXT NOT NULL,
    "status" "RunStatus" NOT NULL DEFAULT 'queued',
    "currentStage" "PipelineStage",
    "startedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "finishedAt" TIMESTAMP(3),
    "durationSec" INTEGER,
    "scenariosFound" INTEGER NOT NULL DEFAULT 0,
    "testCasesGenerated" INTEGER NOT NULL DEFAULT 0,
    "passed" INTEGER NOT NULL DEFAULT 0,
    "failed" INTEGER NOT NULL DEFAULT 0,
    "healed" INTEGER NOT NULL DEFAULT 0,
    "skipped" INTEGER NOT NULL DEFAULT 0,
    "coveragePct" INTEGER NOT NULL DEFAULT 0,
    "qualityScore" INTEGER NOT NULL DEFAULT 0,
    "riskLevel" "RiskLevel" NOT NULL DEFAULT 'low',
    "criticalDefects" INTEGER NOT NULL DEFAULT 0,
    "duplicatesRejected" INTEGER NOT NULL DEFAULT 0,
    "qualityBreakdown" JSONB NOT NULL DEFAULT '[]',
    "trend" JSONB NOT NULL DEFAULT '[]',
    "mode" "SubmissionMode",
    "liveUrl" TEXT,
    "commitRef" TEXT,
    "brdSource" TEXT,
    "brdPath" TEXT,
    "brdContent" TEXT,
    "agentProfile" JSONB,
    "summary" TEXT,
    "errorMessage" TEXT,
    "snapshotId" TEXT,
    "scoringVersion" TEXT,
    "scoreKind" TEXT,
    "complianceScore" DOUBLE PRECISION,
    "ciLow" DOUBLE PRECISION,
    "ciHigh" DOUBLE PRECISION,
    "verificationDepth" DOUBLE PRECISION,
    "scorecard" JSONB,
    "gates" JSONB,
    "runtimeProfile" JSONB,
    "appClassification" JSONB,
    "actionPlan" JSONB,
    "executionRun" JSONB,
    "evidenceCollection" JSONB,
    "outputValidation" JSONB,
    "passFail" JSONB,
    "brdCompliance" JSONB,
    "finalReport" JSONB,
    "projectId" TEXT NOT NULL,

    CONSTRAINT "Run_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "RunStep" (
    "id" TEXT NOT NULL,
    "key" "PipelineStage" NOT NULL,
    "label" TEXT NOT NULL,
    "position" INTEGER NOT NULL,
    "status" "StepStatus" NOT NULL DEFAULT 'pending',
    "detail" TEXT,
    "startedAt" TIMESTAMP(3),
    "finishedAt" TIMESTAMP(3),
    "runId" TEXT NOT NULL,

    CONSTRAINT "RunStep_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "RunEvent" (
    "id" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "level" TEXT NOT NULL DEFAULT 'info',
    "stage" "PipelineStage",
    "message" TEXT NOT NULL,
    "runId" TEXT NOT NULL,

    CONSTRAINT "RunEvent_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Requirement" (
    "id" TEXT NOT NULL,
    "code" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "description" TEXT NOT NULL,
    "priority" TEXT NOT NULL DEFAULT 'medium',
    "kind" TEXT NOT NULL DEFAULT 'functional',
    "acceptanceCriteria" JSONB NOT NULL DEFAULT '[]',
    "section" TEXT,
    "sourceQuote" TEXT,
    "status" "RequirementStatus" NOT NULL DEFAULT 'unknown',
    "evidence" TEXT,
    "verifiability" TEXT NOT NULL DEFAULT 'both',
    "origin" TEXT NOT NULL DEFAULT 'brd',
    "confidence" DOUBLE PRECISION NOT NULL DEFAULT 1,
    "verdict" TEXT,
    "score" DOUBLE PRECISION,
    "runId" TEXT NOT NULL,

    CONSTRAINT "Requirement_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "AcceptanceCriterion" (
    "id" TEXT NOT NULL,
    "code" TEXT NOT NULL,
    "statement" TEXT NOT NULL,
    "oracleHint" TEXT NOT NULL DEFAULT 'semantic',
    "weight" DOUBLE PRECISION NOT NULL DEFAULT 1,
    "verdict" TEXT,
    "bestStrength" TEXT,
    "credit" DOUBLE PRECISION,
    "agreement" DOUBLE PRECISION,
    "rationale" TEXT,
    "negativeSearch" JSONB,
    "requirementId" TEXT NOT NULL,
    "runId" TEXT NOT NULL,

    CONSTRAINT "AcceptanceCriterion_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Evidence" (
    "id" TEXT NOT NULL,
    "method" TEXT NOT NULL,
    "strength" TEXT NOT NULL,
    "outcome" TEXT NOT NULL,
    "citation" JSONB,
    "testCaseId" TEXT,
    "summary" TEXT NOT NULL,
    "validated" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "criterionId" TEXT,
    "runId" TEXT NOT NULL,

    CONSTRAINT "Evidence_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Finding" (
    "id" TEXT NOT NULL,
    "dimension" TEXT NOT NULL,
    "ruleId" TEXT,
    "severity" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "filePath" TEXT,
    "startLine" INTEGER,
    "endLine" INTEGER,
    "rationale" TEXT,
    "fix" TEXT,
    "source" TEXT NOT NULL,
    "confidence" DOUBLE PRECISION NOT NULL DEFAULT 1,
    "runId" TEXT NOT NULL,

    CONSTRAINT "Finding_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "RepoSnapshot" (
    "id" TEXT NOT NULL,
    "repoFullName" TEXT NOT NULL,
    "commitSha" TEXT NOT NULL,
    "indexerVersion" TEXT NOT NULL,
    "fileCount" INTEGER NOT NULL DEFAULT 0,
    "languages" JSONB NOT NULL DEFAULT '{}',
    "repoModel" JSONB,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "RepoSnapshot_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "KgNode" (
    "id" TEXT NOT NULL,
    "kind" TEXT NOT NULL,
    "key" TEXT NOT NULL,
    "filePath" TEXT,
    "startLine" INTEGER,
    "endLine" INTEGER,
    "name" TEXT,
    "props" JSONB NOT NULL DEFAULT '{}',
    "snapshotId" TEXT NOT NULL,

    CONSTRAINT "KgNode_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "KgEdge" (
    "src" TEXT NOT NULL,
    "dst" TEXT NOT NULL,
    "kind" TEXT NOT NULL,
    "snapshotId" TEXT NOT NULL,

    CONSTRAINT "KgEdge_pkey" PRIMARY KEY ("snapshotId","src","kind","dst")
);

-- CreateTable
CREATE TABLE "CodeChunk" (
    "id" TEXT NOT NULL,
    "filePath" TEXT NOT NULL,
    "startLine" INTEGER NOT NULL,
    "endLine" INTEGER NOT NULL,
    "symbol" TEXT,
    "content" TEXT NOT NULL,
    "snapshotId" TEXT NOT NULL,

    CONSTRAINT "CodeChunk_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Scenario" (
    "id" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "module" TEXT NOT NULL,
    "confidence" DOUBLE PRECISION NOT NULL,
    "runId" TEXT NOT NULL,

    CONSTRAINT "Scenario_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "TestCase" (
    "id" TEXT NOT NULL,
    "scenarioTitle" TEXT NOT NULL,
    "module" TEXT NOT NULL,
    "variantType" TEXT NOT NULL,
    "status" "TestStatus" NOT NULL DEFAULT 'passed',
    "durationMs" INTEGER NOT NULL DEFAULT 0,
    "healed" BOOLEAN NOT NULL DEFAULT false,
    "errorSummary" TEXT,
    "specPreview" TEXT,
    "category" TEXT,
    "requirementRef" TEXT,
    "priority" TEXT,
    "input" TEXT,
    "expected" TEXT,
    "actualOutput" TEXT,
    "judgeReasoning" TEXT,
    "judgeScore" INTEGER,
    "brdReference" TEXT,
    "acceptanceCriterion" TEXT,
    "criterionCode" TEXT,
    "runId" TEXT NOT NULL,

    CONSTRAINT "TestCase_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Recommendation" (
    "id" TEXT NOT NULL,
    "category" "RecommendationCategory" NOT NULL,
    "severity" "Severity" NOT NULL,
    "summary" TEXT NOT NULL,
    "evidenceRef" TEXT NOT NULL,
    "evidenceType" "EvidenceType" NOT NULL,
    "runId" TEXT NOT NULL,

    CONSTRAINT "Recommendation_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "User_email_key" ON "User"("email");

-- CreateIndex
CREATE UNIQUE INDEX "Session_tokenHash_key" ON "Session"("tokenHash");

-- CreateIndex
CREATE INDEX "Session_userId_idx" ON "Session"("userId");

-- CreateIndex
CREATE INDEX "Project_userId_idx" ON "Project"("userId");

-- CreateIndex
CREATE INDEX "Run_projectId_idx" ON "Run"("projectId");

-- CreateIndex
CREATE INDEX "RunStep_runId_idx" ON "RunStep"("runId");

-- CreateIndex
CREATE UNIQUE INDEX "RunStep_runId_key_key" ON "RunStep"("runId", "key");

-- CreateIndex
CREATE INDEX "RunEvent_runId_createdAt_idx" ON "RunEvent"("runId", "createdAt");

-- CreateIndex
CREATE INDEX "Requirement_runId_idx" ON "Requirement"("runId");

-- CreateIndex
CREATE INDEX "AcceptanceCriterion_requirementId_idx" ON "AcceptanceCriterion"("requirementId");

-- CreateIndex
CREATE UNIQUE INDEX "AcceptanceCriterion_runId_code_key" ON "AcceptanceCriterion"("runId", "code");

-- CreateIndex
CREATE INDEX "Evidence_runId_criterionId_idx" ON "Evidence"("runId", "criterionId");

-- CreateIndex
CREATE INDEX "Finding_runId_severity_idx" ON "Finding"("runId", "severity");

-- CreateIndex
CREATE UNIQUE INDEX "RepoSnapshot_repoFullName_commitSha_indexerVersion_key" ON "RepoSnapshot"("repoFullName", "commitSha", "indexerVersion");

-- CreateIndex
CREATE INDEX "KgNode_snapshotId_kind_idx" ON "KgNode"("snapshotId", "kind");

-- CreateIndex
CREATE UNIQUE INDEX "KgNode_snapshotId_key_key" ON "KgNode"("snapshotId", "key");

-- CreateIndex
CREATE INDEX "KgEdge_snapshotId_dst_idx" ON "KgEdge"("snapshotId", "dst");

-- CreateIndex
CREATE INDEX "CodeChunk_snapshotId_filePath_idx" ON "CodeChunk"("snapshotId", "filePath");

-- CreateIndex
CREATE INDEX "Scenario_runId_idx" ON "Scenario"("runId");

-- CreateIndex
CREATE INDEX "TestCase_runId_idx" ON "TestCase"("runId");

-- CreateIndex
CREATE INDEX "Recommendation_runId_idx" ON "Recommendation"("runId");

-- AddForeignKey
ALTER TABLE "Session" ADD CONSTRAINT "Session_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Project" ADD CONSTRAINT "Project_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Run" ADD CONSTRAINT "Run_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES "Project"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "RunStep" ADD CONSTRAINT "RunStep_runId_fkey" FOREIGN KEY ("runId") REFERENCES "Run"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "RunEvent" ADD CONSTRAINT "RunEvent_runId_fkey" FOREIGN KEY ("runId") REFERENCES "Run"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Requirement" ADD CONSTRAINT "Requirement_runId_fkey" FOREIGN KEY ("runId") REFERENCES "Run"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "AcceptanceCriterion" ADD CONSTRAINT "AcceptanceCriterion_requirementId_fkey" FOREIGN KEY ("requirementId") REFERENCES "Requirement"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "AcceptanceCriterion" ADD CONSTRAINT "AcceptanceCriterion_runId_fkey" FOREIGN KEY ("runId") REFERENCES "Run"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Evidence" ADD CONSTRAINT "Evidence_criterionId_fkey" FOREIGN KEY ("criterionId") REFERENCES "AcceptanceCriterion"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Evidence" ADD CONSTRAINT "Evidence_runId_fkey" FOREIGN KEY ("runId") REFERENCES "Run"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Finding" ADD CONSTRAINT "Finding_runId_fkey" FOREIGN KEY ("runId") REFERENCES "Run"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "KgNode" ADD CONSTRAINT "KgNode_snapshotId_fkey" FOREIGN KEY ("snapshotId") REFERENCES "RepoSnapshot"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "KgEdge" ADD CONSTRAINT "KgEdge_snapshotId_fkey" FOREIGN KEY ("snapshotId") REFERENCES "RepoSnapshot"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "CodeChunk" ADD CONSTRAINT "CodeChunk_snapshotId_fkey" FOREIGN KEY ("snapshotId") REFERENCES "RepoSnapshot"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Scenario" ADD CONSTRAINT "Scenario_runId_fkey" FOREIGN KEY ("runId") REFERENCES "Run"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "TestCase" ADD CONSTRAINT "TestCase_runId_fkey" FOREIGN KEY ("runId") REFERENCES "Run"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Recommendation" ADD CONSTRAINT "Recommendation_runId_fkey" FOREIGN KEY ("runId") REFERENCES "Run"("id") ON DELETE CASCADE ON UPDATE CASCADE;
