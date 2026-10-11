"use client";

import { use, useState } from "react";
import Link from "next/link";
import { format } from "date-fns";
import { Download, ExternalLink, Lightbulb, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/shared/empty-state";
import { PageHeader, PageHeaderSkeleton } from "@/components/shared/page-header";
import { SectionCard } from "@/components/shared/section-card";
import { CardSkeleton } from "@/components/shared/skeletons";
import { Stagger, StaggerItem } from "@/components/motion/stagger";
import { ErrorState } from "@/components/shared/error-state";
import { QualityScoreCard } from "@/components/reports/quality-score-card";
import { RecommendationCard } from "@/components/reports/recommendation-card";
import { useRun, useRecommendations } from "@/lib/query/hooks";
import { scoreOf, shortName } from "@/lib/insights";

const RISK_COPY: Record<string, string> = {
  low: "This run looks safe to ship — no critical issues found.",
  medium: "A few issues need a human look before this ships with confidence.",
  high: "Critical issues found — review before relying on this build.",
};

/** Fetches the server-rendered PDF (the evaluation service renders it, which takes a few seconds) and saves it. */
async function downloadReportPdf(runId: string) {
  const res = await fetch(`/api/runs/${runId}/report?format=pdf`);
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as { error?: string } | null;
    throw new Error(body?.error ?? (res.status === 404 ? "This run has no final report to download." : "The PDF could not be downloaded."));
  }
  const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "")?.[1] ?? `mta-report-${runId}.pdf`;
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  URL.revokeObjectURL(url);
}

export default function ReportDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const run = useRun(id);
  const recommendations = useRecommendations(id);
  const [downloading, setDownloading] = useState(false);

  if (run.isLoading) {
    return (
      <>
        <PageHeaderSkeleton actions />
        <div className="max-w-3xl space-y-6"><CardSkeleton className="h-56" /><CardSkeleton className="h-32" /></div>
      </>
    );
  }
  if (run.isError || !run.data) {
    return <ErrorState title="Report not found" message="The run may have been removed, or it belongs to another account." onRetry={run.refetch} />;
  }

  const data = run.data;
  const onDownload = async () => {
    setDownloading(true);
    try {
      await downloadReportPdf(id);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "The PDF could not be downloaded.");
    } finally {
      setDownloading(false);
    }
  };

  const recs = recommendations.data ?? [];
  return (
    <>
      <PageHeader
        breadcrumb={[{ label: "Reports", href: "/reports" }, { label: shortName(data.projectName) }]}
        title="Quality report"
        description={<>{data.projectName} · evaluated {format(new Date(data.startedAt), "d MMM yyyy")}</>}
        actions={
          <>
            <Button asChild variant="outline" className="gap-1.5">
              <Link href={`/runs/${data.id}`}><ExternalLink aria-hidden className="size-3.5" /> Open run</Link>
            </Button>
            <Button className="gap-2" onClick={onDownload} disabled={downloading}>
              {downloading ? <Loader2 aria-hidden className="size-4 animate-spin" /> : <Download aria-hidden className="size-4" />}
              {downloading ? "Preparing PDF…" : "Download PDF"}
            </Button>
          </>
        }
      />

      <div className="max-w-3xl space-y-6">
        <QualityScoreCard
          score={scoreOf(data)}
          breakdown={data.qualityBreakdown}
          healingPenalty={4}
          riskLevel={data.stats.riskLevel}
          criticalDefects={data.stats.criticalDefects}
        />

        <SectionCard title="Plain-language summary">
          <p className="text-sm leading-relaxed text-pretty">
            {data.stats.passed} of {data.stats.passed + data.stats.failed} test cases passed
            ({Math.round((data.stats.passed / (data.stats.passed + data.stats.failed || 1)) * 100)}%). {data.stats.healed} were
            automatically fixed. {RISK_COPY[data.stats.riskLevel]}
          </p>
        </SectionCard>

        <section className="space-y-3">
          <h2 className="type-section-title">Suggestions &amp; improvements</h2>
          {recommendations.isLoading ? (
            <CardSkeleton className="h-24" />
          ) : recs.length ? (
            <Stagger className="space-y-2">
              {recs.map((r, i) => (
                <StaggerItem key={r.id} index={i}><RecommendationCard recommendation={r} /></StaggerItem>
              ))}
            </Stagger>
          ) : (
            <EmptyState size="inline" icon={Lightbulb} title="No suggestions" description="This run produced no recommendations." />
          )}
        </section>
      </div>
    </>
  );
}
