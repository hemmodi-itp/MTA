import Link from "next/link";
import { Bot, ChevronRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StatusPill } from "@/components/shared/status-pill";
import { scoreOf } from "@/lib/insights";
import type { Run, SubmissionMode } from "@/lib/types";

const MODE_SHORT: Record<SubmissionMode, string> = {
  brd_and_live: "BRD + live",
  live_only: "Live · generated BRD",
  brd_only: "BRD · static",
};

function scoreColor(score: number) {
  if (score >= 80) return "var(--success)";
  if (score >= 60) return "var(--warning)";
  return "var(--critical)";
}

/** Latest agent-evaluation result per project: the headline "does the agent meet its BRD" score. */
export function AgentScoresCard({ runs }: { runs: Run[] }) {
  // runs arrive newest first; keep each project's most recent agent-evaluation run
  const latest = new Map<string, Run>();
  for (const run of runs) {
    if (run.mode && !latest.has(run.projectId)) latest.set(run.projectId, run);
  }
  const rows = [...latest.values()];

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="text-sm font-medium text-muted-foreground">Agent scores</CardTitle>
        <Button asChild size="sm" variant="outline">
          <Link href="/projects/new">Evaluate an agent</Link>
        </Button>
      </CardHeader>
      <CardContent className="divide-y divide-border p-0">
        {rows.length === 0 ? (
          <div className="flex flex-col items-center gap-2 px-6 py-8 text-center text-sm text-muted-foreground">
            <Bot className="size-6" />
            No agents evaluated yet. Submit a public GitHub repository to get a BRD-based score.
          </div>
        ) : (
          rows.map((run) => {
            const done = run.status === "completed";
            const score = scoreOf(run);
            return (
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
                  <p className="text-xs text-muted-foreground">
                    {MODE_SHORT[run.mode!]}
                    {done && ` · ${run.stats.passed}/${run.stats.passed + run.stats.failed} tests passed · ${run.stats.coveragePct}% coverage`}
                  </p>
                </div>
                {done && score == null ? (
                  <span className="text-xs text-muted-foreground">Not scored</span>
                ) : done && score != null ? (
                  <>
                    <StatusPill status={run.stats.riskLevel} className="hidden sm:inline-flex" />
                    <div className="flex w-28 items-center gap-2">
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                        <div className="h-full rounded-full" style={{ width: `${score}%`, background: scoreColor(score) }} />
                      </div>
                      <span className="w-7 text-right font-mono text-sm font-semibold tabular-nums">{Math.round(score)}</span>
                    </div>
                  </>
                ) : (
                  <StatusPill status={run.status} />
                )}
                <ChevronRight className="size-4 text-muted-foreground" />
              </Link>
            );
          })
        )}
      </CardContent>
    </Card>
  );
}
