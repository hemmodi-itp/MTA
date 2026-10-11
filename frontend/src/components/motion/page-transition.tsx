"use client";

import { m } from "framer-motion";
import { usePathname } from "next/navigation";
import { duration, ease } from "@/lib/motion";

/**
 * Page enter: fade + 8 px rise (280 ms, ease-out). Keyed by pathname because the (app) template only remounts when
 * its own segment changes — without the key, /runs → /runs/[id] would not animate. Search-param changes (filters)
 * keep the same path, so they don't replay it. Target objects, not variant labels, so cards inside don't inherit
 * the page's animation and double it.
 */
export function PageTransition({ children, className }: { children: React.ReactNode; className?: string }) {
  const pathname = usePathname();
  return (
    <m.div
      key={pathname}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: duration.page, ease: ease.enter }}
      className={className}
    >
      {children}
    </m.div>
  );
}
