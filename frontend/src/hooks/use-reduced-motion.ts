import { useSyncExternalStore } from "react";

export const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

type MediaQuery = Pick<MediaQueryList, "matches" | "addEventListener" | "removeEventListener">;

/**
 * External store over the OS "reduce motion" setting. `getMedia` returns null on the server (no window), where the
 * answer is always "no preference" so server and first client render agree.
 */
export function createReducedMotionStore(getMedia: () => MediaQuery | null) {
  return {
    subscribe(onChange: () => void) {
      const media = getMedia();
      if (!media) return () => {};
      media.addEventListener("change", onChange);
      return () => media.removeEventListener("change", onChange);
    },
    getSnapshot: () => getMedia()?.matches ?? false,
    getServerSnapshot: () => false,
  };
}

const store = createReducedMotionStore(() =>
  typeof window === "undefined" || !window.matchMedia ? null : window.matchMedia(REDUCED_MOTION_QUERY)
);

/**
 * True while the user asks for reduced motion. Framer components already honour it through <MotionConfig>; use this
 * for everything framer doesn't drive: Recharts animations, count-ups, scripted scrolling, CSS live effects.
 */
export function usePrefersReducedMotion() {
  return useSyncExternalStore(store.subscribe, store.getSnapshot, store.getServerSnapshot);
}
