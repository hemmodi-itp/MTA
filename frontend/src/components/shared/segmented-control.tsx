"use client";

import { ToggleGroup } from "radix-ui";
import { cn } from "@/lib/utils";
import { Indicator, IndicatorGroup } from "@/components/motion/sliding-indicator";

export interface SegmentItem {
  value: string;
  label: string;
  /** null while loading: the space is kept so the control doesn't widen when counts arrive */
  count?: number | null;
}

/**
 * Single-choice filter (a radio group: arrow keys move, one tab stop) with a sliding active pill. Scrolls sideways
 * with soft edges when it doesn't fit (phones). For switching content panels use <Tabs> instead.
 */
export function SegmentedControl({ items, value, onValueChange, label, className }: {
  items: SegmentItem[];
  value: string;
  onValueChange: (value: string) => void;
  label: string;
  className?: string;
}) {
  return (
    // phones: the control scrolls sideways; the right edge fades out and trailing padding lets the last item clear it
    <div className={cn("no-scrollbar max-w-full overflow-x-auto max-sm:pr-6 max-sm:mask-[linear-gradient(to_right,#000_calc(100%-24px),transparent)]", className)}>
    <ToggleGroup.Root
      type="single"
      value={value}
      // a single toggle group lets you clear the selection; a filter always has one active segment
      onValueChange={(next) => next !== "" && onValueChange(next)}
      aria-label={label}
      className="inline-flex rounded-xl border border-border bg-muted/50 p-1"
    >
      <IndicatorGroup activeKey={value}>
        {items.map((item) => {
          const active = item.value === value;
          return (
            <ToggleGroup.Item
              key={item.value}
              value={item.value}
              className={cn(
                "relative flex h-8 shrink-0 items-center gap-1.5 rounded-lg px-3 text-sm font-medium whitespace-nowrap transition-colors duration-(--dur-micro)",
                "focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring",
                active ? "text-foreground" : "text-muted-foreground hover:text-foreground"
              )}
            >
              {active && <Indicator className="rounded-lg bg-background shadow-control ring-1 ring-border dark:bg-input/50" />}
              <span className="relative">{item.label}</span>
              {item.count !== undefined && (
                <span className={cn("relative min-w-[2ch] text-xs tabular-nums text-muted-foreground", item.count === null && "invisible")}>{item.count ?? 0}</span>
              )}
            </ToggleGroup.Item>
          );
        })}
      </IndicatorGroup>
    </ToggleGroup.Root>
    </div>
  );
}
