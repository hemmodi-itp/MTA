import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { notFound, requireUser, visibleRuns } from "@/lib/api/server/access";
import { mapFinding, mapRequirement } from "@/lib/api/server/mappers";
import type {
  ActionPlan,
  BrdCompliance,
  AgentProfile,
  AppClassification,
  EvidenceCollection,
  ExecutionRun,
  OutputValidation,
  PassFail,
  RunArtifacts,
  RuntimeProfile,
} from "@/lib/types";

const SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"];

/** Only the headline goes to the browser here; the full report (HTML/MD/JSON) has its own route. */
function reportHeadline(stored: unknown): RunArtifacts["finalReport"] {
  const data = (stored as { data?: { decision?: { outcome?: string; compliance?: number | null }; generated_at?: string } } | null)?.data;
  if (!data?.decision?.outcome) return null;
  return { outcome: data.decision.outcome, compliance: data.decision.compliance ?? null, generatedAt: data.generated_at ?? "" };
}

/** The BRD, agent profile, requirements (with criteria + evidence) and review findings of a run. */
export async function GET(_request: Request, { params }: { params: Promise<{ runId: string }> }) {
  const { user, response } = await requireUser();
  if (response) return response;
  const { runId } = await params;
  const run = await prisma.run.findFirst({
    where: { id: runId, ...visibleRuns(user.id) },
    select: {
      brdSource: true,
      brdPath: true,
      brdContent: true,
      agentProfile: true,
      requirements: {
        orderBy: { code: "asc" },
        include: { criteria: { orderBy: { code: "asc" }, include: { evidence: { orderBy: { createdAt: "asc" } } } } },
      },
      findings: true,
      runtimeProfile: true,
      appClassification: true,
      actionPlan: true,
      executionRun: true,
      evidenceCollection: true,
      outputValidation: true,
      passFail: true,
      brdCompliance: true,
      finalReport: true,
    },
  });
  if (!run) return notFound();

  const body: RunArtifacts = {
    brdSource: (run.brdSource as RunArtifacts["brdSource"]) ?? null,
    brdPath: run.brdPath,
    brdContent: run.brdContent,
    agentProfile: (run.agentProfile as unknown as AgentProfile) ?? null,
    requirements: run.requirements.map(mapRequirement),
    findings: [...run.findings]
      .sort((a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity))
      .map(mapFinding),
    runtimeProfile: (run.runtimeProfile as unknown as RuntimeProfile) ?? null,
    appClassification: (run.appClassification as unknown as AppClassification) ?? null,
    actionPlan: (run.actionPlan as unknown as ActionPlan) ?? null,
    executionRun: (run.executionRun as unknown as ExecutionRun) ?? null,
    evidenceCollection: (run.evidenceCollection as unknown as EvidenceCollection) ?? null,
    outputValidation: (run.outputValidation as unknown as OutputValidation) ?? null,
    passFail: (run.passFail as unknown as PassFail) ?? null,
    brdCompliance: (run.brdCompliance as unknown as BrdCompliance) ?? null,
    finalReport: reportHeadline(run.finalReport),
  };
  return NextResponse.json(body);
}
