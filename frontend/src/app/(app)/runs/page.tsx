"use client";

import Link from "next/link";
import { Suspense, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowUpRight, PlayCircle, ShieldAlert, X } from "lucide-react";
import { ErrorState } from "@/components/shared/error-state";
import { EmptyState } from "@/components/shared/empty-state";
import { StatusPill } from "@/components/shared/status-pill";
import { MotionCard } from "@/components/motion/motion-card";
import { cn } from "@/lib/utils";
import { listItem, stagger } from "@/lib/motion";
import { band, isActive, scoreOf, shortName } from "@/lib/insights";
import { sinceDate } from "@/lib/nl-query";
import { timeAgo } from "@/components/shell/notifications";
import { useRuns } from "@/lib/query/hooks";
import type { Run } from "@/lib/types";

const STATUS_TABS = [
  { value: "", label: "All" },
  { value: "running", label: "Running" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
  { value: "cancelled", label: "Cancelled" },
];
const SINCE_LABEL: Record<string, string> = { today: "Today", yesterday: "Since yesterday", "7d": "Last 7 days", "30d": "Last 30 days" };
const BAND_BAR = { good: "bg-success", warn: "bg-warning", bad: "bg-critical", none: "bg-muted-foreground/40" } as const;

function matches(r: Run, f: Record<string, string | null>) {
  if (f.status === "running" ? !isActive(r) : f.status && r.status !== f.status) return false;
  const from = sinceDate(f.since);
  if (from && new Date(r.startedAt) < from) return false;
  if (f.q && !r.projectName.toLowerCase().includes(f.q.toLowerCase())) return false;
  const s = scoreOf(r);
  if (f.maxScore && (s == null || s >= Number(f.maxScore))) return false;
  if (f.minScore && (s == null || s <= Number(f.minScore))) return false;
  if (f.gate === "block" && !(r.compliance?.gates ?? []).some((g) => g.level === "block")) return false;
  return true;
}

function Runs() {
  const { data, isLoading, isError, refetch } = useRuns();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const filters = useMemo(() => Object.fromEntries(["status", "since", "q", "minScore", "maxScore", "gate"].map((k) => [k, params.get(k)])), [params]);
  const rows = useMemo(() => (data ?? []).filter((r) => matches(r, filters)), [data, filters]);

  const set = (k: string, v: string | null) => {
    const next = new URLSearchParams(params.toString());
    if (v) next.set(k, v); else next.delete(k);
    router.replace(`${pathname}${next.size ? `?${next}` : ""}`, { scroll: false });
  };
  const chips = [
    filters.since && { k: "since", label: SINCE_LABEL[filters.since] ?? `Last ${filters.since}` },
    filters.q && { k: "q", label: `Project: ${filters.q}` },
    filters.maxScore && { k: "maxScore", label: `Score < ${filters.maxScore}` },
    filters.minScore && { k: "minScore", label: `Score > ${filters.minScore}` },
    filters.gate && { k: "gate", label: "Blocked" },
  ].filter(Boolean) as { k: string; label: string }[];

  if (isError) return <ErrorState onRetry={refetch} />;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex rounded-xl border border-border bg-muted/40 p-1">
          {STATUS_TABS.map((t) => {
            const active = (filters.status ?? "") === t.value;
            return (
              <button key={t.value} type="button" onClick={() => set("status", t.value || null)}
                className={cn("relative rounded-lg px-3 py-1.5 text-sm font-medium transition-colors", active ? "text-foreground" : "text-muted-foreground hover:text-foreground")}>
                {active && <motion.span layoutId="runs-tab" className="absolute inset-0 rounded-lg bg-background shadow-sm ring-1 ring-border" transition={{ type: "spring", stiffness: 420, damping: 34 }} />}
                <span className="relative">{t.label}</span>
              </button>
            );
          })}
        </div>
        <AnimatePresence>
          {chips.map((c) => (
            <motion.button key={c.k} type="button" onClick={() => set(c.k, null)} layout
              initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.9 }}
              className="inline-flex h-8 items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-3 text-xs font-medium text-primary">
              {c.label} <X className="size-3" />
            </motion.button>
          ))}
        </AnimatePresence>
        <span className="ml-auto text-xs text-muted-foreground">{isLoading ? "Loading…" : `${rows.length} of ${data?.length ?? 0} runs`}</span>
      </div>

      {isLoading ? (
        <div className="space-y-2">{Array.from({ length: 6 }).map((_, i) => <div key={i} className="shimmer h-14 rounded-xl" />)}</div>
      ) : !rows.length ? (
        <EmptyState icon={PlayCircle} title={data?.length ? "No runs match these filters" : "No runs yet"}
          description={data?.length ? "Clear a filter, or ask the Copilot (⌘J) in plain language." : "Start a project evaluation to see runs here."} />
      ) : (
        <MotionCard interactive={false} className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead>
                <tr className="border-b border-border text-left text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  <th className="px-5 py-3 font-semibold">Project</th>
                  <th className="px-3 py-3 font-semibold">Status</th>
                  <th className="w-[22%] px-3 py-3 font-semibold">BRD compliance</th>
                  <th className="px-3 py-3 text-right font-semibold">Runtime tests</th>
                  <th className="px-3 py-3 text-right font-semibold">Verified</th>
                  <th className="px-5 py-3 text-right font-semibold">Started</th>
                </tr>
              </thead>
              <motion.tbody variants={stagger(0.03)} initial="hidden" animate="show">
                {rows.map((r) => {
                  const s = scoreOf(r);
                  const blocks = (r.compliance?.gates ?? []).filter((g) => g.level === "block").length;
                  return (
                    <motion.tr key={r.id} variants={listItem} onClick={() => router.push(`/runs/${r.id}`)}
                      className="group cursor-pointer border-b border-border/60 transition-colors last:border-0 hover:bg-muted/40">
                      <td className="px-5 py-3">
                        <Link href={`/runs/${r.id}`} className="flex items-center gap-2 font-medium group-hover:text-primary" onClick={(e) => e.stopPropagation()}>
                          {shortName(r.projectName)}
                          <ArrowUpRight className="size-3.5 opacity-0 transition-opacity group-hover:opacity-100" />
                        </Link>
                        <span className="block font-mono text-[11px] text-muted-foreground">{r.commitRef?.slice(0, 7) ?? r.id.slice(0, 8)}{r.projectIsSample ? " · sample" : ""}</span>
                      </td>
                      <td className="px-3 py-3"><StatusPill status={r.status} /></td>
                      <td className="px-3 py-3">
                        {s != null ? (
                          <div className="flex items-center gap-2">
                            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                              <motion.div className={cn("h-full rounded-full", BAND_BAR[band(s)])} initial={{ width: 0 }} animate={{ width: `${s}%` }}
                                transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }} />
                            </div>
                            <span className="w-8 text-right font-semibold tabular-nums">{Math.round(s)}</span>
                            {blocks > 0 && <ShieldAlert className="size-3.5 text-critical" aria-label={`${blocks} blocking gate(s)`} />}
                          </div>
                        ) : (
                          <span className="text-muted-foreground" title={r.status === "completed" ? "This run finished without a score" : undefined}>
                            {r.status === "completed" ? "Not scored" : "—"}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-3 text-right tabular-nums text-muted-foreground">
                        <span className="text-success">{r.stats.passed}</span> / <span className="text-critical">{r.stats.failed}</span> / {r.stats.skipped}
                      </td>
                      <td className="px-3 py-3 text-right tabular-nums text-muted-foreground">
                        {r.compliance?.verificationDepth != null ? `${Math.round(r.compliance.verificationDepth * 100)}%` : "—"}
                      </td>
                      <td className="px-5 py-3 text-right text-muted-foreground">{timeAgo(r.startedAt)}</td>
                    </motion.tr>
                  );
                })}
              </motion.tbody>
            </table>
          </div>
        </MotionCard>
      )}
    </div>
  );
}

export default function RunsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Runs</h1>
        <p className="text-sm text-muted-foreground">Every evaluation across every project. Try ⌘K → “failed runs from yesterday”.</p>
      </div>
      <Suspense fallback={<div className="shimmer h-72 rounded-2xl" />}>
        <Runs />
      </Suspense>
    </div>
  );
}
