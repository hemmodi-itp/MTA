"use client";

import Link from "next/link";
import { m } from "framer-motion";
import { itemMotion } from "@/components/motion/stagger";
import { ScoreBadge } from "@/components/shared/score";
import { ease, stagger } from "@/lib/motion";
import type { ProjectHealth } from "@/lib/insights";

function fmtDuration(sec: number | null) {
  if (!sec) return "—";
  const mins = Math.round(sec / 60);
  return mins >= 60 ? `${Math.floor(mins / 60)}h ${mins % 60}m` : `${mins}m`;
}

/**
 * Per-project performance as a list (it fits any column width without clipping): compliance, runtime test outcomes
 * as a stacked bar, verification depth and duration. The bar grows in from the left with a transform.
 */
export function PerformanceMatrix({ items }: { items: ProjectHealth[] }) {
  return (
    <div className="space-y-3">
      <m.ul variants={stagger()} initial="hidden" animate="show" className="divide-y divide-border">
        {items.map((h, i) => {
          const s = h.run.stats;
          const total = s.passed + s.failed + s.skipped || 1;
          return (
            <m.li key={h.projectId} {...itemMotion(i)} className="space-y-2 py-3 first:pt-0 last:pb-0">
              <div className="flex items-center justify-between gap-3">
                <Link href={`/runs/${h.run.id}`} className="min-w-0 truncate rounded-sm text-sm font-medium transition-colors duration-(--dur-micro) hover:text-info-fg">
                  {h.name}
                </Link>
                <ScoreBadge score={h.score} title="BRD compliance" />
              </div>
              <div className="flex items-center gap-3">
                <m.div
                  className="flex h-2 flex-1 origin-left overflow-hidden rounded-full bg-muted"
                  initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 0.6, ease: ease.enter, delay: 0.03 * Math.min(i, 20) }}
                  role="img" aria-label={`${s.passed} passed, ${s.failed} failed, ${s.skipped} inconclusive or not run`}
                >
                  <span className="bg-success" style={{ width: `${(100 * s.passed) / total}%` }} />
                  <span className="bg-critical" style={{ width: `${(100 * s.failed) / total}%` }} />
                  <span className="bg-muted-foreground/40" style={{ width: `${(100 * s.skipped) / total}%` }} />
                </m.div>
                <span className="shrink-0 text-xs tabular-nums">
                  <span className="text-success-fg">{s.passed}</span>
                  <span className="text-muted-foreground"> / </span>
                  <span className="text-critical-fg">{s.failed}</span>
                  <span className="text-muted-foreground"> / {s.skipped}</span>
                </span>
              </div>
              <p className="text-2xs text-muted-foreground">
                {h.depth != null ? `${Math.round(h.depth * 100)}% runtime-verified` : "Not runtime-verified"} · took {fmtDuration(h.run.durationSec)}
              </p>
            </m.li>
          );
        })}
      </m.ul>
      <p className="text-2xs text-muted-foreground">Runtime tests: passed / failed / inconclusive or not run, latest run per project.</p>
    </div>
  );
}
