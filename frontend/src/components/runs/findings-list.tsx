import { ShieldCheck } from "lucide-react";
import { EmptyState } from "@/components/shared/empty-state";
import { cn } from "@/lib/utils";
import type { Finding } from "@/lib/types";

const SEV: Record<Finding["severity"], string> = {
  critical: "bg-critical text-white border-critical",
  high: "bg-critical/15 text-critical border-critical/30",
  medium: "bg-warning/15 text-warning-foreground border-warning/40 dark:text-warning",
  low: "bg-muted text-muted-foreground border-border",
  info: "bg-muted text-muted-foreground border-border",
};

/** Repository review findings: scanner facts and located LLM design findings, most severe first. */
export function FindingsList({ findings, repoUrl, sha }: { findings: Finding[]; repoUrl: string; sha: string | null }) {
  if (findings.length === 0) {
    return <EmptyState icon={ShieldCheck} title="No findings" description="The review found no security, design or readiness issues." />;
  }
  return (
    <ul className="divide-y divide-border rounded-lg border border-border">
      {findings.map((f) => {
        const href = f.filePath && sha ? `${repoUrl}/blob/${sha}/${f.filePath}${f.startLine ? `#L${f.startLine}` : ""}` : null;
        return (
          <li key={f.id} className="space-y-1 px-4 py-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className={cn("rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase", SEV[f.severity])}>{f.severity}</span>
              <span className="text-xs capitalize text-muted-foreground">{f.dimension.replace(/_/g, " ")}</span>
              <span className="font-medium">{f.title}</span>
              <span className="ml-auto text-[11px] text-muted-foreground">{f.source === "scanner" ? "scanner" : "design review"}</span>
            </div>
            {f.filePath &&
              (href ? (
                <a href={href} target="_blank" rel="noreferrer" className="font-mono text-[11px] text-primary hover:underline">
                  {f.filePath}{f.startLine ? `:${f.startLine}` : ""}
                </a>
              ) : (
                <span className="font-mono text-[11px] text-muted-foreground">{f.filePath}</span>
              ))}
            {f.rationale && <p className="text-muted-foreground">{f.rationale}</p>}
            {f.fix && <p className="text-xs"><span className="font-medium">Fix: </span>{f.fix}</p>}
          </li>
        );
      })}
    </ul>
  );
}
