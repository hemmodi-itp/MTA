import Link from "next/link";
import { AlertOctagon, TrendingDown, ShieldAlert, FlaskConical, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Recommendation } from "@/lib/types";

const CATEGORY_META: Record<Recommendation["category"], { label: string; icon: typeof AlertOctagon }> = {
  failed_test: { label: "Failed Test", icon: AlertOctagon },
  coverage_gap: { label: "Coverage Gap", icon: TrendingDown },
  weak_validation: { label: "Weak Validation", icon: ShieldAlert },
  missing_negative_case: { label: "Missing Negative Case", icon: FlaskConical },
  flaky_behavior: { label: "Flaky Behavior", icon: RefreshCw },
};

const SEVERITY_CLASS: Record<Recommendation["severity"], string> = {
  critical: "border-l-critical",
  warning: "border-l-warning",
  info: "border-l-primary",
};

export function RecommendationCard({ recommendation }: { recommendation: Recommendation }) {
  const meta = CATEGORY_META[recommendation.category];
  const body = (
    <>
      <meta.icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
      <div className="min-w-0">
        <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{meta.label}</p>
        <p className="mt-0.5">{recommendation.summary}</p>
      </div>
    </>
  );
  const className = cn(
    "flex items-start gap-3 rounded-lg border border-l-4 border-border bg-card px-4 py-3 text-sm",
    SEVERITY_CLASS[recommendation.severity]
  );

  // Only test cases have a detail page today — a scenario-evidenced recommendation
  // renders as a plain (non-clickable) card instead of linking somewhere that 404s.
  if (recommendation.evidenceType !== "test_case") {
    return <div className={className}>{body}</div>;
  }

  return (
    <Link href={`/test-cases/${recommendation.evidenceRef}`} className={cn(className, "transition-colors hover:bg-muted/50")}>
      {body}
    </Link>
  );
}
