"use client";

import { RadialBar, RadialBarChart, PolarAngleAxis } from "recharts";
import { SectionCard } from "@/components/shared/section-card";
import { StatusPill } from "@/components/shared/status-pill";
import { ProgressBar } from "@/components/motion/progress-bar";
import { CountUp } from "@/components/motion/count-up";
import { useChartAnimation } from "@/components/motion/chart-reveal";
import { band } from "@/lib/insights";
import { BAND_TONE } from "@/lib/status";
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

export function QualityScoreCard({
  score,
  breakdown,
  healingPenalty,
  riskLevel,
  criticalDefects,
  title = "Quality score",
}: QualityScoreCardProps) {
  const chart = useChartAnimation();
  // one band rule everywhere (lib/insights → band(): ≥ 75 good · 50–75 warn · < 50 bad)
  const data = [{ name: "score", value: score ?? 0, fill: score == null ? "var(--muted)" : `var(--${BAND_TONE[band(score)]})` }];

  return (
    <SectionCard title={title}>
      <div className="flex flex-col gap-6 sm:flex-row sm:items-center">
        <div className="relative mx-auto size-32 shrink-0 sm:mx-0">
          <RadialBarChart width={128} height={128} innerRadius="72%" outerRadius="100%" barSize={10} data={data} startAngle={90} endAngle={-270}>
            <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
            <RadialBar dataKey="value" cornerRadius={8} background={{ fill: "var(--muted)" }} {...chart} />
          </RadialBarChart>
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
            {score == null ? (
              <span className="text-sm font-medium text-muted-foreground">Not scored</span>
            ) : (
              <>
                <CountUp value={Math.round(score)} className="text-3xl font-bold" />
                <span className="text-2xs text-muted-foreground">/ 100</span>
              </>
            )}
          </div>
        </div>

        <div className="min-w-0 flex-1 space-y-2.5">
          {breakdown.map((b) => (
            <div key={b.label} className="grid grid-cols-[minmax(0,1fr)_minmax(5rem,1fr)_3.5rem] items-center gap-3 text-sm sm:grid-cols-[minmax(0,11rem)_1fr_3.5rem]">
              <span className="truncate text-muted-foreground">{b.label}</span>
              <ProgressBar value={(b.score / b.max) * 100} tone="info" label={b.label} />
              <span className="text-right font-mono text-xs tabular-nums">{b.score}/{b.max}</span>
            </div>
          ))}
          {healingPenalty ? (
            <div className="grid grid-cols-[minmax(0,1fr)_minmax(5rem,1fr)_3.5rem] items-center gap-3 text-sm sm:grid-cols-[minmax(0,11rem)_1fr_3.5rem]">
              <span className="truncate text-muted-foreground">Healing penalty</span>
              <ProgressBar value={Math.min(100, healingPenalty * 10)} tone="critical" label="Healing penalty" />
              <span className="text-right font-mono text-xs text-critical-fg tabular-nums">−{healingPenalty}</span>
            </div>
          ) : null}

          <div className="flex flex-wrap items-center gap-2 pt-2">
            <StatusPill status={riskLevel} />
            {criticalDefects > 0 && (
              <span className="text-xs text-muted-foreground">
                {criticalDefects} critical defect{criticalDefects === 1 ? "" : "s"}
              </span>
            )}
          </div>
        </div>
      </div>
    </SectionCard>
  );
}
