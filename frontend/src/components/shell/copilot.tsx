"use client";

import { usePathname, useRouter } from "next/navigation";
import { AnimatePresence, m } from "framer-motion";
import { ArrowUp, Eraser, Loader2, RotateCw, Sparkles, Wand2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { MarkdownLite } from "@/components/runs/markdown-lite";
import { cn } from "@/lib/utils";
import { slideInRight, transition } from "@/lib/motion";
import { parseQuery, type Intent } from "@/lib/nl-query";
import { useProjects, useRerunProject, useRuns } from "@/lib/query/hooks";
import { useUIStore } from "@/lib/stores/ui-store";
import { usePrefersReducedMotion } from "@/hooks/use-reduced-motion";

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
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const seq = useRef(0);
  const history = useMemo(() => msgs.filter((msg) => !msg.error).slice(-6).map((msg) => ({ role: msg.role, content: msg.content })), [msgs]);
  const reduced = usePrefersReducedMotion();

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: reduced ? "auto" : "smooth" });
  }, [msgs, busy, reduced]);

  // Keyboard: focus moves into the panel when it opens, Esc closes it, and focus returns to where it was.
  useEffect(() => {
    if (!open) return;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const frame = requestAnimationFrame(() => inputRef.current?.focus());
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !e.defaultPrevented) setCopilotOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("keydown", onKey);
      if (opener?.isConnected) opener.focus();
    };
  }, [open, setCopilotOpen]);

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
        <m.aside key="copilot" variants={slideInRight} initial="hidden" animate="show" exit="exit"
          className="fixed inset-y-2 right-2 z-(--z-panel) flex w-[calc(100vw-1rem)] flex-col overflow-hidden rounded-2xl border border-border bg-popover/95 shadow-overlay backdrop-blur-2xl sm:inset-y-3 sm:right-3 sm:w-[420px]"
          aria-label="MTA Copilot">
          {/* ambient header glow */}
          <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-40 bg-[radial-gradient(60%_100%_at_50%_0%,var(--glow),transparent)]" />
          <header className="relative flex items-center gap-3 border-b border-border px-4 py-3">
            <span className="flex size-9 items-center justify-center rounded-xl bg-gradient-to-br from-primary-solid to-violet text-white shadow-control">
              <Sparkles aria-hidden className="size-[18px]" />
            </span>
            <div className="min-w-0 flex-1">
              <h2 className="text-sm font-semibold">MTA Copilot</h2>
              <p className="truncate text-xs text-muted-foreground">Context: {ctx.label}</p>
            </div>
            {msgs.length > 0 && (
              <button type="button" onClick={() => setMsgs([])} className="rounded-lg p-1.5 text-muted-foreground transition-colors duration-(--dur-micro) hover:bg-muted hover:text-foreground" aria-label="Clear conversation">
                <Eraser aria-hidden className="size-4" />
              </button>
            )}
            <button type="button" onClick={() => setCopilotOpen(false)} className="rounded-lg p-1.5 text-muted-foreground transition-colors duration-(--dur-micro) hover:bg-muted hover:text-foreground" aria-label="Close Copilot (Esc)">
              <X aria-hidden className="size-4" />
            </button>
          </header>

          <div ref={scroller} aria-live="polite" className="relative flex-1 space-y-3 overflow-y-auto px-4 py-4">
            {msgs.length === 0 && (
              <m.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={transition.enter} className="space-y-4 pt-6">
                <div className="space-y-1 text-center">
                  <div className="mx-auto flex size-12 items-center justify-center rounded-2xl bg-gradient-to-br from-primary/20 to-violet/20 text-info-fg">
                    <Sparkles aria-hidden className="size-6" />
                  </div>
                  <p className="pt-2 text-sm font-semibold">Ask about your evaluations</p>
                  <p className="text-xs text-muted-foreground">Answers use only your MTA data, with test and criterion codes.</p>
                </div>
                <div className="space-y-2">
                  {ctx.suggestions.map((s, i) => (
                    <m.button key={s} type="button" onClick={() => ask(s)}
                      initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0, transition: { ...transition.enter, delay: 0.04 * i } }}
                      whileHover={{ x: 2, transition: transition.micro }}
                      className="flex w-full items-center gap-2 rounded-xl border border-border bg-muted/30 px-3 py-2.5 text-left text-sm transition-colors duration-(--dur-micro) hover:border-primary/40 hover:bg-muted/60">
                      <Wand2 aria-hidden className="size-3.5 shrink-0 text-info-fg" /> {s}
                    </m.button>
                  ))}
                </div>
              </m.div>
            )}
            <AnimatePresence initial={false}>
              {msgs.map((msg) => (
                <m.div key={msg.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                  transition={transition.enter} className={cn("flex", msg.role === "user" ? "justify-end" : "justify-start")}>
                  <div className={cn("max-w-[88%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
                    msg.role === "user" ? "rounded-br-md bg-primary-solid text-primary-foreground"
                      : msg.error ? "rounded-bl-md border tone-critical tone-border tone-tint tone-text"
                        : "rounded-bl-md border border-border bg-card/80")}>
                    {msg.role === "assistant" && !msg.error ? (
                      <div className="space-y-2 [&_li]:ml-4 [&_li]:list-disc [&_ol_li]:list-decimal"><MarkdownLite source={msg.content} /></div>
                    ) : msg.content}
                    {msg.intents && (
                      <div className="mt-2 space-y-1.5">
                        {msg.intents.map((i) => (
                          <button key={i.label} type="button" onClick={() => runIntent(i)}
                            className="flex w-full items-center gap-2 rounded-lg border tone-info tone-border tone-tint tone-text px-2.5 py-2 text-left text-xs font-medium transition-colors duration-(--dur-micro) hover:bg-primary/15">
                            {i.kind === "rerun" ? <RotateCw aria-hidden className="size-3.5" /> : <Wand2 aria-hidden className="size-3.5" />}
                            {i.label}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </m.div>
              ))}
            </AnimatePresence>
            {busy && (
              <m.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={transition.micro} className="flex items-center gap-2 text-xs text-muted-foreground">
                {/* typing dots: the one loop here, and it explains that an answer is on its way */}
                <span aria-hidden className="flex gap-1">
                  {[0, 1, 2].map((i) => (
                    <m.span key={i} className="size-1.5 rounded-full bg-primary"
                      animate={{ y: [0, -4, 0], opacity: [0.4, 1, 0.4] }} transition={{ duration: 0.9, repeat: Infinity, delay: i * 0.15 }} />
                  ))}
                </span>
                Reading your evaluation data…
              </m.div>
            )}
          </div>

          <form onSubmit={(e) => { e.preventDefault(); void ask(input); }} className="relative border-t border-border p-3">
            <div className="flex items-end gap-2 rounded-xl border border-border bg-background/60 p-1.5 transition-colors duration-(--dur-micro) focus-within:border-primary/50 focus-within:ring-4 focus-within:ring-glow">
              <textarea ref={inputRef} value={input} onChange={(e) => setInput(e.target.value)} rows={1} placeholder="Ask, or say “re-run BRD_Agent”…"
                aria-label="Ask the Copilot"
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void ask(input); } }}
                className="max-h-32 min-h-9 flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none placeholder:text-muted-foreground" />
              <button type="submit" disabled={!input.trim() || busy}
                className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-primary-solid to-violet text-white transition-transform duration-(--dur-fast) ease-enter active:scale-95 disabled:opacity-40" aria-label="Send">
                {busy ? <Loader2 aria-hidden className="size-4 animate-spin" /> : <ArrowUp aria-hidden className="size-4" />}
              </button>
            </div>
            <p className="mt-1.5 px-1 text-2xs text-muted-foreground">Enter to send · Shift+Enter for a new line · Esc to close · ⌘J to toggle</p>
          </form>
        </m.aside>
      )}
    </AnimatePresence>
  );
}
