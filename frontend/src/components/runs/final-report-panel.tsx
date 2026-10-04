import { Download, ExternalLink, Printer } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { RunArtifacts } from "@/lib/types";

/** Final Evaluation Report (Component 9): the printable report page, plus Markdown / JSON downloads. */
export function FinalReportPanel({ runId, headline }: { runId: string; headline: NonNullable<RunArtifacts["finalReport"]> }) {
  const url = (format: "html" | "md" | "json") => `/api/runs/${runId}/report?format=${format}`;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          <span className="font-medium text-foreground">{headline.outcome}</span>
          {headline.compliance !== null && <> · compliance {Math.round(headline.compliance)}/100</>}
          {headline.generatedAt && <> · generated {headline.generatedAt}</>}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" size="sm">
            <a href={url("html")} target="_blank" rel="noreferrer"><Printer className="size-4" /> Open to print / save as PDF</a>
          </Button>
          <Button asChild variant="outline" size="sm">
            <a href={url("md")}><Download className="size-4" /> Markdown</a>
          </Button>
          <Button asChild variant="outline" size="sm">
            <a href={url("json")}><Download className="size-4" /> JSON</a>
          </Button>
        </div>
      </div>
      <iframe
        title="Final evaluation report"
        src={url("html")}
        sandbox="allow-popups allow-popups-to-escape-sandbox"
        className="h-[78vh] w-full rounded-lg border border-border bg-background"
      />
      <p className="flex items-center gap-1 text-xs text-muted-foreground">
        <ExternalLink className="size-3" /> Links in the report (screenshots, repository) open in a new tab.
      </p>
    </div>
  );
}
