import { cn } from "@/lib/utils";
import type { RiskLevel, RunStatus, TestStatus } from "@/lib/types";

type Kind = RunStatus | TestStatus | RiskLevel;

const STYLES: Record<string, string> = {
  passed: "bg-success/15 text-success border-success/30",
  completed: "bg-success/15 text-success border-success/30",
  low: "bg-success/15 text-success border-success/30",
  healed: "bg-primary/15 text-primary border-primary/30",
  running: "bg-primary/15 text-primary border-primary/30",
  queued: "bg-muted text-muted-foreground border-border",
  cloning: "bg-muted text-muted-foreground border-border",
  installing: "bg-muted text-muted-foreground border-border",
  launching: "bg-muted text-muted-foreground border-border",
  skipped: "bg-muted text-muted-foreground border-border",
  pending: "bg-muted text-muted-foreground border-border",
  not_executed: "bg-muted text-muted-foreground border-border",
  cancelled: "bg-muted text-muted-foreground border-border",
  // ran, but the evidence can't call it either way: amber, but quieter than a warning
  inconclusive: "bg-warning/10 text-warning-foreground/80 border-warning/25 dark:text-warning/85",
  medium: "bg-warning/15 text-warning-foreground border-warning/40 dark:text-warning",
  failed: "bg-critical/15 text-critical border-critical/30",
  high: "bg-critical/15 text-critical border-critical/30",
};

const LABELS: Record<string, string> = {
  passed: "Passed",
  completed: "Completed",
  failed: "Failed",
  healed: "Healed",
  skipped: "Skipped",
  pending: "Pending",
  not_executed: "Not executed",
  inconclusive: "Inconclusive",
  cancelled: "Cancelled",
  queued: "Queued",
  cloning: "Cloning",
  installing: "Installing",
  launching: "Launching",
  running: "Running",
  low: "Low risk",
  medium: "Medium risk",
  high: "High risk",
};

export function StatusPill({ status, className }: { status: Kind; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        STYLES[status] ?? "bg-muted text-muted-foreground border-border",
        className
      )}
    >
      <span className="size-1.5 rounded-full bg-current" />
      {LABELS[status] ?? status}
    </span>
  );
}
