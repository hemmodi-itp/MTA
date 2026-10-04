/**
 * Run lifecycle in one place (client and server). Everything that asks "is this run still going?" uses these sets,
 * so a new terminal status (e.g. `cancelled`) can't be missed by one list in one component.
 */
import type { RunStatus } from "@/lib/types";

export const ACTIVE_RUN_STATUSES = ["queued", "cloning", "installing", "launching", "running"] as const satisfies readonly RunStatus[];
export const FINISHED_RUN_STATUSES = ["completed", "failed", "cancelled"] as const satisfies readonly RunStatus[];

export const isActiveStatus = (status?: RunStatus | null): boolean =>
  !!status && (ACTIVE_RUN_STATUSES as readonly string[]).includes(status);

/** No sign of life from the evaluation service for this long while a run is active = stalled (the service auto-fails it). */
export const STALL_AFTER_MS = 10 * 60_000;

/**
 * Minutes since the evaluation service last showed it is working on the run, when that is longer than STALL_AFTER_MS;
 * otherwise null. Queued runs are never "stalled": they can legitimately wait behind another run.
 * `signsOfLife` are extra timestamps (newest log line, step start/finish) so older services without a heartbeat
 * don't read as stalled while they are visibly progressing.
 */
export function stalledMinutes(
  run: { status: RunStatus; heartbeatAt: string | null; startedAt: string },
  signsOfLife: (string | null | undefined)[] = [],
  now = Date.now()
): number | null {
  if (!isActiveStatus(run.status) || run.status === "queued") return null;
  const last = Math.max(...[run.heartbeatAt, run.startedAt, ...signsOfLife].filter(Boolean).map((t) => new Date(t!).getTime()));
  const idle = now - last;
  return Number.isFinite(idle) && idle > STALL_AFTER_MS ? Math.floor(idle / 60_000) : null;
}
