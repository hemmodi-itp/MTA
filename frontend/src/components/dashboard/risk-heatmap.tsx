"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { HEAT_DIMENSIONS, heatRow, type ProjectHealth } from "@/lib/insights";

function cellColor(v: number | null) {
  if (v == null) return "color-mix(in srgb, var(--muted) 70%, transparent)";
  // red (0) → amber (50) → green (100), translucent so the glass shows through
  const hue = v >= 75 ? "var(--chart-3)" : v >= 50 ? "var(--chart-4)" : "var(--chart-5)";
  const strength = 22 + Math.round((v >= 50 ? (v - 50) / 50 : (50 - v) / 50) * 50);
  return `color-mix(in srgb, ${hue} ${strength}%, transparent)`;
}

/** Projects × quality dimensions; colour = score band. Hover a cell for the number, click a row for the run. */
export function RiskHeatmap({ items }: { items: ProjectHealth[] }) {
  const rows = items.slice(0, 8);
  return (
    <div className="overflow-x-auto">
      <div className="min-w-[620px]">
        <div className="grid gap-1.5" style={{ gridTemplateColumns: `minmax(120px,1.2fr) repeat(${HEAT_DIMENSIONS.length}, minmax(52px,1fr))` }}>
          <span />
          {HEAT_DIMENSIONS.map((d) => (
            <span key={d.key} className="truncate pb-1 text-center text-[10px] font-semibold uppercase tracking-wide text-muted-foreground" title={d.label}>
              {d.label}
            </span>
          ))}
          {rows.map((h, ri) => {
            const row = heatRow(h);
            return [
              <Link key={`${h.projectId}-n`} href={`/runs/${h.run.id}`} className="flex items-center truncate pr-2 text-xs font-medium hover:text-primary">
                {h.name}
              </Link>,
              ...HEAT_DIMENSIONS.map((d, ci) => (
                <Tooltip key={`${h.projectId}-${d.key}`}>
                  <TooltipTrigger asChild>
                    <motion.div
                      initial={{ opacity: 0, scale: 0.6 }} animate={{ opacity: 1, scale: 1 }}
                      transition={{ delay: 0.02 * (ri * HEAT_DIMENSIONS.length + ci), duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                      whileHover={{ scale: 1.08 }}
                      className="flex h-9 items-center justify-center rounded-lg text-[11px] font-semibold tabular-nums ring-1 ring-inset ring-white/5"
                      style={{ background: cellColor(row[d.key]) }}
                    >
                      {row[d.key] != null ? Math.round(row[d.key] as number) : "–"}
                    </motion.div>
                  </TooltipTrigger>
                  <TooltipContent>{h.name} · {d.label}: {row[d.key] != null ? `${Math.round(row[d.key] as number)}/100` : "not measured"}</TooltipContent>
                </Tooltip>
              )),
            ];
          })}
        </div>
      </div>
    </div>
  );
}
