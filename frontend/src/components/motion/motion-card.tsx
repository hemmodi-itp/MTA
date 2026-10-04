"use client";

import { motion, type HTMLMotionProps } from "framer-motion";
import { useCallback } from "react";
import { cn } from "@/lib/utils";
import { fadeUp, spring } from "@/lib/motion";

/**
 * The interactive surface of the redesign: enters with fade-up, lifts 2px on hover, and shows a cursor-following
 * glow (.spotlight reads --mx/--my). `highlight` adds the primary→violet gradient border for hero cards.
 */
export function MotionCard({
  className,
  highlight = false,
  interactive = true,
  children,
  ...props
}: HTMLMotionProps<"div"> & { highlight?: boolean; interactive?: boolean }) {
  const onMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    e.currentTarget.style.setProperty("--mx", `${e.clientX - r.left}px`);
    e.currentTarget.style.setProperty("--my", `${e.clientY - r.top}px`);
  }, []);

  return (
    <motion.div
      variants={fadeUp}
      whileHover={interactive ? { y: -2 } : undefined}
      transition={spring.snappy}
      onMouseMove={interactive ? onMove : undefined}
      className={cn(
        "spotlight rounded-2xl text-card-foreground shadow-[0_1px_0_0_rgb(255_255_255/0.04)_inset,0_8px_24px_-12px_rgb(2_6_23/0.25)] transition-shadow",
        interactive && "hover:shadow-[0_1px_0_0_rgb(255_255_255/0.06)_inset,0_18px_40px_-16px_var(--glow)]",
        highlight ? "gradient-border" : "surface-card border border-border",
        className
      )}
      {...props}
    >
      {children}
    </motion.div>
  );
}
