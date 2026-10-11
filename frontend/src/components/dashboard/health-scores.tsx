"use client";

import Link from "next/link";
import { m } from "framer-motion";
import { ArrowDownRight, ArrowUpRight, ShieldAlert } from "lucide-react";
import { CountUp } from "@/components/motion/count-up";
import { Stagger, StaggerItem } from "@/components/motion/stagger";
import { cn } from "@/lib/utils";
import { ease } from "@/lib/motion";
import { band, type ProjectHealth } from "@/lib/insights";
import { BAND_TONE } from "@/lib/status";
import { usePrefersReducedMotion } from "@/hooks/use-reduced-motion";

/** Score ring: the arc draws in once (600 ms), in the score's band colour; static under reduced motion. */
function Ring({ value, size = 64 }: { value: number | null; size?: number }) {
  const reduced = usePrefersReducedMotion();
  const r = (size - 8) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, value ?? 0)) / 100;
  return (
    <svg aria-hidden width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--muted)" strokeWidth={6} />
      <m.circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={`var(--${BAND_TONE[band(value)]})`} strokeWidth={6} strokeLinecap="round"
        strokeDasharray={c} initial={reduced ? false : { strokeDashoffset: c }} animate={{ strokeDashoffset: c * (1 - pct) }}
        transition={{ duration: 0.6, ease: ease.enter }} />
    </svg>
  );
}

/** Project health: one ring per project (latest compliance), riskiest first, with delta and blocking gates. */
export function HealthScores({ items }: { items: ProjectHealth[] }) {
  return (
    <Stagger className="grid gap-3 sm:grid-cols-2">
      {items.slice(0, 6).map((h, i) => (
        <StaggerItem key={h.projectId} index={i}>
          <Link href={`/runs/${h.run.id}`}
            className="group flex h-full items-center gap-4 rounded-xl border border-border bg-background/30 p-3 transition-colors duration-(--dur-micro) hover:border-primary/40 hover:bg-muted/40">
            <div className="relative shrink-0">
              <Ring value={h.score} />
              <span className="absolute inset-0 flex items-center justify-center text-sm font-bold">
                <CountUp value={h.score != null ? Math.round(h.score) : null} />
              </span>
            </div>
            <div className="min-w-0 flex-1">
              <p className="line-clamp-2 text-sm font-semibold break-words transition-colors duration-(--dur-micro) group-hover:text-info-fg">{h.name}</p>
              <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-2xs text-muted-foreground">
                {h.delta != null && h.delta !== 0 && (
                  <span className={cn("inline-flex items-center gap-0.5 font-semibold", h.delta > 0 ? "text-success-fg" : "text-critical-fg")}>
                    {h.delta > 0 ? <ArrowUpRight aria-hidden className="size-3" /> : <ArrowDownRight aria-hidden className="size-3" />}
                    <span className="sr-only">{h.delta > 0 ? "up" : "down"}</span>{Math.abs(h.delta)}
                  </span>
                )}
                {h.depth != null && <span>{Math.round(h.depth * 100)}% runtime-verified</span>}
                {h.blocks > 0 && <span className="inline-flex items-center gap-0.5 font-semibold text-critical-fg"><ShieldAlert aria-hidden className="size-3" />{h.blocks} blocking</span>}
              </div>
            </div>
          </Link>
        </StaggerItem>
      ))}
    </Stagger>
  );
}
