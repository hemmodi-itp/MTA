import { ListChecks } from "lucide-react";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/shared/empty-state";
import { cn } from "@/lib/utils";
import type { Requirement, RequirementStatus, TestCase } from "@/lib/types";

const STATUS: Record<RequirementStatus, { label: string; className: string }> = {
  implemented: { label: "Implemented", className: "bg-success/15 text-success border-success/30" },
  partial: { label: "Partial", className: "bg-warning/15 text-warning-foreground border-warning/40 dark:text-warning" },
  missing: { label: "Missing", className: "bg-critical/15 text-critical border-critical/30" },
  unknown: { label: "Not reviewed", className: "bg-muted text-muted-foreground border-border" },
};

/** BRD requirements with the static-review verdict and the live test results traced to each. */
export function RequirementsList({ requirements, tests }: { requirements: Requirement[]; tests: TestCase[] }) {
  if (requirements.length === 0) {
    return (
      <EmptyState icon={ListChecks} title="No requirements yet" description="They appear once the BRD has been processed." />
    );
  }
  return (
    <Accordion type="multiple" className="rounded-lg border border-border">
      {requirements.map((r) => {
        const traced = tests.filter((t) => t.requirementRef === r.code);
        const passed = traced.filter((t) => t.status === "passed").length;
        const executed = traced.filter((t) => t.status === "passed" || t.status === "failed").length;
        const status = STATUS[r.status];
        return (
          <AccordionItem key={r.id} value={r.id} className="px-4">
            <AccordionTrigger className="gap-3 text-sm hover:no-underline">
              <span className="flex min-w-0 flex-1 flex-wrap items-center gap-2 text-left">
                <span className="font-mono text-xs text-muted-foreground">{r.code}</span>
                {r.section && <span className="font-mono text-[11px] text-muted-foreground/80">§{r.section}</span>}
                <span className="font-medium">{r.title}</span>
                <Badge variant="secondary" className="font-normal">{r.priority}</Badge>
              </span>
              {executed > 0 && (
                <span className={cn("text-xs tabular-nums", passed === executed ? "text-success" : "text-critical")}>
                  {passed}/{executed} tests
                </span>
              )}
              <span className={cn("rounded-full border px-2 py-0.5 text-xs font-medium", status.className)}>{status.label}</span>
            </AccordionTrigger>
            <AccordionContent className="space-y-3 pb-4 text-sm">
              <p>{r.description}</p>
              {r.sourceQuote && (
                <blockquote className="border-l-2 border-primary/50 pl-3 text-xs italic text-muted-foreground">
                  “{r.sourceQuote}”
                  <span className="not-italic"> (quoted from the BRD)</span>
                </blockquote>
              )}
              {r.acceptanceCriteria.length > 0 && (
                <div>
                  <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Acceptance criteria</p>
                  <ul className="list-disc space-y-0.5 pl-5 text-muted-foreground">
                    {r.acceptanceCriteria.map((c, i) => (
                      <li key={i}>{c}</li>
                    ))}
                  </ul>
                </div>
              )}
              {r.evidence && (
                <div>
                  <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Code review evidence</p>
                  <p className="text-muted-foreground">{r.evidence}</p>
                </div>
              )}
            </AccordionContent>
          </AccordionItem>
        );
      })}
    </Accordion>
  );
}
