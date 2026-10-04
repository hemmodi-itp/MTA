"use client";

import { Info } from "lucide-react";
import { MotionCard } from "@/components/motion/motion-card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/** A dashboard panel: title, optional explainer tooltip and action slot, then content. */
export function Section({ title, hint, action, className, bodyClassName, children }: {
  title: string; hint?: string; action?: React.ReactNode; className?: string; bodyClassName?: string; children: React.ReactNode;
}) {
  return (
    <MotionCard interactive={false} className={cn("flex flex-col", className)}>
      <div className="flex items-center gap-2 px-5 pt-5">
        <h3 className="text-sm font-semibold tracking-tight">{title}</h3>
        {hint && (
          <Tooltip>
            <TooltipTrigger className="text-muted-foreground/70 hover:text-foreground" aria-label={`About ${title}`}><Info className="size-3.5" /></TooltipTrigger>
            <TooltipContent className="max-w-64">{hint}</TooltipContent>
          </Tooltip>
        )}
        <div className="ml-auto">{action}</div>
      </div>
      <div className={cn("flex-1 p-5 pt-4", bodyClassName)}>{children}</div>
    </MotionCard>
  );
}
