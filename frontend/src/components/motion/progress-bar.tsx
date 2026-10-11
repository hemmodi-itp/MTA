"use client";

import { m } from "framer-motion";
import { cn } from "@/lib/utils";
import { ease } from "@/lib/motion";
import { TONE_CLASS, type Tone } from "@/lib/status";

const HEIGHT = { xs: "h-1", sm: "h-1.5", md: "h-2" } as const;

/**
 * Progress / score bar. The fill is a full-width bar slid with translateX (a transform, so no layout work and the
 * rounded end stays round); value changes ease to the new position. `live` adds a moving sheen while work continues.
 */
export function ProgressBar({
  value,
  tone = "info",
  live = false,
  size = "sm",
  animateOnMount = true,
  label,
  className,
}: {
  value: number;
  tone?: Tone;
  live?: boolean;
  size?: keyof typeof HEIGHT;
  animateOnMount?: boolean;
  label?: string;
  className?: string;
}) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn("relative w-full overflow-hidden rounded-full bg-muted", HEIGHT[size], TONE_CLASS[tone], className)}
    >
      <m.div
        className={cn("absolute inset-0 rounded-full tone-fill", live && "progress-sheen")}
        initial={animateOnMount ? { x: "-100%" } : false}
        animate={{ x: `${pct - 100}%` }}
        transition={{ duration: 0.6, ease: ease.enter }}
      />
    </div>
  );
}

/** Indeterminate bar for work in progress without a known percentage (a run list row while it runs). */
export function IndeterminateBar({ tone = "info", size = "sm", label = "In progress", className }: {
  tone?: Tone; size?: keyof typeof HEIGHT; label?: string; className?: string;
}) {
  return (
    <div role="progressbar" aria-label={label} className={cn("relative w-full overflow-hidden rounded-full bg-muted", HEIGHT[size], TONE_CLASS[tone], className)}>
      <div data-indeterminate className="absolute inset-y-0 left-0 w-2/5 rounded-full tone-fill animate-indeterminate" />
    </div>
  );
}
