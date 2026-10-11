"use client";

import { LazyMotion, MotionConfig, domAnimation } from "framer-motion";

/**
 * One motion context for the whole app: framer's small `domAnimation` feature bundle (animations, variants, exit,
 * hover/tap/focus — no layout or drag), loaded once. `strict` makes any stray full-size `motion.*` component throw in
 * development, so every animated element uses `m.*`. reducedMotion="user" drops transform animations when the OS
 * asks for reduced motion.
 */
export function MotionProvider({ children }: { children: React.ReactNode }) {
  return (
    <LazyMotion features={domAnimation} strict>
      <MotionConfig reducedMotion="user">{children}</MotionConfig>
    </LazyMotion>
  );
}
