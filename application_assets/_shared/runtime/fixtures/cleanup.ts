// cleanup.ts — the `cleanup` fixture's registry (Phase 4.4).
//
// A test registers what it created: cleanup.register('product 42', { api: (api) => ..., ui: (page) => ... }).
// At teardown the entries run in REVERSE order (last created, first deleted). Each tries its `api` handler first
// and falls back to `ui` when there is no api handler or it throws. A failure is never swallowed: the fixture
// reports every one (test annotation `cleanup_failed`, a cleanup.json attachment, a console warning, and the MTA
// reporter's `cleanup_failures` field); with execution.cleanup_failure: fail it also fails the test.

export interface CleanupHandlers<A = unknown, P = unknown> {
  api?: (api: A) => Promise<unknown> | unknown;
  ui?: (page: P) => Promise<unknown> | unknown;
}

export interface CleanupFailure {
  label: string;
  via: 'api' | 'ui' | 'none';
  error: string;
}

export interface CleanupOutcome {
  done: Array<{ label: string; via: 'api' | 'ui' }>;
  failures: CleanupFailure[];
}

function message(err: unknown): string {
  return (err instanceof Error ? err.message : String(err)).replace(/\x1b\[[0-9;]*m/g, '').split('\n')[0].slice(0, 500);
}

export class CleanupRegistry<A = unknown, P = unknown> {
  private readonly tasks: Array<{ label: string; handlers: CleanupHandlers<A, P> }> = [];

  register(label: string, handlers: CleanupHandlers<A, P>): void {
    if (!handlers || (!handlers.api && !handlers.ui)) {
      throw new Error(`cleanup.register('${label}'): give an api and/or a ui handler`);
    }
    this.tasks.push({ label, handlers });
  }

  get size(): number {
    return this.tasks.length;
  }

  labels(): string[] {
    return this.tasks.map((t) => t.label);
  }

  /** Runs every entry, newest first; never throws. `api` is a getter so the request context is only made when needed. */
  async run(ctx: { api?: () => A | Promise<A>; page?: () => P | Promise<P> }): Promise<CleanupOutcome> {
    const outcome: CleanupOutcome = { done: [], failures: [] };
    for (const { label, handlers } of [...this.tasks].reverse()) {
      let apiError: string | null = null;
      if (handlers.api && ctx.api) {
        try {
          await handlers.api(await ctx.api());
          outcome.done.push({ label, via: 'api' });
          continue;
        } catch (err) {
          apiError = message(err);
        }
      }
      if (handlers.ui && ctx.page) {
        try {
          await handlers.ui(await ctx.page());
          outcome.done.push({ label, via: 'ui' });
          continue;
        } catch (err) {
          outcome.failures.push({ label, via: 'ui', error: apiError ? `api: ${apiError}; ui: ${message(err)}` : message(err) });
          continue;
        }
      }
      outcome.failures.push({ label, via: apiError ? 'api' : 'none', error: apiError ?? 'no usable handler (api/ui context unavailable)' });
    }
    this.tasks.length = 0;
    return outcome;
  }
}
