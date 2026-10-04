"use client";

import { motion } from "framer-motion";
import { page } from "@/lib/motion";

/** Route transition for every page inside the app shell (a template re-mounts on navigation). */
export default function AppTemplate({ children }: { children: React.ReactNode }) {
  return (
    <motion.div variants={page} initial="hidden" animate="show" className="space-y-6">
      {children}
    </motion.div>
  );
}
