import { cn } from "@/lib/utils";
import { band } from "@/lib/insights";
import { BAND_TONE, TONE_CLASS } from "@/lib/status";
import { ProgressBar } from "@/components/motion/progress-bar";

/** A 0–100 score as a tinted chip in its band colour (≥ 75 good · 50–75 warn · < 50 bad); "—" when not scored. */
export function ScoreBadge({ score, className, title }: { score: number | null | undefined; className?: string; title?: string }) {
  if (score == null) {
    return <span title={title ?? "Not scored"} className={cn("text-sm text-muted-foreground", className)}>—</span>;
  }
  return (
    <span
      title={title}
      className={cn(
        "inline-flex h-6 min-w-9 items-center justify-center rounded-md border px-1.5 text-sm font-semibold tabular-nums tone-tint tone-border tone-text",
        TONE_CLASS[BAND_TONE[band(score)]],
        className
      )}
    >
      {Math.round(score)}
    </span>
  );
}

/** Score bar in the band colour with the number beside it. */
export function ScoreBar({ score, className, animateOnMount = true }: { score: number; className?: string; animateOnMount?: boolean }) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <ProgressBar value={score} tone={BAND_TONE[band(score)]} animateOnMount={animateOnMount} className="flex-1" label="Score" />
      <span className="w-7 text-right text-sm font-semibold tabular-nums">{Math.round(score)}</span>
    </div>
  );
}
