import { describe, expect, it, vi } from "vitest";
import { createReducedMotionStore, REDUCED_MOTION_QUERY } from "./use-reduced-motion";

/** A stand-in for window.matchMedia(...) that can flip its answer and fire "change". */
function fakeMedia(initial: boolean) {
  const listeners = new Set<() => void>();
  const media = {
    matches: initial,
    addEventListener: vi.fn((_: "change", cb: () => void) => listeners.add(cb)),
    removeEventListener: vi.fn((_: "change", cb: () => void) => listeners.delete(cb)),
    flip(next: boolean) {
      media.matches = next;
      listeners.forEach((cb) => cb());
    },
    listeners,
  };
  return media;
}

describe("reduced-motion store", () => {
  it("queries the standard media feature", () => {
    expect(REDUCED_MOTION_QUERY).toBe("(prefers-reduced-motion: reduce)");
  });

  it("reports the OS setting and follows changes", () => {
    const media = fakeMedia(false);
    const store = createReducedMotionStore(() => media as unknown as MediaQueryList);
    expect(store.getSnapshot()).toBe(false);

    const onChange = vi.fn();
    const unsubscribe = store.subscribe(onChange);
    media.flip(true);
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(store.getSnapshot()).toBe(true);

    unsubscribe();
    expect(media.listeners.size).toBe(0);
    media.flip(false);
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("removes exactly the listener it added", () => {
    const media = fakeMedia(true);
    const store = createReducedMotionStore(() => media as unknown as MediaQueryList);
    const unsubscribe = store.subscribe(() => {});
    const added = media.addEventListener.mock.calls[0][1];
    unsubscribe();
    expect(media.removeEventListener).toHaveBeenCalledWith("change", added);
  });

  it("says 'no preference' on the server and without matchMedia, so hydration matches", () => {
    const store = createReducedMotionStore(() => null);
    expect(store.getServerSnapshot()).toBe(false);
    expect(store.getSnapshot()).toBe(false);
    expect(() => store.subscribe(() => {})()).not.toThrow();
  });
});
