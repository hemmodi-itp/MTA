import "dotenv/config";
import { PrismaClient, Prisma } from "@prisma/client";
import { PrismaPg } from "@prisma/adapter-pg";
import {
  MOCK_PROJECTS,
  MOCK_RUNS,
  MOCK_SCENARIOS,
  MOCK_TEST_CASES,
  MOCK_RECOMMENDATIONS,
} from "../src/lib/mock-data";

const adapter = new PrismaPg({ connectionString: process.env.DATABASE_URL });
const prisma = new PrismaClient({ adapter });

async function main() {
  // Re-seed only the shared sample projects (runs, tests etc. cascade). Users' own
  // projects are never touched, so this stays safe to re-run.
  await prisma.project.deleteMany({ where: { OR: [{ isSample: true }, { id: { in: MOCK_PROJECTS.map((p) => p.id) } }] } });

  for (const p of MOCK_PROJECTS) {
    await prisma.project.create({
      data: {
        id: p.id,
        name: p.name,
        githubUrl: p.githubUrl,
        branch: p.branch,
        lastRunStatus: p.lastRunStatus,
        lastQualityScore: p.lastQualityScore,
        isSample: true,
        updatedAt: new Date(p.updatedAt),
      },
    });
  }

  for (const r of MOCK_RUNS) {
    await prisma.run.create({
      data: {
        id: r.id,
        projectId: r.projectId,
        status: r.status,
        currentStage: r.currentStage,
        startedAt: new Date(r.startedAt),
        finishedAt: r.finishedAt ? new Date(r.finishedAt) : null,
        durationSec: r.durationSec,
        scenariosFound: r.stats.scenariosFound,
        testCasesGenerated: r.stats.testCasesGenerated,
        passed: r.stats.passed,
        failed: r.stats.failed,
        healed: r.stats.healed,
        skipped: r.stats.skipped,
        coveragePct: r.stats.coveragePct,
        qualityScore: r.stats.qualityScore,
        riskLevel: r.stats.riskLevel,
        criticalDefects: r.stats.criticalDefects,
        duplicatesRejected: r.stats.duplicatesRejected,
        qualityBreakdown: r.qualityBreakdown as unknown as Prisma.InputJsonValue,
        trend: r.trend as unknown as Prisma.InputJsonValue,
      },
    });
  }

  for (const s of MOCK_SCENARIOS) {
    await prisma.scenario.create({
      data: { id: s.id, runId: s.runId, title: s.title, module: s.module, confidence: s.confidence },
    });
  }

  for (const t of MOCK_TEST_CASES) {
    await prisma.testCase.create({
      data: {
        id: t.id,
        runId: t.runId,
        scenarioTitle: t.scenarioTitle,
        module: t.module,
        variantType: t.variantType,
        status: t.status,
        durationMs: t.durationMs,
        healed: t.healed,
        errorSummary: t.errorSummary,
        specPreview: t.specPreview,
      },
    });
  }

  for (const rec of MOCK_RECOMMENDATIONS) {
    await prisma.recommendation.create({
      data: {
        id: rec.id,
        runId: rec.runId,
        category: rec.category,
        severity: rec.severity,
        summary: rec.summary,
        evidenceRef: rec.evidenceRef,
        evidenceType: rec.evidenceType,
      },
    });
  }

  console.log(
    `Seeded ${MOCK_PROJECTS.length} projects, ${MOCK_RUNS.length} runs, ${MOCK_SCENARIOS.length} scenarios, ${MOCK_TEST_CASES.length} test cases, ${MOCK_RECOMMENDATIONS.length} recommendations.`
  );
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
