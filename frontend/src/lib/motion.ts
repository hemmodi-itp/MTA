/**
 * MTA motion system — one vocabulary for every animation in the app. Motion explains a state change; it never decorates.
 *
 *   duration  fast 0.12 (press) · micro 0.16 (hover, toggles) · exit 0.14 · panel 0.24 (dialogs, panels) · page 0.28 (s)
 *             (mirrored as --dur-* in globals.css; micro-interactions stay within 120–200 ms, panels/pages 200–350 ms)
 *   easing    enter = ease-out · exit = ease-in (and shorter) · move = ease-in-out. No springs: they are reserved for
 *             drag and layout animation, and the app ships framer's domAnimation bundle, which has neither.
 *   rule      animate transform and opacity only; enter = fade + 6–8 px rise; lists stagger 30 ms and only the first
 *             STAGGER_CAP items animate. Reduced motion: <MotionConfig reducedMotion="user"> (components/motion/
 *             motion-provider) drops transforms, and usePrefersReducedMotion() covers what framer doesn't drive.
 */
import type { Transition, Variants } from "framer-motion";

export const duration = { fast: 0.12, micro: 0.16, exit: 0.14, panel: 0.24, page: 0.28 } as const;

export const ease = {
  enter: [0.16, 1, 0.3, 1] as const, // expo-out: things arriving
  exit: [0.4, 0, 1, 1] as const, // accelerate: things leaving
  move: [0.65, 0, 0.35, 1] as const, // position changes
  /** @deprecated legacy names kept for the auth screens: out = enter, inOut = move, emphasized = enter */
  out: [0.16, 1, 0.3, 1] as const,
  inOut: [0.65, 0, 0.35, 1] as const,
  emphasized: [0.16, 1, 0.3, 1] as const,
};

export const transition = {
  enter: { duration: duration.panel, ease: ease.enter } satisfies Transition,
  exit: { duration: duration.exit, ease: ease.exit } satisfies Transition,
  micro: { duration: duration.micro, ease: ease.enter } satisfies Transition,
  move: { duration: duration.panel, ease: ease.move } satisfies Transition,
};

/** Lists: 30 ms between items, and only the first 20 animate (long tables render in place). */
export const STAGGER_STEP = 0.03;
export const STAGGER_CAP = 20;
export const animatesAt = (index: number, cap = STAGGER_CAP) => index < cap;

export const fadeIn: Variants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: transition.enter },
  exit: { opacity: 0, transition: transition.exit },
};

export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { duration: duration.page, ease: ease.enter } },
  exit: { opacity: 0, y: 4, transition: transition.exit },
};

export const scaleIn: Variants = {
  hidden: { opacity: 0, scale: 0.97 },
  show: { opacity: 1, scale: 1, transition: transition.enter },
  exit: { opacity: 0, scale: 0.98, transition: transition.exit },
};

export const slideInRight: Variants = {
  hidden: { opacity: 0, x: 24 },
  show: { opacity: 1, x: 0, transition: { duration: duration.page, ease: ease.enter } },
  exit: { opacity: 0, x: 24, transition: transition.exit },
};

export const page: Variants = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { duration: duration.page, ease: ease.enter } },
};

export const stagger = (step = STAGGER_STEP, delay = 0): Variants => ({
  hidden: {},
  show: { transition: { staggerChildren: step, delayChildren: delay } },
});

export const listItem: Variants = {
  hidden: { opacity: 0, y: 6 },
  show: { opacity: 1, y: 0, transition: transition.enter },
  exit: { opacity: 0, transition: transition.exit },
};

export interface Box { left: number; top: number; width: number; height: number }

/**
 * FLIP "invert" step for the sliding indicator: the transform that makes an element laid out at `to` look as if it
 * were still at `from`. Animating it back to identity slides and stretches the indicator using transforms only.
 */
export function flipDelta(from: Box, to: Box) {
  return {
    x: from.left - to.left,
    y: from.top - to.top,
    scaleX: to.width > 0 ? from.width / to.width : 1,
    scaleY: to.height > 0 ? from.height / to.height : 1,
  };
}

/** Ease-out quart: quick start, soft landing. */
export const easeOutQuart = (t: number) => 1 - Math.pow(1 - t, 4);

/** The count-up value `progress` (0–1) of the way from `from` to `to`; lands exactly on `to`. */
export function tweenValue(from: number, to: number, progress: number) {
  const p = Math.min(1, Math.max(0, progress));
  return p >= 1 ? to : from + (to - from) * easeOutQuart(p);
}
