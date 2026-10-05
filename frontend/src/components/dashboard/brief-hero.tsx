"use client";

import { motion } from "framer-motion";
import { ArrowUpRight, Sparkles } from "lucide-react";
import Link from "next/link";
import { MotionCard } from "@/components/motion/motion-card";
import { useUIStore } from "@/lib/stores/ui-store";
import { fadeUp, stagger } from "@/lib/motion";

/** Hero: the MTA brief — one headline and the few facts behind it, written from the live portfolio numbers. */
export function BriefHero({ headline, lines, chips }: {
  headline: string; lines: string[]; chips: { label: string; href: string }[];
}) {
  const askCopilot = useUIStore((s) => s.askCopilot);
  return (
    <MotionCard highlight interactive={false} className="relative overflow-hidden p-6 sm:p-8">
      {/* ambient mesh inside the hero */}
      <motion.div aria-hidden className="pointer-events-none absolute -right-24 -top-24 size-80 rounded-full bg-violet/20 blur-3xl"
        animate={{ scale: [1, 1.12, 1], opacity: [0.6, 0.9, 0.6] }} transition={{ duration: 8, repeat: Infinity, ease: "easeInOut" }} />
      <motion.div aria-hidden className="pointer-events-none absolute -bottom-28 left-1/3 size-72 rounded-full bg-primary/20 blur-3xl"
        animate={{ scale: [1.1, 1, 1.1] }} transition={{ duration: 10, repeat: Infinity, ease: "easeInOut" }} />

      <motion.div variants={stagger(0.08)} initial="hidden" animate="show" className="relative max-w-4xl space-y-4">
        <motion.p variants={fadeUp} className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-primary">
          <Sparkles className="size-3.5" /> MTA brief
        </motion.p>
        <motion.h2 variants={fadeUp} className="text-gradient text-2xl font-bold leading-tight tracking-tight sm:text-[32px] sm:leading-[1.15]">
          {headline}
        </motion.h2>
        {lines.map((l, i) => (
          <motion.p key={i} variants={fadeUp} className="text-[15px] leading-relaxed text-muted-foreground">{l}</motion.p>
        ))}
        <motion.div variants={fadeUp} className="flex flex-wrap items-center gap-2 pt-2">
          <button type="button" onClick={() => askCopilot("What should I focus on first across my evaluations, and why?")}
            className="inline-flex h-9 items-center gap-2 rounded-xl bg-gradient-to-r from-primary to-violet px-4 text-sm font-semibold text-white shadow-lg shadow-primary/25 transition-transform hover:scale-[1.02] active:scale-[0.98]">
            <Sparkles className="size-4" /> Ask Copilot what to fix first
          </button>
          {chips.map((c) => (
            <Link key={c.href + c.label} href={c.href}
              className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-border bg-background/40 px-3 text-sm font-medium text-muted-foreground backdrop-blur transition-colors hover:border-primary/40 hover:text-foreground">
              {c.label} <ArrowUpRight className="size-3.5" />
            </Link>
          ))}
        </motion.div>
      </motion.div>
    </MotionCard>
  );
}
