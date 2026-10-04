"use client";

import { motion, type HTMLMotionProps } from "framer-motion";
import { listItem, stagger } from "@/lib/motion";

/** Container that staggers its <StaggerItem> children in (rows, cards, feed items). */
export function Stagger({ step = 0.05, delay = 0, ...props }: HTMLMotionProps<"div"> & { step?: number; delay?: number }) {
  return <motion.div variants={stagger(step, delay)} initial="hidden" animate="show" {...props} />;
}

export function StaggerItem(props: HTMLMotionProps<"div">) {
  return <motion.div variants={listItem} {...props} />;
}
