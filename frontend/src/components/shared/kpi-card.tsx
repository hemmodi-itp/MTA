"use client";

import { useId } from "react";
import { ArrowDownRight, ArrowUpRight, type LucideIcon } from "lucide-react";
import { Area, AreaChart, ResponsiveContainer } from "recharts";
import { MotionCard } from "@/components/motion/motion-card";
import { CountUp } from "@/components/motion/count-up";
import { useChartAnimation } from "@/components/motion/chart-reveal";
import { cn } from "@/lib/utils";
import { TONE_CLASS, type Tone } from "@/lib/status";

/**
 * The one KPI card. Numbers count up (and stay put under reduced motion); strings render as they are. The label row
 * reserves two lines in dense grids so every value in a row lines up even when one label wraps.
 */
export function KpiCard({
  label,
  value,
  decimals = 0,
  prefix = "",
  suffix = "",
  sub,
  icon: Icon,
  tone = "info",
  valueTone,
  delta,
  deltaGoodWhen = "up",
  spark,
  size = "md",
  className,
}: {
  label: string;
  value: number | React.ReactNode;
  decimals?: number;
  prefix?: string;
  suffix?: string;
  sub?: React.ReactNode;
  icon?: LucideIcon;
  /** colour of the icon chip and sparkline */
  tone?: Tone;
  /** colour of the value itself (e.g. the score band); default is the foreground colour */
  valueTone?: Tone;
  delta?: number | null;
  deltaGoodWhen?: "up" | "down";
  spark?: { level: number | null }[];
  size?: "md" | "sm";
  className?: string;
}) {
  const chart = useChartAnimation();
  const gradientId = `spark-${useId().replace(/:/g, "")}`;
  const good = delta != null && (deltaGoodWhen === "up" ? delta > 0 : delta < 0);
  const showSpark = !!spark && spark.some((p) => p.level != null);
  return (
    <MotionCard interactive={false} className={cn("relative flex h-full min-w-0 flex-col overflow-hidden", size === "md" ? "p-5" : "p-4", className)}>
      <div className="flex items-start justify-between gap-3">
        <p className={cn("type-eyebrow text-muted-foreground", size === "sm" && "line-clamp-2 min-h-8")}>{label}</p>
        {Icon && (
          <span className={cn("flex size-8 shrink-0 items-center justify-center rounded-lg tone-tint tone-text", TONE_CLASS[tone])}>
            <Icon aria-hidden className="size-4" />
          </span>
        )}
      </div>
      <div className={cn("flex flex-wrap items-baseline gap-x-2 gap-y-1", size === "md" ? "mt-2" : "mt-1.5")}>
        <span className={cn(size === "md" ? "type-kpi" : "type-kpi-sm", valueTone && cn(TONE_CLASS[valueTone], "tone-text"))}>
          {typeof value === "number" ? <CountUp value={value} decimals={decimals} prefix={prefix} suffix={suffix} /> : value ?? "—"}
        </span>
        {delta != null && delta !== 0 && (
          <span className={cn("pill h-5 gap-0.5 px-1.5 text-2xs font-semibold tone-tint tone-border tone-text", good ? "tone-success" : "tone-critical")}>
            {delta > 0 ? <ArrowUpRight aria-hidden className="size-3" /> : <ArrowDownRight aria-hidden className="size-3" />}
            <span className="sr-only">{delta > 0 ? "up" : "down"}</span>
            {Math.abs(delta)}
          </span>
        )}
      </div>
      {sub && <p className="mt-1.5 text-xs text-pretty text-muted-foreground">{sub}</p>}
      {showSpark && (
        <div aria-hidden className={cn("mt-auto pt-3", size === "md" ? "-mx-5 -mb-5" : "-mx-4 -mb-4")}>
          <div className="h-12">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={spark} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={`var(--${tone})`} stopOpacity={0.3} />
                    <stop offset="100%" stopColor={`var(--${tone})`} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <Area type="monotone" dataKey="level" stroke={`var(--${tone})`} strokeWidth={2} fill={`url(#${gradientId})`} connectNulls {...chart} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </MotionCard>
  );
}
