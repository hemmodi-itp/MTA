"use client";

import { AnimatePresence, m } from "framer-motion";
import { duration, ease } from "@/lib/motion";

/**
 * Expand / collapse without animating height (a layout property): the space opens at once — the user asked for it,
 * so it isn't a layout shift — and the content fades in with a 4 px drop, or fades out before the space closes.
 */
export function Collapse({ open, children, className }: { open: boolean; children: React.ReactNode; className?: string }) {
  return (
    <AnimatePresence initial={false}>
      {open && (
        <m.div
          key="collapse"
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0, transition: { duration: duration.micro, ease: ease.enter } }}
          exit={{ opacity: 0, transition: { duration: duration.fast, ease: ease.exit } }}
          className={className}
        >
          {children}
        </m.div>
      )}
    </AnimatePresence>
  );
}
