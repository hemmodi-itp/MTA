"use client";

import { ArrowDownRight, ArrowUpRight, type LucideIcon } from "lucide-react";
import { Area, AreaChart, ResponsiveContainer } from "recharts";
import { MotionCard } from "@/components/motion/motion-card";
import { CountUp } from "@/components/motion/count-up";
import { cn } from "@/lib/utils";

const TONE = {
  primary: { text: "text-primary", bg: "bg-primary/12", stroke: "var(--chart-1)" },
  violet: { text: "text-violet", bg: "bg-violet/12", stroke: "var(--chart-2)" },
  good: { text: "text-success", bg: "bg-success/12", stroke: "var(--chart-3)" },
  warn: { text: "text-warning", bg: "bg-warning/12", stroke: "var(--chart-4)" },
  bad: { text: "text-critical", bg: "bg-critical/12", stroke: "var(--chart-5)" },
} as const;

/** KPI tile: count-up value, optional delta and a progressively drawn sparkline. */
export function KpiTile({ label, value, decimals = 0, suffix = "", sub, icon: Icon, tone = "primary", delta, deltaGoodWhen = "up", spark }: {
  label: string; value: number | null; decimals?: number; suffix?: string; sub?: string; icon: LucideIcon;
  tone?: keyof typeof TONE; delta?: number | null; deltaGoodWhen?: "up" | "down"; spark?: { level: number | null }[];
}) {
  const t = TONE[tone];
  const good = delta != null && (deltaGoodWhen === "up" ? delta > 0 : delta < 0);
  const id = `spark-${label.replace(/\W+/g, "")}`;
  return (
    <MotionCard className="relative overflow-hidden p-5">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">{label}</p>
        <span className={cn("flex size-8 items-center justify-center rounded-lg", t.bg, t.text)}><Icon className="size-4" /></span>
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <CountUp value={value} decimals={decimals} suffix={suffix} className="text-[34px] font-bold leading-none tracking-tight" />
        {delta != null && delta !== 0 && (
          <span className={cn("inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[11px] font-semibold",
            good ? "bg-success/12 text-success" : "bg-critical/12 text-critical")}>
            {delta > 0 ? <ArrowUpRight className="size-3" /> : <ArrowDownRight className="size-3" />}
            {Math.abs(delta)}
          </span>
        )}
      </div>
      {sub && <p className="mt-1.5 text-xs text-muted-foreground">{sub}</p>}
      {spark && spark.some((p) => p.level != null) && (
        <div className="-mx-5 -mb-5 mt-3 h-12">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={spark} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={t.stroke} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={t.stroke} stopOpacity={0} />
                </linearGradient>
              </defs>
              <Area type="monotone" dataKey="level" stroke={t.stroke} strokeWidth={2} fill={`url(#${id})`} connectNulls
                isAnimationActive animationDuration={1200} animationEasing="ease-out" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </MotionCard>
  );
}
