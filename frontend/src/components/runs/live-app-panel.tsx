import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Globe, XCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/shared/empty-state";
import { cn } from "@/lib/utils";
import type {
  ActionPlan,
  ActionStep,
  AppClassification,
  EvidenceBundle,
  EvidenceCollection,
  ExecutionResult,
  ExecutionRun,
  OutputValidation,
  OutputValidationResult,
  PassFail,
  RuntimeProfile,
  TestVerdict,
} from "@/lib/types";

function Flag({ on, label }: { on: boolean; label: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs",
      on ? "border-primary/30 bg-primary/10 text-primary" : "border-border text-muted-foreground")}>
      {on ? <CheckCircle2 className="size-3" /> : <XCircle className="size-3" />}
      {label}
    </span>
  );
}

/** Application Classification Engine output: the app type, why, and how it will be tested (Component 2). */
function ClassificationCard({ c }: { c: AppClassification }) {
  const shown = c.components.length ? c.components : [c.app_type];
  const top = Object.entries(c.scores).filter(([, s]) => s > 0);
  const max = top[0]?.[1] || 1;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground">Application type</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <p className="text-2xl font-semibold">{c.app_type}</p>
          {c.components.length > 0 && <p className="text-muted-foreground">{c.components.join(" + ")}</p>}
          <p className="text-muted-foreground">
            confidence {Math.round(c.confidence * 100)}% · from {c.basis}
          </p>
        </div>
        {c.note && <p className="text-xs text-warning-foreground dark:text-warning">{c.note}</p>}
        {top.length > 0 && (
          <div className="space-y-1.5">
            {top.map(([cls, s]) => (
              <div key={cls} className="grid grid-cols-[9rem_1fr_2.5rem] items-center gap-2 text-xs">
                <span className={cn(shown.includes(cls) ? "font-medium" : "text-muted-foreground")}>{cls}</span>
                <span className="h-1.5 rounded-full bg-muted">
                  <span
                    className={cn("block h-1.5 rounded-full", shown.includes(cls) ? "bg-primary" : "bg-muted-foreground/40")}
                    style={{ width: `${Math.max(4, (s / max) * 100)}%` }}
                  />
                </span>
                <span className="text-right tabular-nums text-muted-foreground">{s.toFixed(1)}</span>
              </div>
            ))}
          </div>
        )}
        {c.evidence.length > 0 && (
          <div>
            <p className="mb-1 text-xs font-medium">Found</p>
            <ul className="space-y-0.5 text-xs text-muted-foreground">
              {c.evidence.slice(0, 8).map((e, i) => (
                <li key={i}>
                  <Badge variant="outline" className="mr-1.5 px-1 py-0 text-[10px] font-normal">{e.source}</Badge>
                  {e.signal} <span className="opacity-70">→ {e.class}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {c.testing_strategy.length > 0 && (
          <div>
            <p className="mb-1 text-xs font-medium">Testing strategy</p>
            {c.testing_strategy.map((t) => (
              <p key={t.class} className="text-xs text-muted-foreground">
                <span className="font-medium text-foreground">{t.class}:</span> {t.strategy}
              </p>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function describeStep(s: ActionStep): string {
  const t = s.target;
  const what = t?.label || t?.text || t?.name || t?.href || "";
  const which = t?.context ? ` (in “${t.context.slice(0, 40)}${t.context.length > 40 ? "…" : ""}”)` : "";
  switch (s.action) {
    case "login": return "Log in with the test account";
    case "goto": return `Open ${s.url}`;
    case "fill": return `Fill “${what}” with “${(s.value ?? "").slice(0, 80)}${(s.value ?? "").length > 80 ? "…" : ""}”`;
    case "select": return `Select “${s.value}” in “${what}”`;
    case "check": return `Check “${what}”`;
    case "upload": return `Upload a file to “${what}”`;
    case "click": return `Click “${what}”${which}`;
    case "send_message": return `Send “${(s.value ?? "").slice(0, 80)}${(s.value ?? "").length > 80 ? "…" : ""}”`;
    case "follow_up": return `After generating, send the follow-up “${(s.value ?? "").slice(0, 80)}${(s.value ?? "").length > 80 ? "…" : ""}”`;
    case "wait_for": return `Wait for the ${s.kind === "response" ? "response" : "page to settle"} (up to ${Math.round((s.timeout_ms ?? 0) / 1000)}s)`;
    case "expect_download": return `Expect a download from “${what}”`;
    case "http": return `${s.method} ${s.path}`;
    case "capture": return `Capture ${(s.what ?? []).join(", ")}`;
    case "assert": return s.kind === "judge" ? `Judge: ${s.expectation}` : `Check ${s.kind}: ${s.value ?? ""}`;
  }
}

/** Action Generation Engine output: per-test browser/HTTP actions on discovered elements (Component 3). */
function ActionPlanCard({ plan }: { plan: ActionPlan }) {
  const c = plan.counts;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground">Action plans</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p>
          <span className="font-medium">{c.ready}/{c.tests}</span> test(s) ready to run
          {c.unmappable > 0 && <> · {c.unmappable} not testable through the UI</>}
          {(c.flow_checks ?? 0) > 0 && <> · {c.flow_checks} flow check(s)</>}
          <span className="text-muted-foreground"> · {c.llm_mapped ?? 0} mapped by Gemini, grounded on {plan.inventory_size} discovered element(s)</span>
        </p>
        {plan.reason && plan.status !== "ready" && <p className="text-xs text-warning-foreground dark:text-warning">{plan.reason}</p>}
        <div className="divide-y divide-border rounded-md border border-border">
          {plan.plans.map((p) => (
            <details key={p.plan_id} className="group px-3 py-2">
              <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2">
                <span className="font-mono text-xs">{p.test_code ?? "flow"}</span>
                <span className="min-w-0 flex-1 truncate">{p.title}</span>
                {p.criterion_code && <Badge variant="outline" className="font-normal">{p.criterion_code}</Badge>}
                {!p.scored && <Badge variant="secondary" className="font-normal">not scored</Badge>}
                <Badge variant={p.status === "ready" ? "secondary" : "outline"} className="font-normal">
                  {p.status === "ready" ? `${p.steps.length} steps · ${p.source === "llm" ? "Gemini" : "rules"}` : "not testable via UI"}
                </Badge>
              </summary>
              {p.reason && <p className="mt-1 text-xs text-muted-foreground">{p.reason}</p>}
              {p.steps.length > 0 && (
                <ol className="mt-2 space-y-0.5 text-xs text-muted-foreground">
                  {p.steps.map((s) => (
                    <li key={s.n}>
                      {s.n}. {describeStep(s)}
                      {s.synthetic && <span className="opacity-70"> (test data)</span>}
                    </li>
                  ))}
                </ol>
              )}
            </details>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

const RESULT_LABEL: Record<ExecutionResult["status"], string> = {
  completed: "ran to the end",
  failed: "stopped at a failing step",
  error: "browser error",
  blocked: "blocked",
  not_run: "not run (time budget)",
};

/** Playwright Executor output: what actually happened in the browser, with captured evidence (Component 4). */
function ExecutionCard({ run, runId, plan }: { run: ExecutionRun; runId: string; plan: ActionPlan | null }) {
  const c = run.counts;
  const file = (p: string) => fileUrl(runId, p);
  const stepsOf = (planId: string) => plan?.plans.find((p) => p.plan_id === planId)?.steps ?? [];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground">Browser execution</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p>
          <span className="font-medium">{c.completed}/{c.plans}</span> plan(s) ran to the end
          {c.failed > 0 && <> · {c.failed} stopped at a failing step</>}
          {c.blocked + c.not_run + c.error > 0 && <> · {c.blocked + c.not_run + c.error} not run</>}
          {c.downloads > 0 && <> · {c.downloads} file(s) downloaded</>}
          <span className="text-muted-foreground"> · {run.duration_s}s · verdicts come from output validation</span>
        </p>
        {run.reason && <p className="text-xs text-warning-foreground dark:text-warning">{run.reason}</p>}
        <div className="divide-y divide-border rounded-md border border-border">
          {run.results.map((r) => {
            const planned = stepsOf(r.plan_id);
            return (
              <details key={r.plan_id} className="px-3 py-2">
                <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2">
                  {r.status === "completed" ? <CheckCircle2 className="size-4 text-success" /> : <XCircle className="size-4 text-critical" />}
                  <span className="font-mono text-xs">{r.test_code ?? "flow"}</span>
                  <span className="min-w-0 flex-1 truncate">{r.title}</span>
                  <Badge variant="outline" className="font-normal">
                    {RESULT_LABEL[r.status]}{r.failed_step ? ` (step ${r.failed_step})` : ""} · {(r.duration_ms / 1000).toFixed(1)}s
                  </Badge>
                </summary>
                <div className="mt-2 space-y-2 text-xs">
                  {r.error && <p className="text-critical">{r.error}</p>}
                  {r.steps.length > 0 && (
                    <ol className="space-y-0.5 text-muted-foreground">
                      {r.steps.map((s) => {
                        const p = planned.find((x) => x.n === s.n);
                        return (
                          <li key={s.n} className={cn(s.status === "failed" && "text-critical", s.status === "skipped" && "opacity-60")}>
                            {s.n}. {p ? describeStep(p) : s.action} — {s.status}
                            {s.detail ? ` · ${s.detail}` : ""}
                            {s.error ? ` · ${s.error}` : ""}
                            {s.screenshot && (
                              <> · <a className="underline" href={file(s.screenshot)} target="_blank" rel="noreferrer">failure screenshot</a></>
                            )}
                          </li>
                        );
                      })}
                    </ol>
                  )}
                  {r.captures.reply && (
                    <p className="whitespace-pre-wrap rounded bg-muted p-2"><span className="font-medium">Reply: </span>{r.captures.reply.slice(0, 600)}</p>
                  )}
                  {(r.captures.downloads ?? []).map((d) => (
                    <p key={d.file}>
                      Downloaded <a className="underline" href={file(d.file)}>{d.name}</a> · {d.kind} · {(d.size / 1024).toFixed(1)} KB
                    </p>
                  ))}
                  {(r.observations.console_errors?.length ?? 0) + (r.observations.http_errors ?? 0) > 0 && (
                    <p className="text-muted-foreground">
                      {r.observations.console_errors?.length ?? 0} console error(s) · {r.observations.http_errors ?? 0} failed API call(s)
                    </p>
                  )}
                  {r.captures.screenshot && (
                    <a href={file(r.captures.screenshot)} target="_blank" rel="noreferrer" className="block">
                      {/* eslint-disable-next-line @next/next/no-img-element -- auth-gated API image, not a static asset */}
                      <img src={file(r.captures.screenshot)} alt={`Screenshot after ${r.test_code ?? r.plan_id}`}
                        className="max-h-64 rounded border border-border object-cover object-top" loading="lazy" />
                    </a>
                  )}
                </div>
              </details>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

const fileUrl = (runId: string, p: string) => `/api/runs/${runId}/execution-files/${p.split("/").map(encodeURIComponent).join("/")}`;

function BundleRow({ b, runId }: { b: EvidenceBundle; runId: string }) {
  const ran = b.execution_status === "completed" || b.execution_status === "failed";
  const shot = b.artifacts.find((a) => a.type === "screenshot");
  return (
    <div className="space-y-1 py-2 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono">{b.test_code ?? "flow"}</span>
        <span className="min-w-0 flex-1 truncate text-sm">{b.title}</span>
        <Badge variant={b.completeness.output_captured ? "secondary" : "outline"} className="font-normal">
          {!ran ? "not executed" : b.completeness.output_captured ? `${b.completeness.expected_output} captured` : "output missing"}
        </Badge>
      </div>
      {b.completeness.missing.length > 0 && <p className="text-warning-foreground dark:text-warning">{b.completeness.missing.join("; ")}</p>}
      {!ran && b.error && <p className="text-muted-foreground">{b.error}</p>}
      {b.inputs.filter((i) => !i.synthetic).length > 0 && (
        <p className="text-muted-foreground">
          Sent: {b.inputs.filter((i) => !i.synthetic).map((i) => `${i.field}: “${(i.value ?? "").slice(0, 60)}${(i.value ?? "").length > 60 ? "…" : ""}”`).join(" · ")}
          {b.inputs.some((i) => i.synthetic) && ` (+${b.inputs.filter((i) => i.synthetic).length} test-data field(s))`}
        </p>
      )}
      {b.observed.reply && <p className="whitespace-pre-wrap rounded bg-muted p-2">Reply: {b.observed.reply.slice(0, 400)}</p>}
      {!b.observed.reply && b.observed.ui_output && (
        <p className="whitespace-pre-wrap rounded bg-muted p-2">{b.observed.page_change === "reordered" ? "Page re-ordered" : "Appeared on the page"}: {b.observed.ui_output.slice(0, 400)}</p>
      )}
      {b.observed.documents.map((d, i) => (
        <p key={i}>
          {d.file ? <a className="underline" href={fileUrl(runId, d.file)}>{d.name}</a> : d.name}
          {d.readable
            ? ` · ${d.format} · ${d.words ?? 0} words${d.pages ? ` · ${d.pages} pages` : ""}${d.tables ? ` · ${d.tables} tables` : ""}`
            : ` · unreadable (${d.error})`}
          {d.text_file && <> · <a className="underline" href={fileUrl(runId, d.text_file)} target="_blank" rel="noreferrer">text</a></>}
          {d.headings && d.headings.length > 0 && <span className="text-muted-foreground"> · {d.headings.slice(0, 6).join(" / ")}</span>}
        </p>
      ))}
      {ran && (
        <p className="text-muted-foreground">
          {b.artifacts.length} artifact(s), sha256-hashed
          {shot && <> · <a className="underline" href={fileUrl(runId, shot.path)} target="_blank" rel="noreferrer">screenshot</a></>}
        </p>
      )}
    </div>
  );
}

/** Evidence Collection Engine output: evidence bundles grouped by acceptance criterion (Component 5). */
function EvidenceCard({ evidence, runId }: { evidence: EvidenceCollection; runId: string }) {
  const c = evidence.counts;
  const scored = evidence.bundles.filter((b) => b.scored && b.criterion_code);
  const groups = Array.from(new Set(scored.map((b) => b.criterion_code as string))).sort();
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground">Evidence by acceptance criterion</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p>
          <span className="font-medium">{c.with_output}/{c.bundles}</span> test(s) with the expected output captured
          · {c.criteria_covered} criteria · {c.documents} document(s) read
          {c.not_executed > 0 && <> · {c.not_executed} not executed</>}
          <span className="text-muted-foreground"> · facts only; verdicts come from output validation</span>
        </p>
        <div className="divide-y divide-border rounded-md border border-border">
          {groups.map((code) => {
            const items = scored.filter((b) => b.criterion_code === code);
            return (
              <details key={code} className="px-3 py-2">
                <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2">
                  <Badge variant="outline" className="font-mono font-normal">{code}</Badge>
                  <span className="min-w-0 flex-1 truncate">{items[0]?.criterion_statement ?? ""}</span>
                  <span className="text-xs text-muted-foreground">
                    {items.filter((b) => b.completeness.output_captured).length}/{items.length} with output
                  </span>
                </summary>
                <div className="divide-y divide-border">
                  {items.map((b) => <BundleRow key={b.bundle_id} b={b} runId={runId} />)}
                </div>
              </details>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

const ASSESSMENT: Record<string, string> = {
  meets: "meets the expectation",
  partially_meets: "partially meets",
  does_not_meet: "does not meet",
  cannot_tell: "cannot tell",
};

function ValidationRow({ r }: { r: OutputValidationResult }) {
  const failed = r.core_failures?.length ?? 0;
  return (
    <details className="px-3 py-2">
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2">
        <span className="font-mono text-xs">{r.test_code ?? "flow"}</span>
        <span className="min-w-0 flex-1 truncate">{r.title}</span>
        {r.criterion_code && <Badge variant="outline" className="font-normal">{r.criterion_code}</Badge>}
        <Badge variant={r.status === "validated" && !failed && r.judge?.assessment === "meets" ? "secondary" : "outline"} className="font-normal">
          {r.status !== "validated" ? "not validatable" : r.judge ? `${ASSESSMENT[r.judge.assessment]} · ${r.judge.score}` : failed ? `${failed} core check(s) failed` : "checks only"}
        </Badge>
      </summary>
      <div className="mt-2 space-y-2 text-xs">
        {r.status !== "validated" && <p className="text-muted-foreground">{r.reason}</p>}
        {r.checks.length > 0 && (
          <ul className="space-y-0.5">
            {r.checks.map((c) => (
              <li key={c.id} className={cn(c.result === "fail" ? "text-critical" : "text-muted-foreground")}>
                {c.result === "pass" ? "✓" : c.result === "fail" ? "✗" : "?"} {c.name}
                {c.weight === "supporting" && <span className="opacity-70"> (supporting)</span>} — {c.detail}
              </li>
            ))}
          </ul>
        )}
        {r.judge && (
          <div className="space-y-1 rounded bg-muted p-2">
            <p><span className="font-medium">Judge:</span> {r.judge.reasoning}</p>
            {r.judge.criteria_results.map((c, i) => (
              <p key={i} className={cn(c.result === "not_met" && "text-critical")}>
                {c.result === "met" ? "✓" : c.result === "not_met" ? "✗" : "?"} {c.criterion}
                {c.quote && <span className="text-muted-foreground"> — “{c.quote}”</span>}
                {c.note && <span className="text-warning-foreground dark:text-warning"> ({c.note})</span>}
              </p>
            ))}
          </div>
        )}
        {r.judge_error && <p className="text-warning-foreground dark:text-warning">Judge unavailable: {r.judge_error}</p>}
      </div>
    </details>
  );
}

/** Output Validation Engine output: deterministic checks + grounded judge per test (Component 6). */
function ValidationCard({ validation }: { validation: OutputValidation }) {
  const c = validation.counts;
  const rows = validation.results.filter((r) => r.scored);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground">Output validation</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p>
          <span className="font-medium">{c.meets}/{c.judged}</span> judged output(s) fully meet the BRD expectation
          · {c.checks_passed} check(s) passed, {c.checks_failed} failed
          {c.not_validatable > 0 && <> · {c.not_validatable} not validatable</>}
          {c.ungrounded_quotes > 0 && <span className="text-warning-foreground dark:text-warning"> · {c.ungrounded_quotes} unverifiable judge claim(s) downgraded</span>}
        </p>
        <div className="divide-y divide-border rounded-md border border-border">
          {rows.map((r) => <ValidationRow key={r.bundle_id} r={r} />)}
        </div>
      </CardContent>
    </Card>
  );
}

const VERDICT_STYLE: Record<TestVerdict["verdict"], string> = {
  passed: "border-success/40 bg-success/10 text-success",
  failed: "border-critical/40 bg-critical/10 text-critical",
  inconclusive: "border-warning/40 bg-warning/10 text-warning-foreground dark:text-warning",
  not_executed: "border-border text-muted-foreground",
};
const CRITERION_STYLE: Record<string, string> = {
  supported: VERDICT_STYLE.passed,
  refuted: VERDICT_STYLE.failed,
  unverified: VERDICT_STYLE.not_executed,
};

function Pill({ className, children }: { className: string; children: ReactNode }) {
  return <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-xs", className)}>{children}</span>;
}

/** Pass/Fail Engine output: verdict per test and runtime verdict per acceptance criterion (Component 7). */
function PassFailCard({ pf }: { pf: PassFail }) {
  const c = pf.counts;
  const tests = pf.tests.filter((t) => t.scored);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground">Verdicts</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
          <p className="text-2xl font-semibold">{pf.pass_rate === null ? "—" : `${pf.pass_rate}%`}</p>
          <p className="text-muted-foreground">
            {c.passed} passed · {c.failed} failed · {c.inconclusive} inconclusive · {c.not_executed} not run
            {" · "}criteria: {c.criteria_supported} supported, {c.criteria_refuted} refuted, {c.criteria_unverified} unverified
          </p>
        </div>
        <p className="text-xs text-muted-foreground">
          Failed = the app produced the wrong result. Inconclusive = MTA could not drive the UI or judge the output; never held
          against the app. E5 = decided by deterministic checks, E4 = by the grounded judge.
        </p>
        <div className="divide-y divide-border rounded-md border border-border">
          {pf.criteria.map((cr) => (
            <details key={cr.criterion_code} className="px-3 py-2">
              <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2">
                <Badge variant="outline" className="font-mono font-normal">{cr.criterion_code}</Badge>
                <span className="min-w-0 flex-1 truncate">{cr.statement}</span>
                <Pill className={CRITERION_STYLE[cr.runtime_verdict]}>
                  {cr.runtime_verdict}{cr.strength ? ` · ${cr.strength}` : ""}{cr.mixed ? " · mixed results" : ""}
                </Pill>
              </summary>
              <div className="mt-2 space-y-2">
                {tests.filter((t) => t.criterion_code === cr.criterion_code).map((t) => (
                  <div key={t.bundle_id} className="space-y-0.5 text-xs">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono">{t.test_code}</span>
                      <span className="min-w-0 flex-1 truncate">{t.title}</span>
                      <Pill className={VERDICT_STYLE[t.verdict]}>
                        {t.verdict.replace("_", " ")}{t.score !== null ? ` · ${t.score}` : ""}{t.strength ? ` · ${t.strength}` : ""}
                      </Pill>
                    </div>
                    {t.reasons.map((r, i) => <p key={i} className="text-muted-foreground">{r}</p>)}
                    {t.supporting_issues.length > 0 && (
                      <p className="text-warning-foreground dark:text-warning">Also noted: {t.supporting_issues.join("; ")}</p>
                    )}
                  </div>
                ))}
              </div>
            </details>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

/** Runtime workflow output: Discovery (1), Classification (2), Actions (3), Executor (4), Evidence (5), Validation (6), Verdicts (7). */
export function LiveAppPanel({ profile, classification, actionPlan, executionRun, evidence, validation, passFail, runId, deployed }: {
  profile: RuntimeProfile | null;
  classification: AppClassification | null;
  actionPlan: ActionPlan | null;
  executionRun: ExecutionRun | null;
  evidence: EvidenceCollection | null;
  validation: OutputValidation | null;
  passFail: PassFail | null;
  runId: string;
  deployed: boolean;
}) {
  if (!profile) {
    return (
      <div className="space-y-4">
        {classification && <ClassificationCard c={classification} />}
        <EmptyState
          icon={Globe}
          title={deployed ? "Live app not inspected yet" : "No live deployment"}
          description={deployed ? "Runtime discovery runs after test generation." : "This evaluation is BRD-only, so there is no live app to inspect."}
        />
      </div>
    );
  }
  const loginFailed = profile.login?.attempted && !profile.login.succeeded;
  return (
    <div className="space-y-4">
      {classification && <ClassificationCard c={classification} />}
      {passFail && <PassFailCard pf={passFail} />}
      {validation && <ValidationCard validation={validation} />}
      {evidence && <EvidenceCard evidence={evidence} runId={runId} />}
      {executionRun && <ExecutionCard run={executionRun} runId={runId} plan={actionPlan} />}
      {actionPlan && <ActionPlanCard plan={actionPlan} />}

      {(profile.needs_credentials || loginFailed) && (
        <Card className="border-warning/40 bg-warning/5">
          <CardContent className="flex gap-3 text-sm">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning-foreground dark:text-warning" />
            <div>
              <p className="font-medium">{loginFailed ? "Login with the test account failed" : "The app is behind a login"}</p>
              <p className="text-muted-foreground">
                {loginFailed
                  ? `${profile.login?.error ?? "Still on the login page"}. Check the test account on the project and re-run.`
                  : `${profile.gated_pages.length} page(s) redirect to the login screen (${profile.gated_pages.slice(0, 5).join(", ")}). Add a test account when you submit the project so MTA can see and test the app.`}
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground">Runtime discovery</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
            <p className="text-2xl font-semibold">{profile.app_type}</p>
            <p className="text-muted-foreground">
              {profile.forms} form(s) · {profile.buttons} button(s) · {profile.pages_inspected} page(s) inspected in {profile.duration_s}s
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Flag on={profile.downloads} label="Downloads" />
            <Flag on={profile.chat_interface} label="Chat interface" />
            <Flag on={profile.authentication} label="Authentication" />
            <Flag on={profile.file_uploads > 0} label="File uploads" />
            {profile.frameworks.map((f) => <Badge key={f} variant="secondary" className="font-normal">{f}</Badge>)}
          </div>
          {profile.classification_signals.length > 0 && (
            <p className="text-xs text-muted-foreground">Why: {profile.classification_signals.join("; ")}</p>
          )}
          {profile.authentication_signals.length > 0 && (
            <p className="text-xs text-muted-foreground">Authentication: {profile.authentication_signals.join("; ")}</p>
          )}
        </CardContent>
      </Card>

      {profile.user_flows.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-sm font-medium text-muted-foreground">User flows found</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm">
            {profile.user_flows.map((f, i) => (
              <div key={i}>
                <p className="font-medium">{f.name}</p>
                <p className="text-xs text-muted-foreground">{f.steps.join(" → ")}</p>
                {f.form_fields && f.form_fields.length > 0 && (
                  <p className="text-xs text-muted-foreground">Fields: {f.form_fields.slice(0, 12).join(", ")}{f.form_fields.length > 12 ? "…" : ""}</p>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader><CardTitle className="text-sm font-medium text-muted-foreground">Pages</CardTitle></CardHeader>
        <CardContent className="divide-y divide-border p-0 text-sm">
          {profile.pages.map((p, i) => (
            <div key={i} className="space-y-1 px-6 py-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs">{p.path}</span>
                {p.status && <span className="text-xs text-muted-foreground">HTTP {p.status}</span>}
                <span className="truncate text-xs text-muted-foreground">{p.title}</span>
                {p.chat_interface && <Badge variant="outline" className="font-normal">chat</Badge>}
              </div>
              <p className="text-xs text-muted-foreground">
                {p.forms.length ? p.forms.map((f) => `${f.is_login ? "login " : ""}form: ${f.field_count} field(s)${f.submit_button ? ` → “${f.submit_button}”` : ""}`).join(" · ") : "no forms"}
                {p.buttons.length ? ` · buttons: ${p.buttons.slice(0, 8).join(", ")}` : ""}
                {p.downloads.buttons.length || p.downloads.links.length ? " · downloads" : ""}
              </p>
            </div>
          ))}
        </CardContent>
      </Card>

      {profile.api_calls.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-sm font-medium text-muted-foreground">API calls observed</CardTitle></CardHeader>
          <CardContent className="grid gap-1 font-mono text-xs sm:grid-cols-2">
            {profile.api_calls.map((c, i) => (
              <span key={i} className={cn(c.status >= 400 ? "text-critical" : "text-muted-foreground")}>
                {c.method} {c.path} → {c.status}
              </span>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
