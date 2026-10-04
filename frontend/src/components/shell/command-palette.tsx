"use client";

import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight, FolderGit2, Laptop, Moon, PanelLeft, PlayCircle, Plus, RotateCw, Sparkles, Sun, Wand2,
} from "lucide-react";
import { toast } from "sonner";
import {
  Command, CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandSeparator, CommandShortcut,
} from "@/components/ui/command";
import { StatusPill } from "@/components/shared/status-pill";
import { parseQuery, type Intent } from "@/lib/nl-query";
import { useProjects, useRerunProject, useRuns } from "@/lib/query/hooks";
import { useUIStore } from "@/lib/stores/ui-store";
import { NAV, SETTINGS_NAV } from "./nav";

/** ⌘K: navigate, search projects/runs, run actions, and ask in plain language. ⌘J opens the Copilot. */
export function CommandPalette() {
  const router = useRouter();
  const { setTheme } = useTheme();
  const { commandPaletteOpen: open, setCommandPaletteOpen: setOpen, askCopilot, setCopilotOpen, toggleSidebar } = useUIStore();
  const projects = useProjects();
  const runs = useRuns();
  const rerun = useRerunProject();
  const [query, setQuery] = useState("");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === "k") { e.preventDefault(); setOpen(!useUIStore.getState().commandPaletteOpen); }
      if (mod && e.key.toLowerCase() === "j") { e.preventDefault(); setCopilotOpen(!useUIStore.getState().copilotOpen); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setOpen, setCopilotOpen]);

  const intents = useMemo(() => parseQuery(query, projects.data ?? [], runs.data ?? []), [query, projects.data, runs.data]);

  const close = () => { setOpen(false); setQuery(""); };
  const go = (href: string) => { close(); router.push(href); };
  const runIntent = (i: Intent) => {
    if (i.kind === "rerun") {
      close();
      rerun.mutate(i.projectId, {
        onSuccess: (r) => { toast.success(`Re-running ${i.projectName}`); router.push(`/runs/${r.runId}`); },
        onError: (e) => toast.error(e instanceof Error ? e.message : "Could not start the run"),
      });
      return;
    }
    go(i.href);
  };

  return (
    <CommandDialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) setQuery(""); }}
      title="Command palette" description="Search, navigate, run actions or ask in plain language"
      className="max-w-2xl! rounded-2xl! border border-border bg-popover/95 shadow-2xl backdrop-blur-2xl">
      <Command className="bg-transparent">
      <CommandInput value={query} onValueChange={setQuery} placeholder="Search or ask… e.g. “failed runs from yesterday”, “re-run BRD_Agent”" />
      <CommandList className="max-h-[440px]">
        <CommandEmpty>Nothing matches. Press Enter to ask the Copilot.</CommandEmpty>

        {query.trim().length > 2 && (
          <CommandGroup heading="Ask MTA">
            {intents.map((i) => (
              <CommandItem key={i.label} value={`intent ${i.label} ${query}`} onSelect={() => runIntent(i)} className="gap-3 py-2.5">
                <span className="flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-primary/20 to-violet/20 text-primary">
                  {i.kind === "rerun" ? <RotateCw className="size-4" /> : i.kind === "new" ? <Plus className="size-4" /> : <Wand2 className="size-4" />}
                </span>
                <span className="flex-1">
                  <span className="block font-medium">{i.label}</span>
                  <span className="block text-xs text-muted-foreground">{i.description}</span>
                </span>
                <ArrowRight className="size-4 text-muted-foreground" />
              </CommandItem>
            ))}
            <CommandItem value={`ask copilot ${query}`} onSelect={() => { const q = query; close(); askCopilot(q); }} className="gap-3 py-2.5">
              <span className="flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-violet text-white">
                <Sparkles className="size-4" />
              </span>
              <span className="flex-1">
                <span className="block font-medium">Ask Copilot: “{query.trim()}”</span>
                <span className="block text-xs text-muted-foreground">Answered from your evaluation data</span>
              </span>
              <CommandShortcut>↵</CommandShortcut>
            </CommandItem>
          </CommandGroup>
        )}

        <CommandGroup heading="Navigate">
          {[...NAV, SETTINGS_NAV].map((n) => (
            <CommandItem key={n.href} value={`go ${n.label} ${n.hint}`} onSelect={() => go(n.href)} className="gap-3">
              <n.icon className="size-4 text-muted-foreground" />
              <span className="flex-1">{n.label}</span>
              <span className="hidden text-xs text-muted-foreground sm:block">{n.hint}</span>
            </CommandItem>
          ))}
        </CommandGroup>

        {(projects.data?.length ?? 0) > 0 && (
          <>
            <CommandSeparator />
            <CommandGroup heading="Projects">
              {projects.data!.slice(0, 8).map((p) => (
                <CommandItem key={p.id} value={`project ${p.name}`} onSelect={() => go(`/projects/${p.id}`)} className="gap-3">
                  <FolderGit2 className="size-4 text-muted-foreground" />
                  <span className="flex-1 truncate">{p.name}</span>
                  {p.lastQualityScore != null && <span className="font-mono text-xs tabular-nums text-muted-foreground">{p.lastQualityScore}</span>}
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        )}

        {(runs.data?.length ?? 0) > 0 && (
          <>
            <CommandSeparator />
            <CommandGroup heading="Recent runs">
              {runs.data!.slice(0, 6).map((r) => (
                <CommandItem key={r.id} value={`run ${r.projectName} ${r.status} ${r.id}`} onSelect={() => go(`/runs/${r.id}`)} className="gap-3">
                  <PlayCircle className="size-4 text-muted-foreground" />
                  <span className="flex-1 truncate">{r.projectName}</span>
                  <StatusPill status={r.status} />
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        )}

        <CommandSeparator />
        <CommandGroup heading="Actions">
          <CommandItem value="new evaluation create workflow" onSelect={() => go("/projects/new")} className="gap-3">
            <Plus className="size-4 text-muted-foreground" /> <span className="flex-1">New evaluation</span>
          </CommandItem>
          <CommandItem value="open copilot assistant ai" onSelect={() => { close(); setCopilotOpen(true); }} className="gap-3">
            <Sparkles className="size-4 text-muted-foreground" /> <span className="flex-1">Open Copilot</span><CommandShortcut>⌘J</CommandShortcut>
          </CommandItem>
          <CommandItem value="toggle collapse sidebar" onSelect={() => { close(); toggleSidebar(); }} className="gap-3">
            <PanelLeft className="size-4 text-muted-foreground" /> <span className="flex-1">Toggle sidebar</span>
          </CommandItem>
          {([["light", Sun], ["dark", Moon], ["system", Laptop]] as const).map(([t, I]) => (
            <CommandItem key={t} value={`theme ${t} mode appearance`} onSelect={() => { close(); setTheme(t); }} className="gap-3">
              <I className="size-4 text-muted-foreground" /> <span className="flex-1 capitalize">{t} theme</span>
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
      </Command>
    </CommandDialog>
  );
}
