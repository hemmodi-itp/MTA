/**
 * MTA motion system — one vocabulary for every animation in the app.
 *
 *   duration  instant 0.1 · fast 0.16 · base 0.24 · slow 0.4 · slower 0.6   (seconds)
 *   easing    out (enter) · inOut (move) · emphasized (hero) · springs for physical UI
 *   rule      enter = fade + 6–12px rise (no filter blur: it is costly on top of glass), exit = faster fade; lists stagger 40–60ms;
 *             hover = 2px lift; press = 0.98 scale. Everything respects prefers-reduced-motion via
 *             <MotionConfig reducedMotion="user"> in providers.tsx.
 */
import type { Transition, Variants } from "framer-motion";

export const duration = { instant: 0.1, fast: 0.16, base: 0.24, slow: 0.4, slower: 0.6 } as const;

export const ease = {
  out: [0.16, 1, 0.3, 1] as const,          // expo-out: entrances
  inOut: [0.65, 0, 0.35, 1] as const,       // position changes
  emphasized: [0.2, 0, 0, 1] as const,      // hero / page
};

export const spring = {
  snappy: { type: "spring", stiffness: 420, damping: 34, mass: 0.8 } satisfies Transition,
  gentle: { type: "spring", stiffness: 220, damping: 26 } satisfies Transition,
  bouncy: { type: "spring", stiffness: 500, damping: 18 } satisfies Transition,
  layout: { type: "spring", stiffness: 380, damping: 32 } satisfies Transition,
};

export const fadeIn: Variants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { duration: duration.base, ease: ease.out } },
  exit: { opacity: 0, transition: { duration: duration.fast } },
};

export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0, transition: { duration: duration.slow, ease: ease.out } },
  exit: { opacity: 0, y: 6, transition: { duration: duration.fast } },
};

export const scaleIn: Variants = {
  hidden: { opacity: 0, scale: 0.96 },
  show: { opacity: 1, scale: 1, transition: { duration: duration.base, ease: ease.out } },
  exit: { opacity: 0, scale: 0.98, transition: { duration: duration.fast } },
};

export const slideInRight: Variants = {
  hidden: { opacity: 0, x: 28 },
  show: { opacity: 1, x: 0, transition: spring.gentle },
  exit: { opacity: 0, x: 28, transition: { duration: duration.fast } },
};

export const page: Variants = {
  hidden: { opacity: 0, y: 8, scale: 0.995 },
  show: { opacity: 1, y: 0, scale: 1, transition: { duration: duration.slow, ease: ease.emphasized } },
};

export const stagger = (step = 0.05, delay = 0): Variants => ({
  hidden: {},
  show: { transition: { staggerChildren: step, delayChildren: delay } },
});

export const listItem: Variants = {
  hidden: { opacity: 0, y: 6 },
  show: { opacity: 1, y: 0, transition: { duration: duration.base, ease: ease.out } },
};

export const overlay: Variants = {
  hidden: { opacity: 0, backdropFilter: "blur(0px)" },
  show: { opacity: 1, backdropFilter: "blur(6px)", transition: { duration: duration.base } },
  exit: { opacity: 0, backdropFilter: "blur(0px)", transition: { duration: duration.fast } },
};

/** Hover / press physics for interactive surfaces. */
export const hoverLift = { whileHover: { y: -2 }, whileTap: { scale: 0.985 }, transition: spring.snappy } as const;
export const pressable = { whileHover: { scale: 1.02 }, whileTap: { scale: 0.96 }, transition: spring.bouncy } as const;
