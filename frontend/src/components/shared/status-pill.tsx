import {
  Ban, CheckCircle2, CircleHelp, CircleMinus, CircleSlash, Clock3, ShieldAlert, ShieldCheck, ShieldX, Shuffle, Wand2, XCircle,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { statusMeta, TONE_CLASS, type SemanticStatus } from "@/lib/status";
import { LiveDot } from "@/components/motion/live-dot";
import type { RiskLevel, RunStatus, StepStatus, TestStatus } from "@/lib/types";

type Kind = RunStatus | TestStatus | StepStatus | RiskLevel | SemanticStatus;

/** One icon per semantic status, so colour is never the only cue. "running" uses the live dot instead. */
export const STATUS_ICON: Record<SemanticStatus, LucideIcon | null> = {
  passed: CheckCircle2,
  failed: XCircle,
  running: null,
  queued: Clock3,
  inconclusive: CircleHelp,
  skipped: CircleMinus,
  flaky: Shuffle,
  healed: Wand2,
};

/** More specific icons for a few values that share a semantic status. */
const KEY_ICON: Partial<Record<string, LucideIcon>> = {
  cancelled: Ban,
  not_executed: CircleSlash,
  low: ShieldCheck,
  medium: ShieldAlert,
  high: ShieldX,
};

export function StatusPill({ status, label, className }: { status: Kind; label?: string; className?: string }) {
  const meta = statusMeta(status);
  const Icon = KEY_ICON[meta.key] ?? (meta.semantic ? STATUS_ICON[meta.semantic] : null);
  return (
    <span className={cn("pill tone-tint tone-border tone-text", TONE_CLASS[meta.tone], className)}>
      {meta.semantic === "running" ? <LiveDot tone={meta.tone} /> : Icon ? <Icon aria-hidden className="size-3 shrink-0" /> : null}
      {label ?? meta.label}
    </span>
  );
}
