import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusPill } from "@/components/shared/status-pill";
import { formatScore, scoreOf } from "@/lib/insights";
import type { Run } from "@/lib/types";

function timeAgo(iso: string) {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export function RecentRunsList({ runs }: { runs: Run[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground">Recent runs</CardTitle>
      </CardHeader>
      <CardContent className="divide-y divide-border p-0">
        {runs.map((run) => (
          <Link
            key={run.id}
            href={`/runs/${run.id}`}
            className="flex items-center gap-4 px-6 py-3 text-sm transition-colors hover:bg-muted/50"
          >
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">
                {run.projectName}
                {run.projectIsSample && <span className="ml-2 text-xs font-normal text-muted-foreground">sample</span>}
              </p>
              <p className="text-xs text-muted-foreground">{timeAgo(run.startedAt)}</p>
            </div>
            <StatusPill status={run.status} />
            {run.status === "completed" && (
              <span className="w-10 text-right font-mono text-sm tabular-nums" title={scoreOf(run) == null ? "Not scored" : undefined}>
                {formatScore(scoreOf(run))}
              </span>
            )}
            <ChevronRight className="size-4 text-muted-foreground" />
          </Link>
        ))}
      </CardContent>
    </Card>
  );
}
