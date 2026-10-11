"use client";

import { Cell, Pie, PieChart, ResponsiveContainer } from "recharts";
import { CountUp } from "@/components/motion/count-up";
import { ChartReveal, useChartAnimation } from "@/components/motion/chart-reveal";
import { isActive } from "@/lib/insights";
import type { Run } from "@/lib/types";

/** Donut of run outcomes (completed / running / failed / cancelled) with an animated total in the middle. */
export function StatusOverview({ runs }: { runs: Run[] }) {
  const chart = useChartAnimation();
  // colours from the status registry's tones: completed = success, running = info, failed = critical, cancelled = neutral
  const parts = [
    { key: "completed", label: "Completed", color: "var(--success)", n: runs.filter((r) => r.status === "completed").length },
    { key: "running", label: "Running", color: "var(--info)", n: runs.filter(isActive).length },
    { key: "failed", label: "Failed", color: "var(--critical)", n: runs.filter((r) => r.status === "failed").length },
    { key: "cancelled", label: "Cancelled", color: "var(--neutral)", n: runs.filter((r) => r.status === "cancelled").length },
  ];
  const data = parts.filter((p) => p.n > 0);
  return (
    <div className="flex flex-col items-center gap-5 sm:flex-row lg:flex-col xl:flex-row 2xl:flex-col">
      <ChartReveal className="relative size-36 shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data.length ? data : [{ key: "none", n: 1, color: "var(--muted)" }]} dataKey="n" innerRadius="70%" outerRadius="100%"
              paddingAngle={data.length > 1 ? 3 : 0} stroke="none" startAngle={90} endAngle={-270} {...chart}>
              {(data.length ? data : [{ key: "none", color: "var(--muted)" }]).map((p) => <Cell key={p.key} fill={p.color} />)}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <CountUp value={runs.length} className="text-2xl font-bold" />
          <span className="text-2xs text-muted-foreground">runs</span>
        </div>
      </ChartReveal>
      <ul className="w-full min-w-0 flex-1 space-y-2.5">
        {parts.map((p) => (
          <li key={p.key} className="flex items-center gap-2 text-sm">
            <span aria-hidden className="size-2.5 rounded-full" style={{ background: p.color }} />
            <span className="flex-1 text-muted-foreground">{p.label}</span>
            <span className="font-semibold tabular-nums">{p.n}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
