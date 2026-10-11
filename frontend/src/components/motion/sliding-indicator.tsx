"use client";

import { Component, createContext, useCallback, useContext, useLayoutEffect, useMemo, useRef, type ReactNode } from "react";
import { m, useSpring } from "framer-motion";
import { usePrefersReducedMotion } from "@/hooks/use-reduced-motion";
import { cn } from "@/lib/utils";
import { flipDelta, type Box } from "@/lib/motion";

/*
 * Shared active indicator for nav items, segmented controls and tabs — the effect of framer's `layoutId` without its
 * layout bundle. The indicator always lives inside the active item (so it is server-rendered in the right place and
 * follows resizes for free). When the active item changes, the old indicator's box is recorded just before React
 * commits, and the new one starts transformed onto that box, then animates back to identity (FLIP, transforms only).
 */

interface GroupApi {
  register: (node: HTMLElement | null) => void;
  /** The previous indicator's box, if it was captured in this commit (StrictMode may mount the new one twice). */
  take: () => Box | null;
}

/** A capture older than this belongs to an earlier change, so a later remount must not slide from it. */
const CAPTURE_TTL_MS = 120;

const GroupContext = createContext<GroupApi | null>(null);

/** Runs `onBeforeUpdate` before React mutates the DOM for a new `watch` value (the only hook-free way to do this). */
class BeforeUpdate extends Component<{ watch: unknown; onBeforeUpdate: () => void; children: ReactNode }> {
  getSnapshotBeforeUpdate(prev: { watch: unknown }) {
    if (prev.watch !== this.props.watch) this.props.onBeforeUpdate();
    return null;
  }
  componentDidUpdate() {}
  render() {
    return this.props.children;
  }
}

/** Wrap the items; `activeKey` is whatever identifies the active one (href, tab value…). */
export function IndicatorGroup({ activeKey, children }: { activeKey: unknown; children: ReactNode }) {
  const current = useRef<HTMLElement | null>(null);
  const last = useRef<{ box: Box; at: number } | null>(null);
  const api = useMemo<GroupApi>(() => ({
    register: (node) => {
      current.current = node;
    },
    take: () => (last.current && performance.now() - last.current.at < CAPTURE_TTL_MS ? last.current.box : null),
  }), []);
  const capture = useCallback(() => {
    const r = current.current?.getBoundingClientRect();
    last.current = r && r.width > 0 ? { box: { left: r.left, top: r.top, width: r.width, height: r.height }, at: performance.now() } : null;
  }, []);
  return (
    <GroupContext.Provider value={api}>
      <BeforeUpdate watch={activeKey} onBeforeUpdate={capture}>{children}</BeforeUpdate>
    </GroupContext.Provider>
  );
}

/** Critically damped (no overshoot): the indicator is the app's one layout-style animation, where springs are allowed. */
const SPRING = { stiffness: 520, damping: 48, mass: 1 };

/** Render inside the active item only (the item needs `relative`; its content should sit above with `relative`). */
export function Indicator({ className }: { className?: string }) {
  const group = useContext(GroupContext);
  const ref = useRef<HTMLSpanElement>(null);
  const reduced = usePrefersReducedMotion();
  const x = useSpring(0, SPRING);
  const y = useSpring(0, SPRING);
  const scaleX = useSpring(1, SPRING);
  const scaleY = useSpring(1, SPRING);

  // Before paint: start the indicator on the previous item's box, then let the springs carry it home. Motion values
  // (not animation controls) so it also works through StrictMode's mount → unmount → mount in development.
  useLayoutEffect(() => {
    const node = ref.current;
    group?.register(node);
    const from = group?.take();
    if (from && node && !reduced) {
      // measure the real layout box: StrictMode's second run would otherwise see the transform from the first
      node.style.transform = "none";
      const r = node.getBoundingClientRect();
      const d = flipDelta(from, { left: r.left, top: r.top, width: r.width, height: r.height });
      x.jump(d.x);
      y.jump(d.y);
      scaleX.jump(d.scaleX);
      scaleY.jump(d.scaleY);
      // framer writes the transform on its next frame; set it now so the first paint is already in place
      node.style.transform = `translateX(${d.x}px) translateY(${d.y}px) scaleX(${d.scaleX}) scaleY(${d.scaleY})`;
      x.set(0);
      y.set(0);
      scaleX.set(1);
      scaleY.set(1);
    }
    return () => {
      if (group) group.register(null);
    };
  }, [group, reduced, x, y, scaleX, scaleY]);

  return (
    <m.span
      ref={ref}
      aria-hidden
      style={{ x, y, scaleX, scaleY, originX: 0, originY: 0 }}
      className={cn("pointer-events-none absolute inset-0", className)}
    />
  );
}
