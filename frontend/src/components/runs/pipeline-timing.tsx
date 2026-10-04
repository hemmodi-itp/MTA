"use client";

import { useEffect, useState } from "react";
import type { RunProgress } from "@/lib/types";

function fmt(sec: number) {
  const s = Math.max(0, Math.round(sec));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  return h ? `${h}h ${m}m` : m ? `${m}m ${String(r).padStart(2, "0")}s` : `${r}s`;
}

/** Seconds left: finished steps 0; the running step uses its live "about N min left" or its typical duration minus
 *  elapsed; pending steps their typical duration (median of recent completed runs). */
export function remainingSeconds(p: RunProgress, now: number): number | null {
  const est = p.estimates ?? {};
  let total = 0, known = false;
  for (const s of p.steps) {
    if (s.status === "success" || s.status === "skipped" || s.status === "failed") continue;
    if (s.status === "running") {
      const live = s.detail?.match(/about (\d+) min left/);
      const elapsed = s.startedAt ? (now - new Date(s.startedAt).getTime()) / 1000 : 0;
      if (live) { total += Number(live[1]) * 60; known = true; }
      else if (est[s.key] !== undefined) { total += Math.max(est[s.key] - elapsed, 10); known = true; }
    } else if (est[s.key] !== undefined) {
      total += est[s.key];
      known = true;
    }
  }
  return known ? total : null;
}

/** Pipeline header: total elapsed, estimated time remaining (while running) or total duration (when finished). */
export function PipelineTiming({ progress, active }: { progress: RunProgress; active: boolean }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [active]);

  const first = progress.steps.map((s) => s.startedAt).filter(Boolean).sort()[0] ?? progress.startedAt;
  if (!first) return null;
  const end = active ? now : new Date(progress.finishedAt ?? progress.steps.map((s) => s.finishedAt).filter(Boolean).sort().pop() ?? now).getTime();
  const elapsed = (end - new Date(first).getTime()) / 1000;
  const left = active ? remainingSeconds(progress, now) : null;
  return (
    <span className="font-mono text-xs tabular-nums text-muted-foreground">
      {active ? `elapsed ${fmt(elapsed)}` : `took ${fmt(elapsed)}`}
      {left !== null && <> · about {fmt(left)} left · ends ~{new Date(now + left * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</>}
    </span>
  );
}
