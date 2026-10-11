import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { TONE_CLASS, type Tone } from "@/lib/status";

/** An inline banner about the state of the thing on screen (cancelled, stalled, sample data…). */
export function Notice({ tone = "neutral", icon: Icon, title, children, className }: {
  tone?: Tone;
  icon: LucideIcon;
  title: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <div role="status" className={cn("flex gap-3 rounded-2xl border tone-border tone-tint p-4 text-sm", TONE_CLASS[tone], className)}>
      <Icon aria-hidden className="mt-0.5 size-4 shrink-0 tone-text" />
      <div className="min-w-0 space-y-1">
        <p className="font-medium text-foreground">{title}</p>
        {children && <div className="text-pretty text-muted-foreground">{children}</div>}
      </div>
    </div>
  );
}
