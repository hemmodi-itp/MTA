"use client";

import { use } from "react";
import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/shared/error-state";
import { QualityScoreCard } from "@/components/reports/quality-score-card";
import { RecommendationCard } from "@/components/reports/recommendation-card";
import { useRun, useRecommendations } from "@/lib/query/hooks";
import { scoreOf } from "@/lib/insights";

const RISK_COPY: Record<string, string> = {
  low: "This run looks safe to ship — no critical issues found.",
  medium: "A few issues need a human look before this ships with confidence.",
  high: "Critical issues found — review before relying on this build.",
};

export default function ReportDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const run = useRun(id);
  const recommendations = useRecommendations(id);

  if (run.isLoading) return <Skeleton className="h-96 rounded-lg" />;
  if (run.isError || !run.data) return <ErrorState message="Report not found." onRetry={run.refetch} />;

  const data = run.data;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold">Quality Report</h1>
          <p className="text-sm text-muted-foreground">{data.projectName} · run {data.id}</p>
        </div>
        <Button className="gap-2">
          <Download className="size-4" />
          Download PDF
        </Button>
      </div>

      <QualityScoreCard
        score={scoreOf(data)}
        breakdown={data.qualityBreakdown}
        healingPenalty={4}
        riskLevel={data.stats.riskLevel}
        criticalDefects={data.stats.criticalDefects}
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground">Plain-language summary</CardTitle>
        </CardHeader>
        <CardContent className="text-sm leading-relaxed">
          <p>
            {data.stats.passed} of {data.stats.passed + data.stats.failed} test cases passed
            ({Math.round((data.stats.passed / (data.stats.passed + data.stats.failed || 1)) * 100)}%). {data.stats.healed} were
            automatically fixed. {RISK_COPY[data.stats.riskLevel]}
          </p>
        </CardContent>
      </Card>

      <div>
        <h2 className="mb-2 text-sm font-medium text-muted-foreground">Suggestions &amp; improvements</h2>
        <div className="space-y-2">
          {(recommendations.data ?? []).map((r) => (
            <RecommendationCard key={r.id} recommendation={r} />
          ))}
        </div>
      </div>
    </div>
  );
}
