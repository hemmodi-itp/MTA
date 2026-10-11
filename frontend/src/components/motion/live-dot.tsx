import { cn } from "@/lib/utils";
import { TONE_CLASS, type Tone } from "@/lib/status";

/** "Live" marker: a dot with a pulse ring (transform + opacity). The only kind of loop the app allows; under reduced
 *  motion the ring stops and the dot stays. */
export function LiveDot({ tone = "info", className }: { tone?: Tone; className?: string }) {
  return (
    <span aria-hidden className={cn("relative inline-flex size-2 shrink-0", TONE_CLASS[tone], className)}>
      <span className="absolute inset-0 rounded-full tone-fill animate-pulse-ring" />
      <span className="relative size-full rounded-full tone-fill" />
    </span>
  );
}
