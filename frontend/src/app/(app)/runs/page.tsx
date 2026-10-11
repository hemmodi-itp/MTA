"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { AnimatePresence, m } from "framer-motion";
import { ArrowUpRight, Info, PlayCircle, Plus, Search, SearchX, ShieldAlert, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ErrorState } from "@/components/shared/error-state";
import { EmptyState } from "@/components/shared/empty-state";
import { PageHeader } from "@/components/shared/page-header";
import { SegmentedControl } from "@/components/shared/segmented-control";
import { StatusPill } from "@/components/shared/status-pill";
import { ScoreBar } from "@/components/shared/score";
import { TableSkeleton } from "@/components/shared/skeletons";
import { MotionCard } from "@/components/motion/motion-card";
import { IndeterminateBar } from "@/components/motion/progress-bar";
import { itemMotion } from "@/components/motion/stagger";
import { cn } from "@/lib/utils";
import { stagger, transition } from "@/lib/motion";
import { isActive, scoreOf, shortName } from "@/lib/insights";
import { sinceDate } from "@/lib/nl-query";
import { timeAgo } from "@/components/shell/notifications";
import { useRuns } from "@/lib/query/hooks";
import type { Run } from "@/lib/types";

const STATUS_TABS = [
  { value: "all", label: "All" },
  { value: "running", label: "Running" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
  { value: "cancelled", label: "Cancelled" },
];
const SINCE_LABEL: Record<string, string> = { today: "Today", yesterday: "Since yesterday", "7d": "Last 7 days", "30d": "Last 30 days" };

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

const stage = (r: Run) => (r.currentStage ? r.currentStage.replace(/_/g, " ") : r.status === "queued" ? "waiting to start" : "starting");
const blocking = (r: Run) => (r.compliance?.gates ?? []).filter((g) => g.level === "block").length;

/** Compliance cell: the score bar, or a live bar with the current step while the run is going. */
function Compliance({ run, animate }: { run: Run; animate: boolean }) {
  if (isActive(run)) {
    return (
      <div className="min-w-0 space-y-1.5">
        <IndeterminateBar label={`Evaluation in progress: ${stage(run)}`} />
        <p className="truncate text-2xs text-muted-foreground first-letter:uppercase">{stage(run)}</p>
      </div>
    );
  }
  const s = scoreOf(run);
  if (s == null) {
    return <span className="text-sm text-muted-foreground" title={run.status === "completed" ? "This run finished without a score" : undefined}>
      {run.status === "completed" ? "Not scored" : "—"}
    </span>;
  }
  const blocks = blocking(run);
  return (
    <div className="flex items-center gap-2">
      <ScoreBar score={s} className="flex-1" animateOnMount={animate} />
      {blocks > 0 && (
        <span className="tone-critical tone-text" title={`${blocks} blocking gate${blocks > 1 ? "s" : ""}`}>
          <ShieldAlert aria-hidden className="size-3.5" />
          <span className="sr-only">{blocks} blocking gate{blocks > 1 ? "s" : ""}</span>
        </span>
      )}
    </div>
  );
}

function Tests({ run, className }: { run: Run; className?: string }) {
  return (
    <span className={cn("tabular-nums", className)}>
      <span className="text-success-fg" title="passed">{run.stats.passed}</span>
      <span className="text-muted-foreground"> / </span>
      <span className="text-critical-fg" title="failed">{run.stats.failed}</span>
      <span className="text-muted-foreground"> / </span>
      <span className="text-muted-foreground" title="inconclusive or not run">{run.stats.skipped}</span>
    </span>
  );
}

const noop = () => () => {};

function Runs() {
  const { data, isLoading: fetching, isError, refetch } = useRuns();
  // This list hydrates after the shared runs query may already have data; until hydrated, render what the server
  // rendered (the loading state) so markup matches.
  const hydrated = useSyncExternalStore(noop, () => true, () => false);
  const isLoading = fetching || !hydrated;
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const filters = useMemo(() => Object.fromEntries(["status", "since", "q", "minScore", "maxScore", "gate"].map((k) => [k, params.get(k)])), [params]);
  const rows = useMemo(() => (data ?? []).filter((r) => matches(r, filters)), [data, filters]);

  const set = useCallback((k: string, v: string | null) => {
    const next = new URLSearchParams(params.toString());
    if (v) next.set(k, v); else next.delete(k);
    router.replace(`${pathname}${next.size ? `?${next}` : ""}`, { scroll: false });
  }, [params, pathname, router]);

  // the search box edits the existing `q` URL filter; debounced so typing doesn't rewrite the URL per key
  const [query, setQuery] = useState(filters.q ?? "");
  const [urlQ, setUrlQ] = useState(filters.q);
  if (filters.q !== urlQ) {
    setUrlQ(filters.q);
    setQuery(filters.q ?? "");
  }
  useEffect(() => {
    const next = query.trim();
    if (next === (params.get("q") ?? "")) return;
    const t = setTimeout(() => set("q", next || null), 250);
    return () => clearTimeout(t);
  }, [query, params, set]);

  const counts = useMemo(() => {
    const all = data ?? [];
    return {
      all: all.length,
      running: all.filter(isActive).length,
      completed: all.filter((r) => r.status === "completed").length,
      failed: all.filter((r) => r.status === "failed").length,
      cancelled: all.filter((r) => r.status === "cancelled").length,
    } as Record<string, number>;
  }, [data]);

  const chips = [
    filters.since && { k: "since", label: SINCE_LABEL[filters.since] ?? `Last ${filters.since}` },
    filters.maxScore && { k: "maxScore", label: `Score < ${filters.maxScore}` },
    filters.minScore && { k: "minScore", label: `Score > ${filters.minScore}` },
    filters.gate && { k: "gate", label: "Blocked" },
  ].filter(Boolean) as { k: string; label: string }[];
  const filtered = chips.length > 0 || !!filters.q || !!filters.status;

  if (isError) return <ErrorState onRetry={refetch} />;
  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <SegmentedControl
          label="Filter by status"
          value={filters.status ?? "all"}
          onValueChange={(v) => set("status", v === "all" ? null : v)}
          items={STATUS_TABS.map((t) => ({ ...t, count: isLoading ? null : counts[t.value] }))}
        />
        <div className="flex flex-1 flex-wrap items-center gap-2">
          <div className="relative w-full sm:w-64">
            <Search aria-hidden className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search projects" aria-label="Search runs by project" className="h-9 pl-8" />
          </div>
          <AnimatePresence initial={false}>
            {chips.map((c) => (
              <m.button key={c.k} type="button" onClick={() => set(c.k, null)}
                initial={{ opacity: 0, scale: 0.92 }} animate={{ opacity: 1, scale: 1, transition: transition.micro }} exit={{ opacity: 0, scale: 0.92, transition: transition.exit }}
                aria-label={`Remove filter: ${c.label}`}
                className="tone-info tone-tint tone-border tone-text inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-xs font-medium transition-colors duration-(--dur-micro) hover:bg-primary/15">
                {c.label} <X aria-hidden className="size-3" />
              </m.button>
            ))}
          </AnimatePresence>
          <span className="ml-auto text-xs text-muted-foreground tabular-nums" aria-live="polite">
            {isLoading ? "" : `${rows.length} of ${data?.length ?? 0} runs`}
          </span>
        </div>
      </div>

      {isLoading ? (
        <TableSkeleton rows={8} label="Loading runs…" />
      ) : !rows.length ? (
        data?.length ? (
          <EmptyState icon={SearchX} title="No runs match these filters" description="Clear a filter, or ask the Copilot (⌘J) in plain language."
            actionLabel={filtered ? "Clear filters" : undefined} onAction={() => router.replace(pathname, { scroll: false })} />
        ) : (
          <EmptyState icon={PlayCircle} title="No runs yet" description="Start an evaluation and its live progress shows up here."
            actionLabel="New evaluation" actionHref="/projects/new" />
        )
      ) : (
        <MotionCard interactive={false} className="overflow-hidden">
          {/* phones: one stacked row per run */}
          <m.ul variants={stagger()} initial="hidden" animate="show" className="divide-y divide-border/70 sm:hidden">
            {rows.map((r, i) => (
              <m.li key={r.id} {...itemMotion(i)}>
                <Link href={`/runs/${r.id}`} className="block space-y-2 px-4 py-3.5 transition-colors duration-(--dur-micro) hover:bg-muted/40">
                  <div className="flex items-center justify-between gap-3">
                    <span className="min-w-0">
                      <span className="block truncate font-medium">{shortName(r.projectName)}</span>
                      <span className="block font-mono text-2xs text-muted-foreground">{r.commitRef?.slice(0, 7) ?? r.id.slice(0, 8)}{r.projectIsSample ? " · sample" : ""}</span>
                    </span>
                    <StatusPill status={r.status} />
                  </div>
                  <Compliance run={r} animate={i < 20} />
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">Tests <Tests run={r} /></span>
                    <span className="text-muted-foreground">{timeAgo(r.startedAt)}</span>
                  </div>
                </Link>
              </m.li>
            ))}
          </m.ul>

          {/* tablet and up: the table */}
          <div className="hidden overflow-x-auto sm:block">
            <table className="w-full min-w-[720px] text-sm">
              <caption className="sr-only">Evaluation runs, newest first</caption>
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th scope="col" className="px-5 py-3 type-eyebrow">Project</th>
                  <th scope="col" className="px-3 py-3 type-eyebrow">Status</th>
                  <th scope="col" className="w-[24%] px-3 py-3 type-eyebrow">BRD compliance</th>
                  <th scope="col" className="px-3 py-3 text-right type-eyebrow">
                    <Tooltip>
                      <TooltipTrigger className="inline-flex items-center gap-1 rounded-sm uppercase">
                        Runtime tests <Info aria-hidden className="size-3" />
                      </TooltipTrigger>
                      <TooltipContent>Passed / failed / inconclusive or not run</TooltipContent>
                    </Tooltip>
                  </th>
                  <th scope="col" className="px-3 py-3 text-right type-eyebrow">Verified</th>
                  <th scope="col" className="px-5 py-3 text-right type-eyebrow">Started</th>
                </tr>
              </thead>
              <m.tbody variants={stagger()} initial="hidden" animate="show">
                {rows.map((r, i) => (
                  <m.tr key={r.id} {...itemMotion(i)} onClick={() => router.push(`/runs/${r.id}`)}
                    className="group cursor-pointer border-b border-border/60 transition-colors duration-(--dur-micro) last:border-0 hover:bg-muted/40 focus-within:bg-muted/40">
                    <td className="px-5 py-3">
                      <Link href={`/runs/${r.id}`} className="inline-flex items-center gap-1.5 rounded-sm font-medium group-hover:text-info-fg" onClick={(e) => e.stopPropagation()}>
                        {shortName(r.projectName)}
                        <ArrowUpRight aria-hidden className="size-3.5 opacity-0 transition-opacity duration-(--dur-micro) group-hover:opacity-100" />
                      </Link>
                      <span className="block font-mono text-2xs text-muted-foreground">{r.commitRef?.slice(0, 7) ?? r.id.slice(0, 8)}{r.projectIsSample ? " · sample" : ""}</span>
                    </td>
                    <td className="px-3 py-3"><StatusPill status={r.status} /></td>
                    <td className="px-3 py-3"><Compliance run={r} animate={i < 20} /></td>
                    <td className="px-3 py-3 text-right"><Tests run={r} /></td>
                    <td className="px-3 py-3 text-right text-muted-foreground tabular-nums">
                      {r.compliance?.verificationDepth != null ? `${Math.round(r.compliance.verificationDepth * 100)}%` : "—"}
                    </td>
                    <td className="px-5 py-3 text-right whitespace-nowrap text-muted-foreground" title={new Date(r.startedAt).toLocaleString()}>{timeAgo(r.startedAt)}</td>
                  </m.tr>
                ))}
              </m.tbody>
            </table>
          </div>
        </MotionCard>
      )}
    </div>
  );
}

export default function RunsPage() {
  return (
    <>
      <PageHeader
        title="Runs"
        description="Every evaluation, newest first. Filter by status or project, or ask the Copilot (⌘J) in plain language."
        actions={
          <Button asChild size="lg" className="gap-1.5">
            <Link href="/projects/new"><Plus aria-hidden /> New evaluation</Link>
          </Button>
        }
      />
      <Suspense fallback={<TableSkeleton rows={8} label="Loading runs…" />}>
        <Runs />
      </Suspense>
    </>
  );
}
