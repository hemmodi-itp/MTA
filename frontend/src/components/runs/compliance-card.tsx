import { AlertOctagon, AlertTriangle, CheckCircle2 } from "lucide-react";
import { SectionCard } from "@/components/shared/section-card";
import { ProgressBar } from "@/components/motion/progress-bar";
import { CountUp } from "@/components/motion/count-up";
import { cn } from "@/lib/utils";
import { band } from "@/lib/insights";
import { BAND_TONE, TONE_CLASS, type Tone } from "@/lib/status";
import type { ComplianceResult, GateLevel } from "@/lib/types";

const GATE: Record<GateLevel, { icon: typeof CheckCircle2; tone: Tone; label: string }> = {
  pass: { icon: CheckCircle2, tone: "success", label: "Pass" },
  warn: { icon: AlertTriangle, tone: "warning", label: "Warn" },
  block: { icon: AlertOctagon, tone: "critical", label: "Block" },
};

/** BRD Compliance Score (evidence-weighted), its confidence band, verification depth, gates and quality scorecard. */
export function ComplianceCard({ c }: { c: ComplianceResult }) {
  const label = c.scoreKind === "inferred_conformance" ? "Conformance to inferred intent" : "BRD compliance";
  const depth = Math.round((c.verificationDepth ?? 0) * 100);
  const gates = [...c.gates].sort((a, b) => ["block", "warn", "pass"].indexOf(a.level) - ["block", "warn", "pass"].indexOf(b.level));
  return (
    <SectionCard title={label} hint="Evidence-weighted: runtime-proven criteria count fully, code-only evidence at most 75%. Bands: ≥ 75 good, 50–75 needs work, < 50 poor.">
      <div className="space-y-5">
        <div className="flex flex-wrap items-end gap-x-10 gap-y-4">
          <div>
            {c.score === null ? (
              <p className="text-sm text-muted-foreground">Not scored. The gates below and the run log say why.</p>
            ) : (
              <>
                <p className={cn("text-5xl leading-none font-bold tracking-tight tabular-nums tone-text", TONE_CLASS[BAND_TONE[band(c.score)]])}>
                  <CountUp value={Math.round(c.score)} />
                </p>
                <p className="mt-2 text-xs text-muted-foreground">
                  out of 100{c.ciLow !== null && c.ciHigh !== null ? ` · 90% interval ${Math.round(c.ciLow)}–${Math.round(c.ciHigh)}` : ""}
                </p>
              </>
            )}
          </div>
          <div className="min-w-48 flex-1 space-y-2">
            <div className="flex justify-between gap-3 text-xs">
              <span className="text-muted-foreground">Verification depth (runtime-verified criteria)</span>
              <span className="font-semibold tabular-nums">{depth}%</span>
            </div>
            <ProgressBar value={depth} tone="info" label="Verification depth" />
          </div>
        </div>

        {gates.length > 0 && (
          <ul className="space-y-1.5">
            {gates.map((g, i) => {
              const meta = GATE[g.level];
              return (
                <li key={i} className={cn("flex items-start gap-2 rounded-xl border px-3 py-2 text-xs tone-border tone-tint", TONE_CLASS[meta.tone])}>
                  <meta.icon aria-hidden className="mt-0.5 size-3.5 shrink-0 tone-text" />
                  <span>
                    <span className="font-semibold uppercase tone-text">{meta.label}</span>
                    <span className="text-foreground"> · {g.reason}</span>
                  </span>
                </li>
              );
            })}
          </ul>
        )}

        {c.scorecard && (
          <div>
            <p className="mb-2.5 type-eyebrow text-muted-foreground">Quality scorecard (separate from compliance)</p>
            <div className="grid gap-x-8 gap-y-2.5 sm:grid-cols-2">
              {Object.entries(c.scorecard).map(([dim, s]) => (
                <div key={dim} className="grid grid-cols-[minmax(0,10rem)_1fr_2rem] items-center gap-3 text-sm">
                  <span className="truncate capitalize text-muted-foreground">{dim.replace(/_/g, " ")}</span>
                  <ProgressBar value={s} tone={BAND_TONE[band(s)]} label={dim.replace(/_/g, " ")} />
                  <span className="text-right text-xs font-semibold tabular-nums">{s}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </SectionCard>
  );
}
