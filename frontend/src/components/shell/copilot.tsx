"use client";

import { usePathname, useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowUp, Eraser, Loader2, RotateCw, Sparkles, Wand2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { MarkdownLite } from "@/components/runs/markdown-lite";
import { cn } from "@/lib/utils";
import { slideInRight, spring } from "@/lib/motion";
import { parseQuery, type Intent } from "@/lib/nl-query";
import { useProjects, useRerunProject, useRuns } from "@/lib/query/hooks";
import { useUIStore } from "@/lib/stores/ui-store";

interface Msg { id: number; role: "user" | "assistant"; content: string; intents?: Intent[]; error?: boolean }

function useContext() {
  const pathname = usePathname();
  const runs = useRuns();
  const projects = useProjects();
  const runId = pathname.match(/^\/runs\/([^/]+)/)?.[1];
  const projectId = pathname.match(/^\/projects\/(?!new)([^/]+)/)?.[1];
  const run = runs.data?.find((r) => r.id === runId);
  const project = projects.data?.find((p) => p.id === projectId);
  if (runId) {
    const name = run?.projectName.split("/").pop() ?? "this run";
    return { runId, label: `Run · ${name}`, suggestions: [
      `Why did ${name} get this score?`, "Which tests failed, and are they app defects or MTA limitations?",
      "What should be fixed first?", "Summarise the code-vs-runtime discrepancies",
    ] };
  }
  if (projectId) {
    const name = project?.name.split("/").pop() ?? "this project";
    return { projectId, label: `Project · ${name}`, suggestions: [
      `How has ${name}'s compliance changed over its runs?`, "What are the biggest risks right now?", "Is it ready to ship?",
    ] };
  }
  return { label: "Portfolio", suggestions: [
    "Which project is most at risk, and why?", "Summarise today's evaluations", "Show failed runs from yesterday",
    "Which evaluations are blocked by a login wall?",
  ] };
}

/** MTA Copilot — floating, context-aware assistant (⌘J). Answers come from your evaluation data via /api/copilot. */
export function Copilot() {
  const router = useRouter();
  const { copilotOpen: open, setCopilotOpen, copilotPrompt, clearCopilotPrompt } = useUIStore();
  const ctx = useContext();
  const projects = useProjects();
  const runs = useRuns();
  const rerun = useRerunProject();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const seq = useRef(0);
  const history = useMemo(() => msgs.filter((m) => !m.error).slice(-6).map((m) => ({ role: m.role, content: m.content })), [msgs]);

  useEffect(() => { scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" }); }, [msgs, busy]);

  const ask = async (q: string) => {
    const question = q.trim();
    if (!question || busy) return;
    setInput("");
    setMsgs((m) => [...m, { id: ++seq.current, role: "user", content: question }]);
    // conversational actions: offer them as one-click confirmations instead of acting silently
    const intents = parseQuery(question, projects.data ?? [], runs.data ?? []).filter((i) => i.kind !== "navigate" || /report|runs\?/.test(i.href));
    const actionOnly = intents.length > 0 && /^(re-?run|run analysis|generate|create|start|new|show|open)\b/i.test(question);
    if (actionOnly) {
      setMsgs((m) => [...m, { id: ++seq.current, role: "assistant", content: "Here's what I can do for that:", intents }]);
      return;
    }
    setBusy(true);
    try {
      const res = await fetch("/api/copilot", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, runId: ctx.runId, projectId: ctx.projectId, history }),
      });
      const out = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(out.error ?? "The Copilot is unavailable right now.");
      setMsgs((m) => [...m, { id: ++seq.current, role: "assistant", content: out.answer, intents: intents.length ? intents : undefined }]);
    } catch (e) {
      setMsgs((m) => [...m, { id: ++seq.current, role: "assistant", content: e instanceof Error ? e.message : "Something went wrong.", error: true }]);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (open && copilotPrompt) { const q = copilotPrompt; clearCopilotPrompt(); void ask(q); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, copilotPrompt]);

  const runIntent = (i: Intent) => {
    if (i.kind === "rerun") {
      rerun.mutate(i.projectId, {
        onSuccess: (r) => { toast.success(`Re-running ${i.projectName}`); router.push(`/runs/${r.runId}`); },
        onError: (e) => toast.error(e instanceof Error ? e.message : "Could not start the run"),
      });
      return;
    }
    router.push(i.href);
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.aside key="copilot" variants={slideInRight} initial="hidden" animate="show" exit="exit"
          className="fixed inset-y-2 right-2 z-50 flex border border-border bg-popover/95 backdrop-blur-2xl w-[calc(100vw-1rem)] flex-col overflow-hidden rounded-2xl shadow-2xl shadow-primary/10 sm:inset-y-3 sm:right-3 sm:w-[420px]"
          aria-label="MTA Copilot">
          {/* ambient header glow */}
          <div className="pointer-events-none absolute inset-x-0 top-0 h-40 bg-[radial-gradient(60%_100%_at_50%_0%,var(--glow),transparent)]" />
          <header className="relative flex items-center gap-3 border-b border-border px-4 py-3">
            <span className="flex size-9 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-violet text-white shadow-lg shadow-primary/30">
              <Sparkles className="size-[18px]" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold">MTA Copilot</p>
              <p className="truncate text-xs text-muted-foreground">Context: {ctx.label}</p>
            </div>
            {msgs.length > 0 && (
              <button type="button" onClick={() => setMsgs([])} className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted" aria-label="Clear conversation">
                <Eraser className="size-4" />
              </button>
            )}
            <button type="button" onClick={() => setCopilotOpen(false)} className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted" aria-label="Close Copilot">
              <X className="size-4" />
            </button>
          </header>

          <div ref={scroller} className="relative flex-1 space-y-3 overflow-y-auto px-4 py-4">
            {msgs.length === 0 && (
              <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-4 pt-6">
                <div className="space-y-1 text-center">
                  <motion.div animate={{ rotate: [0, 8, -8, 0] }} transition={{ duration: 4, repeat: Infinity }}
                    className="mx-auto flex size-12 items-center justify-center rounded-2xl bg-gradient-to-br from-primary/20 to-violet/20 text-primary">
                    <Sparkles className="size-6" />
                  </motion.div>
                  <p className="pt-2 text-sm font-semibold">Ask about your evaluations</p>
                  <p className="text-xs text-muted-foreground">Answers use only your MTA data, with test and criterion codes.</p>
                </div>
                <div className="space-y-2">
                  {ctx.suggestions.map((s, i) => (
                    <motion.button key={s} type="button" onClick={() => ask(s)}
                      initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0, transition: { delay: 0.05 * i } }}
                      whileHover={{ x: 3 }} transition={spring.snappy}
                      className="flex w-full items-center gap-2 rounded-xl border border-border bg-muted/30 px-3 py-2.5 text-left text-sm hover:border-primary/40 hover:bg-muted/60">
                      <Wand2 className="size-3.5 shrink-0 text-primary" /> {s}
                    </motion.button>
                  ))}
                </div>
              </motion.div>
            )}
            <AnimatePresence initial={false}>
              {msgs.map((m) => (
                <motion.div key={m.id} layout initial={{ opacity: 0, y: 8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
                  transition={spring.snappy} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
                  <div className={cn("max-w-[88%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
                    m.role === "user" ? "rounded-br-md bg-primary text-primary-foreground"
                      : m.error ? "rounded-bl-md border border-critical/30 bg-critical/10 text-critical"
                        : "rounded-bl-md border border-border bg-card/80")}>
                    {m.role === "assistant" && !m.error ? (
                      <div className="space-y-2 [&_li]:ml-4 [&_li]:list-disc [&_ol_li]:list-decimal"><MarkdownLite source={m.content} /></div>
                    ) : m.content}
                    {m.intents && (
                      <div className="mt-2 space-y-1.5">
                        {m.intents.map((i) => (
                          <button key={i.label} type="button" onClick={() => runIntent(i)}
                            className="flex w-full items-center gap-2 rounded-lg border border-primary/30 bg-primary/10 px-2.5 py-2 text-left text-xs font-medium text-primary hover:bg-primary/15">
                            {i.kind === "rerun" ? <RotateCw className="size-3.5" /> : <Wand2 className="size-3.5" />}
                            {i.label}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
            {busy && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center gap-2 text-xs text-muted-foreground">
                <span className="flex gap-1">
                  {[0, 1, 2].map((i) => (
                    <motion.span key={i} className="size-1.5 rounded-full bg-primary"
                      animate={{ y: [0, -4, 0], opacity: [0.4, 1, 0.4] }} transition={{ duration: 0.9, repeat: Infinity, delay: i * 0.15 }} />
                  ))}
                </span>
                Reading your evaluation data…
              </motion.div>
            )}
          </div>

          <form onSubmit={(e) => { e.preventDefault(); void ask(input); }} className="relative border-t border-border p-3">
            <div className="flex items-end gap-2 rounded-xl border border-border bg-background/60 p-1.5 focus-within:border-primary/50 focus-within:shadow-[0_0_0_4px_var(--glow)]">
              <textarea value={input} onChange={(e) => setInput(e.target.value)} rows={1} placeholder="Ask, or say “re-run BRD_Agent”…"
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void ask(input); } }}
                className="max-h-32 min-h-9 flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none placeholder:text-muted-foreground" />
              <motion.button type="submit" disabled={!input.trim() || busy} whileTap={{ scale: 0.9 }}
                className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-violet text-white disabled:opacity-40" aria-label="Send">
                {busy ? <Loader2 className="size-4 animate-spin" /> : <ArrowUp className="size-4" />}
              </motion.button>
            </div>
            <p className="mt-1.5 px-1 text-[11px] text-muted-foreground">Enter to send · Shift+Enter for a new line · ⌘J to toggle</p>
          </form>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
