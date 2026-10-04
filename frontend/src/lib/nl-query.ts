/**
 * Natural-language → intent, shared by the ⌘K palette and the Copilot. Deterministic (no LLM): every intent
 * is a real filtered page or a real action, so "Show failed runs from yesterday" can never invent results.
 *
 *   navigation   "failed runs yesterday", "running evaluations", "runs below 50", "blocked runs last week",
 *                "failed tests", "BRD_Agent runs"
 *   actions      "generate report" (latest report), "re-run <project>" / "run analysis", "new evaluation" /
 *                "create workflow"
 */
import type { Project, Run } from "@/lib/types";

export type Intent =
  | { kind: "navigate"; label: string; description: string; href: string }
  | { kind: "rerun"; label: string; description: string; projectId: string; projectName: string }
  | { kind: "new"; label: string; description: string; href: "/projects/new" };

const STATUS: [RegExp, string, string][] = [
  [/\b(fail(ed|ing|ures?)?|errors?|broken)\b/i, "failed", "failed"],
  [/\b(running|in progress|active|ongoing|live)\b/i, "running", "running"],
  [/\b(complet(ed|e)|finished|done|succeeded|passed)\b/i, "completed", "completed"],
  [/\b(queued|waiting|pending)\b/i, "queued", "queued"],
];

function since(text: string): { value: string; label: string } | null {
  const t = text.toLowerCase();
  if (/\btoday\b/.test(t)) return { value: "today", label: "today" };
  if (/\byesterday\b/.test(t)) return { value: "yesterday", label: "since yesterday" };
  if (/\b(this|last|past) week\b|\b7 ?days\b/.test(t)) return { value: "7d", label: "in the last 7 days" };
  if (/\b(this|last|past) month\b|\b30 ?days\b/.test(t)) return { value: "30d", label: "in the last 30 days" };
  const m = t.match(/\b(last|past)\s+(\d{1,3})\s*(h|hours?|d|days?)\b/);
  if (m) {
    const unit = m[3].startsWith("h") ? "h" : "d";
    return { value: `${m[2]}${unit}`, label: `in the last ${m[2]} ${unit === "h" ? "hours" : "days"}` };
  }
  return null;
}

/** Start of the window a `since` value means, or null for none. */
export function sinceDate(value: string | null, now = new Date()): Date | null {
  if (!value) return null;
  const d = new Date(now);
  if (value === "today") { d.setHours(0, 0, 0, 0); return d; }
  if (value === "yesterday") { d.setDate(d.getDate() - 1); d.setHours(0, 0, 0, 0); return d; }
  const m = value.match(/^(\d+)([hd])$/);
  if (!m) return null;
  return new Date(now.getTime() - Number(m[1]) * (m[2] === "h" ? 3_600_000 : 86_400_000));
}

function matchProject(text: string, projects: Project[]): Project | undefined {
  const t = text.toLowerCase();
  return projects
    .map((p) => ({ p, key: p.name.toLowerCase().split("/").pop() ?? p.name.toLowerCase() }))
    .filter(({ key }) => key.length >= 3 && t.includes(key))
    .sort((a, b) => b.key.length - a.key.length)[0]?.p;
}

export function parseQuery(raw: string, projects: Project[], runs: Run[]): Intent[] {
  const text = raw.trim();
  if (text.length < 3) return [];
  const t = text.toLowerCase();
  const intents: Intent[] = [];
  const project = matchProject(text, projects);

  // actions first — explicit verbs
  if (/\b(re-?run|run (the )?(analysis|evaluation|tests?) (again|on|for)|run analysis|evaluate again)\b/.test(t)) {
    const target = project ?? projects.find((p) => !p.isSample);
    if (target && !target.isSample) {
      intents.push({ kind: "rerun", label: `Re-run the evaluation of ${target.name}`, description: "Starts a new run now",
        projectId: target.id, projectName: target.name });
    }
  }
  if (/\b(new|create|start)\b.*\b(evaluation|project|workflow|run)\b|\bcreate workflow\b/.test(t)) {
    intents.push({ kind: "new", label: "Start a new evaluation", description: "Submit a repo, BRD and live URL", href: "/projects/new" });
  }
  if (/\b(generate|show|open|get)\b.*\breport\b|\breport for\b/.test(t)) {
    const run = runs.find((r) => r.status === "completed" && (!project || r.projectId === project.id));
    if (run) {
      intents.push({ kind: "navigate", label: `Open the evaluation report for ${run.projectName}`,
        description: "Final Evaluation Report of the latest completed run", href: `/runs/${run.id}` });
    }
  }

  // filtered navigation
  const status = STATUS.find(([rx]) => rx.test(t));
  const window = since(t);
  const below = t.match(/\b(below|under|less than|<)\s*(\d{1,3})\b/);
  const above = t.match(/\b(above|over|more than|>)\s*(\d{1,3})\b/);
  const blocked = /\bblock(ed|ing)?\b|\bgates?\b/.test(t);
  const wantsTests = /\btests?( cases?)?\b/.test(t) && !/\b(runs?|evaluations?)\b/.test(t);

  if (wantsTests && status) {
    const map: Record<string, string> = { failed: "failed", completed: "passed", running: "all", queued: "all" };
    intents.push({ kind: "navigate", label: `Show ${status[2] === "completed" ? "passed" : status[2]} test cases`,
      description: "Test cases across your evaluations", href: `/test-cases?status=${map[status[1]]}` });
  }
  if (status || window || below || above || blocked || (project && /\bruns?|evaluations?|history\b/.test(t))) {
    const q = new URLSearchParams();
    const parts: string[] = [];
    if (status) { q.set("status", status[1]); parts.push(status[2]); }
    if (blocked) { q.set("gate", "block"); parts.push("blocked"); }
    if (project) { q.set("q", project.name.split("/").pop() ?? project.name); }
    if (below) { q.set("maxScore", below[2]); }
    if (above) { q.set("minScore", above[2]); }
    if (window) q.set("since", window.value);
    const label = `Show ${parts.join(", ") || "all"} runs` + (project ? ` of ${project.name.split("/").pop()}` : "")
      + (below ? ` scoring below ${below[2]}` : "") + (above ? ` scoring above ${above[2]}` : "") + (window ? ` ${window.label}` : "");
    intents.push({ kind: "navigate", label, description: "Filtered run history", href: `/runs?${q.toString()}` });
  }
  if (project && !intents.some((i) => i.kind === "navigate" && i.href.startsWith("/projects/"))) {
    intents.push({ kind: "navigate", label: `Open ${project.name}`, description: "Project overview", href: `/projects/${project.id}` });
  }
  return intents.slice(0, 4);
}
