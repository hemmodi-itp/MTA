"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { TEST_STATUS_OPTIONS, TestResultTable } from "@/components/test-cases/test-result-table";
import { ErrorState } from "@/components/shared/error-state";
import { useAllTestCases } from "@/lib/query/hooks";
import type { TestStatus } from "@/lib/types";

const STATUSES = TEST_STATUS_OPTIONS.map((o) => o.value as string);

function TestCases() {
  const { data, isLoading, isError, refetch, hasNextPage, fetchNextPage, isFetchingNextPage } = useAllTestCases();
  const params = useSearchParams();
  const status = params.get("status");
  const initial = (status && STATUSES.includes(status) ? status : "all") as TestStatus | "all";
  const rows = data?.pages.flatMap((p) => p.rows) ?? [];
  if (isError) return <ErrorState onRetry={refetch} />;
  if (isLoading) return <div className="shimmer h-72 rounded-2xl" />;
  return (
    <div className="space-y-3">
      <TestResultTable key={initial} data={rows} initialStatus={initial} />
      {hasNextPage && (
        <div className="flex items-center justify-center gap-3 text-xs text-muted-foreground">
          <span>Showing the first {rows.length} test cases.</span>
          <Button variant="outline" size="sm" onClick={() => fetchNextPage()} disabled={isFetchingNextPage}>
            {isFetchingNextPage && <Loader2 className="size-3.5 animate-spin" />} Load more
          </Button>
        </div>
      )}
    </div>
  );
}

export default function TestCasesPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Test cases</h1>
        <p className="text-sm text-muted-foreground">Every BRD-traced test, across every evaluation.</p>
      </div>
      <Suspense fallback={<div className="shimmer h-72 rounded-2xl" />}>
        <TestCases />
      </Suspense>
    </div>
  );
}
