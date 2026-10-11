/**
 * Status registry — presentation only. Every status the app shows (run, test, pipeline step, risk) maps onto one of
 * eight semantic statuses, and each semantic status has exactly one tone (colour family, see globals.css). Pills, step
 * glyphs, dots and bars read this file, so "failed" looks the same on every page.
 */
import type { Band } from "@/lib/insights";
import type { RiskLevel, RunStatus, StepStatus, TestStatus } from "@/lib/types";

export const TONES = ["success", "warning", "critical", "info", "neutral", "violet", "orange"] as const;
export type Tone = (typeof TONES)[number];

/** Literal class names (so Tailwind generates them) that set --tone / --tone-fg for the tone-* utilities. */
export const TONE_CLASS: Record<Tone, string> = {
  success: "tone-success",
  warning: "tone-warning",
  critical: "tone-critical",
  info: "tone-info",
  neutral: "tone-neutral",
  violet: "tone-violet",
  orange: "tone-orange",
};

export const SEMANTIC_STATUSES = ["passed", "failed", "running", "queued", "inconclusive", "skipped", "flaky", "healed"] as const;
export type SemanticStatus = (typeof SEMANTIC_STATUSES)[number];

export const SEMANTIC_TONE: Record<SemanticStatus, Tone> = {
  passed: "success",
  failed: "critical",
  running: "info",
  queued: "neutral",
  inconclusive: "warning",
  skipped: "neutral",
  flaky: "orange", // not emitted by the backend yet (retry/flaky handling is planned); styled so it is ready
  healed: "violet",
};

const SEMANTIC_LABEL: Record<SemanticStatus, string> = {
  passed: "Passed",
  failed: "Failed",
  running: "Running",
  queued: "Queued",
  inconclusive: "Inconclusive",
  skipped: "Skipped",
  flaky: "Flaky",
  healed: "Healed",
};

type Entry = readonly [SemanticStatus, string];

export const RUN_STATUS: Record<RunStatus, Entry> = {
  queued: ["queued", "Queued"],
  cloning: ["running", "Cloning"],
  installing: ["running", "Installing"],
  launching: ["running", "Launching"],
  running: ["running", "Running"],
  completed: ["passed", "Completed"],
  failed: ["failed", "Failed"],
  cancelled: ["skipped", "Cancelled"],
};

export const TEST_STATUS: Record<TestStatus, Entry> = {
  passed: ["passed", "Passed"],
  failed: ["failed", "Failed"],
  inconclusive: ["inconclusive", "Inconclusive"],
  not_executed: ["skipped", "Not executed"],
  pending: ["queued", "Pending"],
  healed: ["healed", "Healed"],
  skipped: ["skipped", "Skipped"],
};

export const STEP_STATUS: Record<StepStatus, Entry> = {
  pending: ["queued", "Pending"],
  running: ["running", "Running"],
  success: ["passed", "Done"],
  failed: ["failed", "Failed"],
  skipped: ["skipped", "Skipped"],
};

export const RISK_LEVEL: Record<RiskLevel, readonly [Tone, string]> = {
  low: ["success", "Low risk"],
  medium: ["warning", "Medium risk"],
  high: ["critical", "High risk"],
};

export interface StatusMeta {
  /** The value that was looked up, e.g. "cancelled" — lets callers pick a more specific icon. */
  key: string;
  label: string;
  /** null for levels that are not a lifecycle status (risk). */
  semantic: SemanticStatus | null;
  tone: Tone;
}

/** Look up any run / test / step status, semantic status or risk level. Unknown values render neutral. */
export function statusMeta(key: string): StatusMeta {
  const semantic = (SEMANTIC_STATUSES as readonly string[]).includes(key) ? (key as SemanticStatus) : null;
  if (semantic) return { key, label: SEMANTIC_LABEL[semantic], semantic, tone: SEMANTIC_TONE[semantic] };
  const entry = RUN_STATUS[key as RunStatus] ?? TEST_STATUS[key as TestStatus] ?? STEP_STATUS[key as StepStatus];
  if (entry) return { key, label: entry[1], semantic: entry[0], tone: SEMANTIC_TONE[entry[0]] };
  const risk = RISK_LEVEL[key as RiskLevel];
  if (risk) return { key, label: risk[1], semantic: null, tone: risk[0] };
  return { key, label: key.replace(/_/g, " "), semantic: null, tone: "neutral" };
}

/** Score bands (lib/insights → band(): ≥ 75 good · 50–75 warn · < 50 bad) as tones. */
export const BAND_TONE: Record<Band, Tone> = { good: "success", warn: "warning", bad: "critical", none: "neutral" };
