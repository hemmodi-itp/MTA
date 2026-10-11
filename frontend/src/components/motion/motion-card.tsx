"use client";

import { m, type HTMLMotionProps } from "framer-motion";
import { useCallback } from "react";
import { cn } from "@/lib/utils";
import { fadeUp, transition } from "@/lib/motion";

const LIFT = { y: -2, transition: transition.micro };

/**
 * The card surface of the app. Inside a <Stagger> it fades up with its siblings. `interactive` cards (ones you can
 * click) lift 2 px on hover with a stronger shadow (an opacity fade on a pseudo-element) and a cursor-following glow
 * (.spotlight reads --mx/--my). `highlight` adds the primary→violet gradient border for hero cards.
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
    <m.div
      variants={fadeUp}
      // framer owns this element's transform (entrance), so the hover lift goes through framer too, not CSS
      whileHover={interactive ? LIFT : undefined}
      onMouseMove={interactive ? onMove : undefined}
      className={cn(
        "spotlight rounded-2xl text-card-foreground shadow-card",
        interactive && "card-elevate",
        highlight ? "gradient-border" : "surface-card border border-border",
        className
      )}
      {...props}
    >
      {children}
    </m.div>
  );
}
