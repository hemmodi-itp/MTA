"use client";

import { RadialBar, RadialBarChart, PolarAngleAxis } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusPill } from "@/components/shared/status-pill";
import type { QualityBreakdown, RiskLevel } from "@/lib/types";

interface QualityScoreCardProps {
  /** null = the run was not scored: the ring stays empty and reads "Not scored". */
  score: number | null;
  breakdown: QualityBreakdown[];
  /** Legacy Playwright runs only; omitted for agent evaluations. */
  healingPenalty?: number;
  title?: string;
  riskLevel: RiskLevel;
  criticalDefects: number;
}

function scoreColor(score: number) {
  if (score >= 80) return "var(--success)";
  if (score >= 60) return "var(--warning)";
  return "var(--critical)";
}

export function QualityScoreCard({
  score,
  breakdown,
  healingPenalty,
  riskLevel,
  criticalDefects,
  title = "Quality score",
}: QualityScoreCardProps) {
  const data = [{ name: "score", value: score ?? 0, fill: score == null ? "var(--muted)" : scoreColor(score) }];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-6 sm:flex-row sm:items-center">
        <div className="relative mx-auto size-32 shrink-0 sm:mx-0">
          <RadialBarChart
            width={128}
            height={128}
            innerRadius="72%"
            outerRadius="100%"
            barSize={10}
            data={data}
            startAngle={90}
            endAngle={-270}
          >
            <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
            <RadialBar dataKey="value" cornerRadius={8} background={{ fill: "var(--muted)" }} />
          </RadialBarChart>
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
            {score == null ? (
              <span className="text-sm font-medium text-muted-foreground">Not scored</span>
            ) : (
              <>
                <span className="font-mono text-3xl font-bold tabular-nums">{Math.round(score)}</span>
                <span className="text-[11px] text-muted-foreground">/ 100</span>
              </>
            )}
          </div>
        </div>

        <div className="flex-1 space-y-2.5">
          {breakdown.map((b) => (
            <div key={b.label} className="flex items-center gap-3 text-sm">
              <span className="w-48 shrink-0 text-muted-foreground">{b.label}</span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                <div className="h-full rounded-full bg-primary" style={{ width: `${(b.score / b.max) * 100}%` }} />
              </div>
              <span className="w-14 shrink-0 text-right font-mono text-xs tabular-nums">
                {b.score}/{b.max}
              </span>
            </div>
          ))}
          {healingPenalty ? (
          <div className="flex items-center gap-3 text-sm">
            <span className="w-40 shrink-0 text-muted-foreground">Healing Penalty</span>
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
              <div className="h-full rounded-full bg-critical" style={{ width: `${Math.min(100, healingPenalty * 10)}%` }} />
            </div>
            <span className="w-14 shrink-0 text-right font-mono text-xs tabular-nums text-critical">
              −{healingPenalty}
            </span>
          </div>
          ) : null}

          <div className="flex items-center gap-2 pt-2">
            <StatusPill status={riskLevel} />
            {criticalDefects > 0 && (
              <span className="text-xs text-muted-foreground">
                {criticalDefects} critical defect{criticalDefects === 1 ? "" : "s"}
              </span>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
