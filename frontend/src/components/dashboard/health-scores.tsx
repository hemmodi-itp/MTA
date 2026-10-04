"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowDownRight, ArrowUpRight, ShieldAlert } from "lucide-react";
import { CountUp } from "@/components/motion/count-up";
import { Stagger, StaggerItem } from "@/components/motion/stagger";
import { cn } from "@/lib/utils";
import { band, type ProjectHealth } from "@/lib/insights";

const RING = { good: "var(--chart-3)", warn: "var(--chart-4)", bad: "var(--chart-5)", none: "var(--muted-foreground)" } as const;

function Ring({ value, size = 64 }: { value: number | null; size?: number }) {
  const r = (size - 8) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, value ?? 0)) / 100;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--muted)" strokeWidth={6} />
      <motion.circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={RING[band(value)]} strokeWidth={6} strokeLinecap="round"
        strokeDasharray={c} initial={{ strokeDashoffset: c }} animate={{ strokeDashoffset: c * (1 - pct) }}
        transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }} />
    </svg>
  );
}

/** Project health: one ring per project (latest compliance), riskiest first, with delta and blocking gates. */
export function HealthScores({ items }: { items: ProjectHealth[] }) {
  return (
    <Stagger step={0.06} className="grid gap-3 sm:grid-cols-2">
      {items.slice(0, 6).map((h) => (
        <StaggerItem key={h.projectId}>
          <Link href={`/runs/${h.run.id}`} className="group flex items-center gap-4 rounded-xl border border-border bg-background/30 p-3 transition-colors hover:border-primary/40 hover:bg-muted/40">
            <div className="relative shrink-0">
              <Ring value={h.score} />
              <CountUp value={h.score != null ? Math.round(h.score) : null} className="absolute inset-0 flex items-center justify-center text-sm font-bold" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold group-hover:text-primary">{h.name}</p>
              <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
                {h.delta != null && h.delta !== 0 && (
                  <span className={cn("inline-flex items-center gap-0.5 font-semibold", h.delta > 0 ? "text-success" : "text-critical")}>
                    {h.delta > 0 ? <ArrowUpRight className="size-3" /> : <ArrowDownRight className="size-3" />}{Math.abs(h.delta)}
                  </span>
                )}
                {h.depth != null && <span>{Math.round(h.depth * 100)}% runtime-verified</span>}
                {h.blocks > 0 && <span className="inline-flex items-center gap-0.5 font-semibold text-critical"><ShieldAlert className="size-3" />{h.blocks} blocking</span>}
              </div>
            </div>
          </Link>
        </StaggerItem>
      ))}
    </Stagger>
  );
}
