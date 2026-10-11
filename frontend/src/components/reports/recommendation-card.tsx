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
  critical: "tone-critical",
  warning: "tone-warning",
  info: "tone-info",
};

export function RecommendationCard({ recommendation }: { recommendation: Recommendation }) {
  const meta = CATEGORY_META[recommendation.category];
  const body = (
    <>
      <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg tone-tint tone-text"><meta.icon aria-hidden className="size-3.5" /></span>
      <div className="min-w-0">
        <p className="type-eyebrow text-muted-foreground">{meta.label}</p>
        <p className="mt-0.5 text-pretty wrap-anywhere">{recommendation.summary}</p>
      </div>
    </>
  );
  const className = cn(
    "flex items-start gap-3 rounded-xl border border-border bg-card/80 px-4 py-3 text-sm",
    SEVERITY_CLASS[recommendation.severity]
  );

  return <div className={className}>{body}</div>;
}
