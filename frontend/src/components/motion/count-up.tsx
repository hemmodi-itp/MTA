"use client";

import { useInView } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { tweenValue } from "@/lib/motion";
import { usePrefersReducedMotion } from "@/hooks/use-reduced-motion";

/**
 * Animated number: counts from the previous value to the new one (0 on first view), and shows the final value at once
 * under reduced motion. The final value is laid out invisibly underneath, so the box never changes width while the
 * digits run (no layout shift); screen readers get only the final value.
 */
export function CountUp({
  value,
  decimals = 0,
  prefix = "",
  suffix = "",
  duration = 0.9,
  align = "start",
  className,
}: {
  value: number | null | undefined;
  decimals?: number;
  prefix?: string;
  suffix?: string;
  duration?: number;
  align?: "start" | "end";
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  const reduced = usePrefersReducedMotion();
  const from = useRef(0);
  const [shown, setShown] = useState(0);

  useEffect(() => {
    if (value == null || !inView || reduced) return;
    const start = performance.now();
    const a = from.current;
    let frame = requestAnimationFrame(function tick(now) {
      const progress = (now - start) / (duration * 1000);
      setShown(tweenValue(a, value, progress));
      if (progress < 1) frame = requestAnimationFrame(tick);
    });
    from.current = value;
    return () => cancelAnimationFrame(frame);
  }, [value, inView, reduced, duration]);

  const format = (v: number) => `${prefix}${v.toFixed(decimals)}${suffix}`;
  if (value == null) return <span className={className}>—</span>;
  return (
    <span ref={ref} className={cn("relative inline-block whitespace-nowrap tabular-nums", className)}>
      <span aria-hidden className="invisible">{format(value)}</span>
      <span aria-hidden className={cn("absolute top-0", align === "end" ? "right-0" : "left-0")}>
        {format(reduced ? value : shown)}
      </span>
      <span className="sr-only">{format(value)}</span>
    </span>
  );
}
