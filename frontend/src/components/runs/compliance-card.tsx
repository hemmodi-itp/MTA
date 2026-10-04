import { AlertOctagon, AlertTriangle, CheckCircle2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { ComplianceResult } from "@/lib/types";

function tone(score: number) {
  if (score >= 80) return "text-success";
  if (score >= 60) return "text-warning-foreground dark:text-warning";
  return "text-critical";
}

const GATE_ICON = { pass: CheckCircle2, warn: AlertTriangle, block: AlertOctagon };
const GATE_STYLE = {
  pass: "border-success/30 bg-success/10 text-success",
  warn: "border-warning/40 bg-warning/10 text-warning-foreground dark:text-warning",
  block: "border-critical/40 bg-critical/10 text-critical",
};

/** BRD Compliance Score (evidence-weighted), its confidence band, verification depth, gates and quality scorecard. */
export function ComplianceCard({ c }: { c: ComplianceResult }) {
  const label = c.scoreKind === "inferred_conformance" ? "Conformance to inferred intent" : "BRD compliance";
  const depth = Math.round((c.verificationDepth ?? 0) * 100);
  const gates = [...c.gates].sort((a, b) => ["block", "warn", "pass"].indexOf(a.level) - ["block", "warn", "pass"].indexOf(b.level));
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="flex flex-wrap items-end gap-x-8 gap-y-4">
          <div>
            {c.score === null ? (
              <p className="text-sm text-muted-foreground">Not scored. The gates below and the run log say why.</p>
            ) : (
              <>
                <p className={cn("font-mono text-5xl font-bold tabular-nums", tone(c.score))}>{Math.round(c.score)}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  / 100{c.ciLow !== null && c.ciHigh !== null ? ` · 90% interval ${Math.round(c.ciLow)}–${Math.round(c.ciHigh)}` : ""}
                </p>
              </>
            )}
          </div>
          <div className="min-w-48 flex-1 space-y-1.5">
            <div className="flex justify-between text-xs">
              <span className="text-muted-foreground">Verification depth (runtime-verified criteria)</span>
              <span className="font-mono tabular-nums">{depth}%</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-muted">
              <div className="h-full rounded-full bg-primary" style={{ width: `${depth}%` }} />
            </div>
            <p className="text-xs text-muted-foreground">
              Credit is scaled by evidence strength: runtime-proven counts fully, code-only at most 75%.
            </p>
          </div>
        </div>

        <div className="space-y-1.5">
          {gates.map((g, i) => {
            const Icon = GATE_ICON[g.level];
            return (
              <div key={i} className={cn("flex items-start gap-2 rounded-md border px-3 py-2 text-xs", GATE_STYLE[g.level])}>
                <Icon className="mt-0.5 size-3.5 shrink-0" />
                <span>
                  <span className="font-semibold uppercase">{g.level}</span> · {g.reason}
                </span>
              </div>
            );
          })}
        </div>

        {c.scorecard && (
          <div>
            <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Quality scorecard (separate from compliance)
            </p>
            <div className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
              {Object.entries(c.scorecard).map(([dim, s]) => (
                <div key={dim} className="flex items-center gap-3 text-sm">
                  <span className="w-40 shrink-0 capitalize text-muted-foreground">{dim.replace(/_/g, " ")}</span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                    <div
                      className={cn("h-full rounded-full", s >= 80 ? "bg-success" : s >= 60 ? "bg-warning" : "bg-critical")}
                      style={{ width: `${s}%` }}
                    />
                  </div>
                  <span className="w-8 text-right font-mono text-xs tabular-nums">{s}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
