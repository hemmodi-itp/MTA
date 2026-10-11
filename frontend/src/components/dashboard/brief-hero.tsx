"use client";

import { m } from "framer-motion";
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
      {/* ambient light inside the hero: still, so it doesn't compete with the facts */}
      <div aria-hidden className="pointer-events-none absolute -top-24 -right-24 size-80 rounded-full bg-violet/15 blur-3xl" />
      <div aria-hidden className="pointer-events-none absolute -bottom-28 left-1/3 size-72 rounded-full bg-primary/15 blur-3xl" />

      <m.div variants={stagger(0.06)} initial="hidden" animate="show" className="relative max-w-4xl space-y-4">
        <m.p variants={fadeUp} className="flex items-center gap-2 type-eyebrow text-info-fg">
          <Sparkles aria-hidden className="size-3.5" /> MTA brief
        </m.p>
        <m.h2 variants={fadeUp} className="text-gradient text-2xl leading-tight font-bold tracking-tight text-balance sm:text-[32px] sm:leading-[1.15]">
          {headline}
        </m.h2>
        {lines.map((l, i) => (
          <m.p key={i} variants={fadeUp} className="text-[15px] leading-relaxed text-pretty text-muted-foreground">{l}</m.p>
        ))}
        <m.div variants={fadeUp} className="flex flex-wrap items-center gap-2 pt-2">
          <button type="button" onClick={() => askCopilot("What should I focus on first across my evaluations, and why?")}
            className="inline-flex h-9 items-center gap-2 rounded-xl bg-primary-solid px-4 text-sm font-semibold text-primary-foreground shadow-control transition-[background-color,transform] duration-(--dur-fast) ease-enter hover:bg-primary-solid-hover active:scale-[0.98]">
            <Sparkles aria-hidden className="size-4" /> Ask Copilot what to fix first
          </button>
          {chips.map((c) => (
            <Link key={c.href + c.label} href={c.href}
              className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-border bg-background/40 px-3 text-sm font-medium text-muted-foreground backdrop-blur transition-colors duration-(--dur-micro) hover:border-primary/40 hover:text-foreground">
              {c.label} <ArrowUpRight aria-hidden className="size-3.5" />
            </Link>
          ))}
        </m.div>
      </m.div>
    </MotionCard>
  );
}
