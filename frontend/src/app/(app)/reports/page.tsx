"use client";

import Link from "next/link";
import { FileBarChart2, ChevronRight } from "lucide-react";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useRuns } from "@/lib/query/hooks";
import { formatScore, scoreOf } from "@/lib/insights";

export default function ReportsPage() {
  const { data, isLoading, isError, refetch } = useRuns();
  const completed = (data ?? []).filter((r) => r.status === "completed");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Reports</h1>
        <p className="text-sm text-muted-foreground">Quality reports generated per run.</p>
      </div>

      {isError ? (
        <ErrorState onRetry={refetch} />
      ) : isLoading ? (
        <Skeleton className="h-48 rounded-lg" />
      ) : !completed.length ? (
        <EmptyState icon={FileBarChart2} title="No reports yet" description="Reports appear once a run completes." />
      ) : (
        <Card className="divide-y divide-border p-0">
          {completed.map((r) => (
            <Link key={r.id} href={`/reports/${r.id}`} className="flex items-center gap-4 px-6 py-3 text-sm hover:bg-muted/50">
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{r.projectName}</p>
                <p className="text-xs text-muted-foreground">{new Date(r.startedAt).toLocaleDateString()}</p>
              </div>
              <span className="font-mono text-sm font-semibold tabular-nums" title={scoreOf(r) == null ? "Not scored" : undefined}>
                {formatScore(scoreOf(r))}
              </span>
              <ChevronRight className="size-4 text-muted-foreground" />
            </Link>
          ))}
        </Card>
      )}
    </div>
  );
}
