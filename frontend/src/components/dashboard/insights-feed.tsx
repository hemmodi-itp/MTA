"use client";

import Link from "next/link";
import { CheckCircle2, Lightbulb, ShieldAlert, Sparkles, TrendingDown, TrendingUp } from "lucide-react";
import { Stagger, StaggerItem } from "@/components/motion/stagger";
import { EmptyState } from "@/components/shared/empty-state";
import { cn } from "@/lib/utils";
import { TONE_CLASS, type Tone } from "@/lib/status";
import type { Insight, InsightKind } from "@/lib/insights";

const KIND: Record<InsightKind, { icon: typeof ShieldAlert; tone: Tone; label: string }> = {
  risk: { icon: ShieldAlert, tone: "critical", label: "Risk" },
  "trend-down": { icon: TrendingDown, tone: "critical", label: "Regression" },
  "trend-up": { icon: TrendingUp, tone: "success", label: "Trend" },
  recommendation: { icon: Lightbulb, tone: "warning", label: "Recommendation" },
  success: { icon: CheckCircle2, tone: "success", label: "Healthy" },
};

/** AI insights: risks, regressions and recommendations generated from the latest evaluations. */
export function InsightsFeed({ items }: { items: Insight[] }) {
  if (!items.length) {
    return <EmptyState size="inline" icon={Sparkles} title="Nothing needs you right now" description="No risks, regressions or recommendations in the latest runs." />;
  }
  return (
    <Stagger className="space-y-1">
      {items.map((i, idx) => {
        const k = KIND[i.kind];
        return (
          <StaggerItem key={i.id} index={idx}>
            <Link href={i.href} className="group flex gap-3 rounded-xl border border-transparent p-2.5 transition-colors duration-(--dur-micro) hover:border-border hover:bg-muted/40">
              <span className={cn("mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg tone-tint tone-text", TONE_CLASS[k.tone])}>
                <k.icon aria-hidden className="size-4" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2">
                  <span className="truncate text-sm font-semibold transition-colors duration-(--dur-micro) group-hover:text-info-fg">{i.title}</span>
                  <span className="shrink-0 rounded-full border border-border px-1.5 text-[10px] font-medium text-muted-foreground">{k.label}</span>
                </span>
                <span className="line-clamp-2 text-xs leading-relaxed text-muted-foreground">{i.body}</span>
              </span>
            </Link>
          </StaggerItem>
        );
      })}
    </Stagger>
  );
}
