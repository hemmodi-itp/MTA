"use client";

import { m, type HTMLMotionProps } from "framer-motion";
import { animatesAt, listItem, stagger, STAGGER_STEP } from "@/lib/motion";

/** Container that staggers its <StaggerItem> children in (cards, feed items). */
export function Stagger({ step = STAGGER_STEP, delay = 0, ...props }: HTMLMotionProps<"div"> & { step?: number; delay?: number }) {
  return <m.div variants={stagger(step, delay)} initial="hidden" animate="show" {...props} />;
}

/** Pass `index` so items past the cap (20) render in place instead of animating. */
export function StaggerItem({ index, ...props }: HTMLMotionProps<"div"> & { index?: number }) {
  return <m.div {...itemMotion(index)} {...props} />;
}

/** Props for any m.* element inside a stagger container (rows: <m.tr {...itemMotion(i)} />). */
export function itemMotion(index?: number) {
  return index == null || animatesAt(index) ? { variants: listItem } : { variants: listItem, initial: false as const };
}
