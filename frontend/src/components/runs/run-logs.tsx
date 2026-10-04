"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Download, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { useRunLogs } from "@/lib/query/hooks";
import type { RunEvent, RunStatus, RunStep } from "@/lib/types";

const LEVELS: RunEvent["level"][] = ["info", "success", "warning", "error"];
const LEVEL_STYLE: Record<RunEvent["level"], string> = {
  info: "text-muted-foreground",
  success: "text-success",
  warning: "text-warning-foreground dark:text-warning",
  error: "text-critical",
};

function clock(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour12: false });
}

function offset(from: string, iso: string) {
  const s = Math.max(0, Math.round((new Date(iso).getTime() - new Date(from).getTime()) / 1000));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return `+${h ? `${h}:` : ""}${String(m).padStart(h ? 2 : 1, "0")}:${String(sec).padStart(2, "0")}`;
}

/** Full run log: every line the pipeline wrote, with stage / level filters, search, follow mode and download. */
export function RunLogs({ runId, status, steps }: { runId: string; status: RunStatus; steps: RunStep[] }) {
  const logs = useRunLogs(runId, status);
  const [stage, setStage] = useState<string>("all");
  const [levels, setLevels] = useState<Set<RunEvent["level"]>>(new Set(LEVELS));
  const [query, setQuery] = useState("");
  const [follow, setFollow] = useState(true);
  const box = useRef<HTMLDivElement>(null);

  const events = useMemo(() => logs.data?.events ?? [], [logs.data]);
  const labels = useMemo(() => Object.fromEntries(steps.map((s) => [s.key, s.label])), [steps]);
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return events.filter((e) => (stage === "all" || e.stage === stage) && levels.has(e.level)
      && (!q || e.message.toLowerCase().includes(q)));
  }, [events, stage, levels, query]);
  const counts = useMemo(() => Object.fromEntries(LEVELS.map((l) => [l, events.filter((e) => e.level === l).length])), [events]);

  useEffect(() => {
    if (follow && box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [shown.length, follow]);

  const start = logs.data?.startedAt ?? events[0]?.createdAt ?? new Date().toISOString();
  const download = () => {
    const text = events.map((e) => `${e.createdAt}\t${offset(start, e.createdAt)}\t${e.level.toUpperCase()}\t${e.stage ?? "-"}\t${e.message}`).join("\n");
    const url = URL.createObjectURL(new Blob([text + "\n"], { type: "text/plain" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: `mta-run-${runId}-log.txt` });
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={stage}
          onChange={(e) => setStage(e.target.value)}
          className="h-8 rounded-md border border-border bg-background px-2 text-sm"
          aria-label="Filter by pipeline step"
        >
          <option value="all">All steps</option>
          {steps.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
        </select>
        {LEVELS.map((l) => (
          <button
            key={l}
            type="button"
            onClick={() => setLevels((prev) => { const n = new Set(prev); if (n.has(l)) n.delete(l); else n.add(l); return n; })}
            className={cn("h-8 rounded-full border px-3 text-xs capitalize",
              levels.has(l) ? "border-primary/40 bg-primary/10 text-foreground" : "border-border text-muted-foreground")}
          >
            {l} <span className="tabular-nums opacity-70">{counts[l] ?? 0}</span>
          </button>
        ))}
        <div className="relative min-w-40 flex-1">
          <Search className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search the log" className="h-8 pl-7 text-sm" />
        </div>
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> Follow
        </label>
        <Button variant="outline" size="sm" onClick={download} disabled={!events.length}>
          <Download className="size-4" /> Download
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        {shown.length === events.length ? `${events.length} lines` : `${shown.length} of ${events.length} lines`}
        {status === "running" || status === "queued" || status === "cloning" ? " · updating live" : ""}
      </p>
      <div
        ref={box}
        onScroll={(e) => {
          const el = e.currentTarget;
          if (el.scrollHeight - el.scrollTop - el.clientHeight > 40 && follow) setFollow(false);
        }}
        className="h-[65vh] overflow-y-auto rounded-lg border border-border bg-muted/40 p-3 font-mono text-xs leading-relaxed"
      >
        {logs.isLoading ? (
          <p className="text-muted-foreground">Loading the log…</p>
        ) : shown.length === 0 ? (
          <p className="text-muted-foreground">{events.length ? "No lines match the filters." : "No log lines yet."}</p>
        ) : (
          shown.map((e) => (
            <div key={e.id} className="flex gap-2">
              <span className="shrink-0 tabular-nums text-muted-foreground/70" title={offset(start, e.createdAt)}>{clock(e.createdAt)}</span>
              <span className="w-28 shrink-0 truncate text-muted-foreground/70" title={e.stage ? labels[e.stage] : ""}>
                {e.stage ? (labels[e.stage] ?? e.stage) : "—"}
              </span>
              <span className={cn("min-w-0 whitespace-pre-wrap break-words", LEVEL_STYLE[e.level])}>{e.message}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
