import { CheckCircle2, ChevronDown, ExternalLink, ListChecks, XCircle } from "lucide-react";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/shared/empty-state";
import { cn } from "@/lib/utils";
import type { BrdCompliance, ComplianceDiscrepancy, Criterion, CriterionVerdict, EvidenceItem, Requirement } from "@/lib/types";

const VERDICT: Record<string, { label: string; className: string }> = {
  verified_pass: { label: "Verified", className: "tone-success" },
  verified: { label: "Verified", className: "tone-success" },
  implemented_static: { label: "Implemented (code)", className: "tone-success" },
  implemented: { label: "Implemented", className: "tone-success" },
  partial: { label: "Partial", className: "tone-warning" },
  contested: { label: "Contested", className: "tone-warning" },
  verified_fail: { label: "Failed at runtime", className: "tone-critical" },
  failed: { label: "Failed", className: "tone-critical" },
  not_implemented: { label: "Not implemented", className: "tone-critical" },
  insufficient_evidence: { label: "Insufficient evidence", className: "tone-neutral" },
  not_technically_verifiable: { label: "Not technically verifiable", className: "tone-neutral" },
};

const STRENGTH_HINT: Record<string, string> = {
  E5: "runtime + deterministic assertion",
  E4: "runtime, judged",
  E3: "code, wired to an entry point",
  E2: "code only",
  E1: "unverified claim (no credit)",
};

function VerdictPill({ v }: { v: string | null }) {
  const s = VERDICT[v ?? ""] ?? { label: v ?? "Pending", className: "tone-neutral" };
  return <span className={cn("pill shrink-0 tone-tint tone-border tone-text", s.className)}>{s.label}</span>;
}

const DISCREPANCY: Record<ComplianceDiscrepancy["kind"], { label: string; className: string }> = {
  broken_at_runtime: { label: "Implemented, but broken at runtime", className: "tone-critical" },
  mixed_runtime: { label: "Inconsistent at runtime", className: "tone-warning" },
  runtime_only_unverified: { label: "Runtime-only, not reached", className: "tone-warning" },
  missed_by_code_review: { label: "Works live, not found in code", className: "tone-neutral" },
};
const MIX = [
  { key: "E5", label: "E5 runtime, deterministic", className: "bg-success" },
  { key: "E4", label: "E4 runtime, judged", className: "bg-success/60" },
  { key: "E3", label: "E3 code, wired", className: "bg-primary/70" },
  { key: "E2", label: "E2 code only", className: "bg-primary/35" },
  { key: "E1", label: "E1 / none: no evidence", className: "bg-muted-foreground/30" },
] as const;

/** BRD Compliance Engine summary: what the evidence rests on, and where code and runtime disagree (Component 8). */
export function ComplianceSummary({ compliance }: { compliance: BrdCompliance }) {
  const m = compliance.evidence_mix.by_strength;
  const counts: Record<string, number> = { ...m, E1: m.E1 + m.none };
  const total = compliance.counts.criteria || 1;
  return (
    <div className="space-y-3 rounded-2xl border border-border bg-card/60 p-4 text-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-medium">What the verdicts rest on</p>
        <p className="text-xs text-muted-foreground">
          {Math.round(compliance.evidence_mix.runtime_share * 100)}% of {compliance.counts.criteria} criteria proven on the live app ·{" "}
          {Math.round(compliance.evidence_mix.credit_by_basis.runtime * 100)}% of earned credit from runtime evidence
        </p>
      </div>
      <div className="flex h-2 overflow-hidden rounded-full bg-muted" role="img" aria-label="Evidence strength mix">
        {MIX.map((x) => counts[x.key] > 0 && (
          <span key={x.key} className={x.className} style={{ width: `${(100 * counts[x.key]) / total}%` }} title={`${x.label}: ${counts[x.key]}`} />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {MIX.map((x) => (
          <span key={x.key} className="inline-flex items-center gap-1.5">
            <span className={cn("size-2 rounded-full", x.className)} />{x.label}: {counts[x.key]}
          </span>
        ))}
      </div>
      {compliance.discrepancies.length > 0 && (
        <div className="space-y-1.5">
          <p className="font-medium">Code vs runtime</p>
          {compliance.discrepancies.map((d) => (
            <div key={d.criterion_code + d.kind} className="flex flex-wrap items-start gap-2 text-xs">
              <span className={cn("pill shrink-0 tone-tint tone-border tone-text", DISCREPANCY[d.kind].className)}>{DISCREPANCY[d.kind].label}</span>
              <span className="font-mono">{d.criterion_code}</span>
              <span className="min-w-0 flex-1 text-muted-foreground">{d.requirement_code} {d.requirement_title} — {d.detail}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Requirement Traceability Matrix: requirement → acceptance criteria → verdict + graded evidence with citations. */
export function TraceabilityMatrix({ requirements, runId }: { requirements: Requirement[]; runId: string }) {
  if (requirements.length === 0) {
    return <EmptyState icon={ListChecks} title="No requirements yet" description="They appear once the BRD has been processed." />;
  }
  return (
    <Accordion type="multiple" className="rounded-2xl border border-border bg-card/60">
      {requirements.map((r) => (
        <AccordionItem key={r.id} value={r.id} className="px-4">
          <AccordionTrigger className="gap-3 text-sm hover:no-underline">
            <span className="flex min-w-0 flex-1 flex-wrap items-center gap-2 text-left">
              <span className="font-mono text-xs text-muted-foreground">{r.code}</span>
              {r.section && <span className="font-mono text-2xs text-muted-foreground">§{r.section}</span>}
              <span className="font-medium">{r.title}</span>
              <Badge variant="secondary" className="font-normal">{r.priority}</Badge>
              {r.origin !== "brd" && (
                <Badge variant="outline" className="font-normal">
                  {r.origin === "inferred" ? `inferred · ${Math.round(r.confidence * 100)}%` : "descriptive · not scored"}
                </Badge>
              )}
            </span>
            {r.score !== null && (
              <span className="w-10 text-right font-mono text-xs tabular-nums text-muted-foreground">{Math.round(r.score * 100)}%</span>
            )}
            <VerdictPill v={r.verdict} />
          </AccordionTrigger>
          <AccordionContent className="space-y-3 pb-4 text-sm">
            <p>{r.description}</p>
            {r.sourceQuote && (
              <blockquote className="border-l-2 border-primary/50 pl-3 text-xs italic text-muted-foreground">
                “{r.sourceQuote}” <span className="not-italic">(quoted from the BRD)</span>
              </blockquote>
            )}
            <div className="space-y-2">
              {r.criteria.map((c) => (
                <CriterionRow key={c.id} c={c} runId={runId} />
              ))}
            </div>
          </AccordionContent>
        </AccordionItem>
      ))}
    </Accordion>
  );
}

function CriterionRow({ c, runId }: { c: Criterion; runId: string }) {
  return (
    <details className="group rounded-xl border border-border px-3 py-2">
      <summary className="flex cursor-pointer list-none items-start gap-2 rounded-sm [&::-webkit-details-marker]:hidden">
        <ChevronDown aria-hidden className="mt-0.5 size-3.5 shrink-0 text-muted-foreground transition-transform duration-(--dur-micro) ease-enter group-open:rotate-180" />
        <span className="mt-0.5 font-mono text-2xs text-muted-foreground">{c.code}</span>
        <span className="flex-1">{c.statement}</span>
        {c.bestStrength && (
          <span title={STRENGTH_HINT[c.bestStrength]} className="shrink-0 rounded border border-border px-1.5 font-mono text-2xs text-muted-foreground">
            {c.bestStrength}
          </span>
        )}
        <VerdictPill v={c.verdict as CriterionVerdict} />
      </summary>
      <div className="mt-2 space-y-2 border-t border-border pt-2 text-xs animate-in fade-in-0 slide-in-from-top-1 duration-(--dur-micro) ease-enter">
        {c.rationale && <p className="text-muted-foreground">{c.rationale}</p>}
        {c.agreement !== null && c.agreement < 1 && (
          <p className="text-warning-fg">The two independent verifier samples disagreed; the more conservative verdict was kept.</p>
        )}
        {c.evidence.length === 0 ? (
          <p className="text-muted-foreground">No evidence recorded.</p>
        ) : (
          <ul className="space-y-1.5">{c.evidence.map((e) => <EvidenceRow key={e.id} e={e} runId={runId} />)}</ul>
        )}
      </div>
    </details>
  );
}

const artifactUrl = (runId: string, p: string) =>
  `/api/runs/${runId}/execution-files/${p.split("/").map(encodeURIComponent).join("/")}`;

function EvidenceRow({ e, runId }: { e: EvidenceItem; runId: string }) {
  const cit = e.citation;
  const where = cit?.file ? `${cit.file}:${cit.start_line}${cit.end_line && cit.end_line !== cit.start_line ? `-${cit.end_line}` : ""}` : null;
  return (
    <li className="flex gap-2">
      {e.validated ? <CheckCircle2 aria-label="validated" className="mt-0.5 size-3.5 shrink-0 text-success-fg" /> : <XCircle aria-label="rejected" className="mt-0.5 size-3.5 shrink-0 text-critical-fg" />}
      <div className="min-w-0 space-y-0.5">
        <div className="flex flex-wrap items-center gap-x-2">
          <span className="font-mono text-2xs text-muted-foreground">{e.strength} · {e.method}</span>
          {where &&
            (cit?.url ? (
              <a href={cit.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-sm font-mono text-2xs text-info-fg hover:underline">
                {where}
                <ExternalLink className="size-3" />
              </a>
            ) : (
              <span className="font-mono text-2xs text-muted-foreground line-through">{where}</span>
            ))}
        </div>
        <p className={cn(!e.validated && "text-muted-foreground")}>{e.summary}</p>
        {cit?.kind === "runtime" && (cit.screenshot || (cit.documents?.length ?? 0) > 0) && (
          <p className="flex flex-wrap gap-x-3 text-2xs">
            {cit.screenshot && (
              <a className="rounded-sm text-info-fg hover:underline" href={artifactUrl(runId, cit.screenshot)} target="_blank" rel="noreferrer">screenshot</a>
            )}
            {(cit.documents ?? []).map((d) => (
              <a key={d.file} className="rounded-sm text-info-fg hover:underline" href={artifactUrl(runId, d.file)}>{d.name}</a>
            ))}
          </p>
        )}
        {!e.validated && cit?.check && <p className="text-critical-fg">Rejected: {cit.check}</p>}
      </div>
    </li>
  );
}
