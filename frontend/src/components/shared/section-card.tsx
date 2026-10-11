"use client";

import { Info } from "lucide-react";
import { MotionCard } from "@/components/motion/motion-card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/** A titled panel: title, optional explainer tooltip and action slot, then content. Used by every page section. */
export function SectionCard({ title, hint, action, className, bodyClassName, headingLevel = 2, children }: {
  title: React.ReactNode;
  hint?: string;
  action?: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  headingLevel?: 2 | 3;
  children: React.ReactNode;
}) {
  const Heading = headingLevel === 2 ? "h2" : "h3";
  return (
    <MotionCard interactive={false} className={cn("flex min-w-0 flex-col", className)}>
      <div className="flex min-h-6 items-center gap-2 px-5 pt-5">
        <Heading className="type-section-title">{title}</Heading>
        {hint && (
          <Tooltip>
            <TooltipTrigger className="rounded-sm text-muted-foreground transition-colors hover:text-foreground" aria-label={`About ${typeof title === "string" ? title : "this section"}`}>
              <Info className="size-3.5" />
            </TooltipTrigger>
            <TooltipContent className="max-w-64">{hint}</TooltipContent>
          </Tooltip>
        )}
        {action && <div className="ml-auto flex items-center gap-2">{action}</div>}
      </div>
      <div className={cn("min-w-0 flex-1 p-5 pt-4", bodyClassName)}>{children}</div>
    </MotionCard>
  );
}
