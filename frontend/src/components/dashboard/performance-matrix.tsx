"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { listItem, stagger } from "@/lib/motion";
import { band, type ProjectHealth } from "@/lib/insights";

const BAND_TEXT = { good: "text-success", warn: "text-warning", bad: "text-critical", none: "text-muted-foreground" } as const;

function fmtDuration(sec: number | null) {
  if (!sec) return "—";
  const m = Math.round(sec / 60);
  return m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m}m`;
}

/** Per-project performance: compliance, runtime test outcomes (stacked bar), depth and duration. Rows stagger in. */
export function PerformanceMatrix({ items }: { items: ProjectHealth[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] text-sm">
        <thead>
          <tr className="text-left text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            <th className="pb-2 font-semibold">Project</th>
            <th className="pb-2 text-right font-semibold">Compliance</th>
            <th className="w-[36%] pb-2 pl-4 font-semibold">Runtime tests</th>
            <th className="pb-2 text-right font-semibold">Verified</th>
            <th className="hidden pb-2 text-right font-semibold 2xl:table-cell">Duration</th>
          </tr>
        </thead>
        <motion.tbody variants={stagger(0.05)} initial="hidden" animate="show">
          {items.map((h) => {
            const s = h.run.stats;
            const total = s.passed + s.failed + s.skipped || 1;
            return (
              <motion.tr key={h.projectId} variants={listItem} className="border-t border-border">
                <td className="py-2.5 pr-3">
                  <Link href={`/runs/${h.run.id}`} className="font-medium hover:text-primary">{h.name}</Link>
                </td>
                <td className={cn("py-2.5 text-right font-semibold tabular-nums", BAND_TEXT[band(h.score)])}>
                  {h.score != null ? Math.round(h.score) : "—"}
                </td>
                <td className="py-2.5 pl-4">
                  <div className="flex items-center gap-2">
                    <div className="flex h-2 flex-1 overflow-hidden rounded-full bg-muted">
                      {[["passed", s.passed, "bg-success"], ["failed", s.failed, "bg-critical"], ["other", s.skipped, "bg-muted-foreground/40"]].map(([k, n, c]) => (
                        <motion.span key={k as string} className={c as string} initial={{ width: 0 }}
                          animate={{ width: `${(100 * (n as number)) / total}%` }} transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }} />
                      ))}
                    </div>
                    <span className="w-16 shrink-0 text-right text-xs tabular-nums text-muted-foreground">{s.passed}/{s.failed}/{s.skipped}</span>
                  </div>
                </td>
                <td className="py-2.5 text-right tabular-nums text-muted-foreground">{h.depth != null ? `${Math.round(h.depth * 100)}%` : "—"}</td>
                <td className="hidden py-2.5 text-right tabular-nums text-muted-foreground 2xl:table-cell">{fmtDuration(h.run.durationSec)}</td>
              </motion.tr>
            );
          })}
        </motion.tbody>
      </table>
      <p className="mt-2 text-[11px] text-muted-foreground">Runtime tests: passed / failed / inconclusive or not run, latest run per project.</p>
    </div>
  );
}
