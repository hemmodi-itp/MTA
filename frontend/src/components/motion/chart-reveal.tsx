"use client";

import { m } from "framer-motion";
import { duration, ease } from "@/lib/motion";
import { usePrefersReducedMotion } from "@/hooks/use-reduced-motion";

/** Chart entrance: the plot fades in and rises 8 px; the series draw (see useChartAnimation) runs inside it. */
export function ChartReveal({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <m.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: duration.page, ease: ease.enter }}
      className={className}
    >
      {children}
    </m.div>
  );
}

/** Recharts animation props: a short ease-out draw (≤ 600 ms), none at all under reduced motion. */
export function useChartAnimation() {
  const reduced = usePrefersReducedMotion();
  return { isAnimationActive: !reduced, animationDuration: 600, animationEasing: "ease-out" as const };
}
