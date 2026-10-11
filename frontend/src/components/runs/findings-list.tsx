import { ShieldCheck } from "lucide-react";
import { EmptyState } from "@/components/shared/empty-state";
import { cn } from "@/lib/utils";
import type { Finding } from "@/lib/types";

const SEV: Record<Finding["severity"], string> = {
  critical: "border-transparent bg-critical-solid text-white",
  high: "tone-critical tone-tint tone-border tone-text",
  medium: "tone-warning tone-tint tone-border tone-text",
  low: "tone-neutral tone-tint tone-border tone-text",
  info: "tone-neutral tone-tint tone-border tone-text",
};

/** Repository review findings: scanner facts and located LLM design findings, most severe first. */
export function FindingsList({ findings, repoUrl, sha }: { findings: Finding[]; repoUrl: string; sha: string | null }) {
  if (findings.length === 0) {
    return <EmptyState icon={ShieldCheck} title="No findings" description="The review found no security, design or readiness issues." />;
  }
  return (
    <ul className="divide-y divide-border overflow-hidden rounded-2xl border border-border bg-card/60">
      {findings.map((f) => {
        const href = f.filePath && sha ? `${repoUrl}/blob/${sha}/${f.filePath}${f.startLine ? `#L${f.startLine}` : ""}` : null;
        return (
          <li key={f.id} className="space-y-1.5 px-4 py-3.5 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className={cn("pill h-5 px-2 text-2xs font-semibold uppercase", SEV[f.severity])}>{f.severity}</span>
              <span className="text-xs capitalize text-muted-foreground">{f.dimension.replace(/_/g, " ")}</span>
              <span className="font-medium">{f.title}</span>
              <span className="ml-auto text-2xs text-muted-foreground">{f.source === "scanner" ? "scanner" : "design review"}</span>
            </div>
            {f.filePath &&
              (href ? (
                <a href={href} target="_blank" rel="noreferrer" className="rounded-sm font-mono text-2xs text-info-fg hover:underline">
                  {f.filePath}{f.startLine ? `:${f.startLine}` : ""}
                </a>
              ) : (
                <span className="font-mono text-2xs text-muted-foreground">{f.filePath}</span>
              ))}
            {f.rationale && <p className="text-muted-foreground">{f.rationale}</p>}
            {f.fix && <p className="text-xs"><span className="font-medium">Fix: </span>{f.fix}</p>}
          </li>
        );
      })}
    </ul>
  );
}
