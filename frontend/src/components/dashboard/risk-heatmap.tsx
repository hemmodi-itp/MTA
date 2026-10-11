"use client";

import Link from "next/link";
import { m } from "framer-motion";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { animatesAt, ease, STAGGER_STEP } from "@/lib/motion";
import { band, HEAT_DIMENSIONS, heatRow, type ProjectHealth } from "@/lib/insights";
import { BAND_TONE } from "@/lib/status";

function cellColor(v: number | null) {
  if (v == null) return "color-mix(in srgb, var(--muted) 70%, transparent)";
  // band colour, stronger the further the score is from the 50 midpoint; translucent so the card shows through
  const strength = 22 + Math.round((v >= 50 ? (v - 50) / 50 : (50 - v) / 50) * 50);
  return `color-mix(in srgb, var(--${BAND_TONE[band(v)]}) ${strength}%, transparent)`;
}

/** Projects × quality dimensions; colour = score band. Hover a cell for details, click a project for its run. */
export function RiskHeatmap({ items }: { items: ProjectHealth[] }) {
  const rows = items.slice(0, 8);
  return (
    // scrolls inside the card on narrow screens; the project column stays put
    <div className="-mx-1 overflow-x-auto px-1 pb-1">
      <div className="grid w-full gap-1.5" role="table" aria-label="Risk heatmap"
        style={{ gridTemplateColumns: `minmax(110px,1.2fr) repeat(${HEAT_DIMENSIONS.length}, minmax(56px,1fr))`, minWidth: 110 + HEAT_DIMENSIONS.length * 62 }}>
        <div role="row" className="contents">
          <span role="columnheader" className="sticky left-0 z-10 bg-card/95" />
          {HEAT_DIMENSIONS.map((d) => (
            <span key={d.key} role="columnheader" className="flex items-end justify-center px-1 pb-1 text-center text-2xs leading-tight font-semibold text-balance text-muted-foreground">
              {d.label}
            </span>
          ))}
        </div>
        {rows.map((h, ri) => {
          const row = heatRow(h);
          return (
            <div key={h.projectId} role="row" className="contents">
              <Link role="rowheader" href={`/runs/${h.run.id}`} title={h.name}
                className="sticky left-0 z-10 flex items-center truncate rounded-sm bg-card/95 pr-2 text-xs font-medium transition-colors duration-(--dur-micro) hover:text-info-fg">
                {h.name}
              </Link>
              {HEAT_DIMENSIONS.map((d, ci) => {
                const i = ri * HEAT_DIMENSIONS.length + ci;
                const v = row[d.key];
                return (
                  <Tooltip key={d.key}>
                    <TooltipTrigger asChild>
                      <m.div
                        role="cell"
                        initial={animatesAt(i) ? { opacity: 0, scale: 0.85 } : false}
                        animate={{ opacity: 1, scale: 1 }}
                        transition={{ delay: STAGGER_STEP * Math.min(i, 20), duration: 0.24, ease: ease.enter }}
                        className="flex h-9 items-center justify-center rounded-lg text-2xs font-semibold tabular-nums ring-1 ring-white/5 ring-inset"
                        style={{ background: cellColor(v) }}
                      >
                        {v != null ? Math.round(v) : <span aria-label="not measured">–</span>}
                      </m.div>
                    </TooltipTrigger>
                    <TooltipContent>{h.name} · {d.label}: {v != null ? `${Math.round(v)}/100` : "not measured"}</TooltipContent>
                  </Tooltip>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}
