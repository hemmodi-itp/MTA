"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { CheckCircle2, Lightbulb, ShieldAlert, Sparkles, TrendingDown, TrendingUp } from "lucide-react";
import { Stagger, StaggerItem } from "@/components/motion/stagger";
import { cn } from "@/lib/utils";
import type { Insight, InsightKind } from "@/lib/insights";

const KIND: Record<InsightKind, { icon: typeof ShieldAlert; tone: string; label: string }> = {
  risk: { icon: ShieldAlert, tone: "text-critical bg-critical/12", label: "Risk" },
  "trend-down": { icon: TrendingDown, tone: "text-critical bg-critical/12", label: "Regression" },
  "trend-up": { icon: TrendingUp, tone: "text-success bg-success/12", label: "Trend" },
  recommendation: { icon: Lightbulb, tone: "text-warning bg-warning/12", label: "Recommendation" },
  success: { icon: CheckCircle2, tone: "text-success bg-success/12", label: "Healthy" },
};

/** AI insights: risks, regressions and recommendations generated from the latest evaluations. */
export function InsightsFeed({ items }: { items: Insight[] }) {
  if (!items.length) {
    return (
      <div className="flex flex-col items-center gap-2 py-10 text-center text-sm text-muted-foreground">
        <motion.span animate={{ y: [0, -4, 0] }} transition={{ duration: 3, repeat: Infinity }}><Sparkles className="size-6 text-primary" /></motion.span>
        No risks or recommendations right now.
      </div>
    );
  }
  return (
    <Stagger step={0.06} className="space-y-2">
      {items.map((i) => {
        const k = KIND[i.kind];
        return (
          <StaggerItem key={i.id}>
            <Link href={i.href} className="group flex gap-3 rounded-xl border border-transparent p-2.5 transition-colors hover:border-border hover:bg-muted/40">
              <span className={cn("mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg", k.tone)}><k.icon className="size-4" /></span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2">
                  <span className="truncate text-sm font-semibold group-hover:text-primary">{i.title}</span>
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
