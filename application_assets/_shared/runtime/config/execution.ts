// execution.ts — the `execution:` block of project.yaml (Phase 4), TypeScript side.
//
// Mirrors tools/execution/config.py: same keys, same defaults, same fallback for an invalid value
// (default + one warning). Both sides are tested against tests/fixtures/execution_config_cases.json —
// change them together.

export const KNOWN_PROJECTS = ['chromium', 'firefox', 'webkit', 'pixel-7', 'iphone-14'] as const;
export type ProjectName = (typeof KNOWN_PROJECTS)[number];

const TRACE_MODES = ['off', 'on', 'retain-on-failure', 'on-first-retry', 'on-all-retries', 'retain-on-first-failure'];
const VIDEO_MODES = ['off', 'on', 'retain-on-failure', 'on-first-retry'];
const SCREENSHOT_MODES = ['off', 'on', 'only-on-failure', 'on-first-failure'];
const SUITE_MODES = ['files', 'grep'];
const CONSOLE_GUARD_MODES = ['off', 'warn', 'fail'];
const NETWORK_MODES = ['off', 'on-failure', 'on'];
const CLEANUP_FAILURE_MODES = ['warn', 'fail'];
const ATTR_RE = /^[A-Za-z_][\w.:-]*$/;

export interface ExecutionConfig {
  matrix: string[];
  test_id_attribute: string;
  locale: string | null;
  timezone_id: string | null;
  trace: string;
  video: string;
  screenshot: string;
  junit: boolean;
  mta_reporter: boolean;
  role_auth: boolean;
  role_auth_max_age_minutes: number;
  suite_mode: string;
  shards: number;
  max_parallel_shards: number;
  // Phase 4 (session 2)
  retries: 'auto' | number;
  fail_on_flaky_tests: 'auto' | boolean;
  data_isolation: boolean;
  console_guard: string;
  network: string;
  cleanup_failure: string;
  test_steps: boolean;
  module_roles: boolean;
  projects: string[];
}

export const DEFAULTS: Omit<ExecutionConfig, 'projects'> = {
  matrix: ['chromium'],
  test_id_attribute: 'data-testid',
  locale: null,
  timezone_id: null,
  trace: 'retain-on-failure',
  video: 'retain-on-failure',
  screenshot: 'only-on-failure',
  junit: true,
  mta_reporter: true,
  role_auth: false,
  role_auth_max_age_minutes: 30,
  suite_mode: 'files',
  shards: 1,
  max_parallel_shards: 1,
  retries: 'auto',
  fail_on_flaky_tests: 'auto',
  data_isolation: false,
  console_guard: 'warn',
  network: 'on-failure',
  cleanup_failure: 'warn',
  test_steps: true,
  module_roles: false,
};

type Env = Record<string, string | undefined>;

/** retries for one run: headed -> 0; 'auto' -> 2 in CI, 1 locally (same as config.py::effective_retries). */
export function effectiveRetries(exec: Pick<ExecutionConfig, 'retries'>, env: Env, headed = false): number {
  if (headed) return 0;
  if (exec.retries === 'auto') return env.CI ? 2 : 1;
  return exec.retries;
}

/** failOnFlakyTests: 'auto' -> true in CI (same as config.py::effective_fail_on_flaky). */
export function effectiveFailOnFlaky(exec: Pick<ExecutionConfig, 'fail_on_flaky_tests'>, env: Env): boolean {
  return exec.fail_on_flaky_tests === 'auto' ? !!env.CI : exec.fail_on_flaky_tests;
}

type Warn = (message: string) => void;

function isMapping(v: unknown): v is Record<string, any> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

/** 'Pixel 7' / 'pixel_7' / 'PIXEL-7' -> 'pixel-7' (same as config.py::project_slug). */
export function projectSlug(name: unknown): string {
  return String(name).trim().toLowerCase().replace(/[\s_]+/g, '-');
}

export function resolveProjects(matrix: string[], profile: string | null, warn: Warn = () => {}): string[] {
  const wanted = new Set(matrix.map(projectSlug));
  if (profile === 'smoke') {
    const extra = [...wanted].filter((p) => p !== 'chromium').sort();
    if (extra.length) warn(`[execution] test_generation.profile=smoke runs chromium only — ignoring matrix ${extra}`);
    return ['chromium'];
  }
  return KNOWN_PROJECTS.filter((p) => p === 'chromium' || wanted.has(p));
}

export function resolveExecutionConfig(raw: unknown, warn: Warn = (m) => console.warn(m)): ExecutionConfig {
  const project = isMapping(raw) ? raw : {};
  const block: Record<string, any> = isMapping(project.execution) ? project.execution : {};
  const bad = (key: string, value: unknown, fallback: unknown) =>
    warn(`[execution] invalid execution.${key}=${JSON.stringify(value)} — using ${JSON.stringify(fallback)}`);

  const has = (key: string) => Object.prototype.hasOwnProperty.call(block, key);
  const enumOf = (key: keyof typeof DEFAULTS, allowed: string[]): string => {
    if (!has(key) || block[key] === null || block[key] === undefined) return DEFAULTS[key] as string;
    const value = String(block[key]).trim();
    if (allowed.includes(value)) return value;
    bad(key, block[key], DEFAULTS[key]);
    return DEFAULTS[key] as string;
  };
  const bool = (key: keyof typeof DEFAULTS): boolean => {
    const value = has(key) ? block[key] : DEFAULTS[key];
    if (typeof value === 'boolean') return value;
    bad(key, value, DEFAULTS[key]);
    return DEFAULTS[key] as boolean;
  };
  const int = (key: keyof typeof DEFAULTS, lo: number, hi: number): number => {
    const value = has(key) ? block[key] : DEFAULTS[key];
    if (typeof value !== 'number' || !Number.isInteger(value) || value < lo || value > hi) {
      bad(key, value, DEFAULTS[key]);
      return DEFAULTS[key] as number;
    }
    return value;
  };
  const isAuto = (v: unknown) => v === null || v === undefined || (typeof v === 'string' && v.trim().toLowerCase() === 'auto');
  const autoInt = (key: 'retries', lo: number, hi: number): 'auto' | number => {
    const value = has(key) ? block[key] : DEFAULTS[key];
    if (isAuto(value)) return 'auto';
    if (typeof value !== 'number' || !Number.isInteger(value) || value < lo || value > hi) {
      bad(key, value, DEFAULTS[key]);
      return DEFAULTS[key];
    }
    return value;
  };
  const autoBool = (key: 'fail_on_flaky_tests'): 'auto' | boolean => {
    const value = has(key) ? block[key] : DEFAULTS[key];
    if (isAuto(value)) return 'auto';
    if (typeof value === 'boolean') return value;
    bad(key, value, DEFAULTS[key]);
    return DEFAULTS[key];
  };
  const optStr = (key: keyof typeof DEFAULTS): string | null => {
    const value = block[key];
    if (value === null || value === undefined) return null;
    if (typeof value === 'string' && value.trim()) return value.trim();
    bad(key, value, null);
    return null;
  };

  let matrixRaw: unknown = has('matrix') ? block.matrix : DEFAULTS.matrix;
  if (typeof matrixRaw === 'string') matrixRaw = [matrixRaw];
  if (!Array.isArray(matrixRaw)) {
    bad('matrix', matrixRaw, DEFAULTS.matrix);
    matrixRaw = [...DEFAULTS.matrix];
  }
  const matrix: string[] = [];
  for (const entry of matrixRaw as unknown[]) {
    const slug = projectSlug(entry);
    if (!(KNOWN_PROJECTS as readonly string[]).includes(slug)) {
      warn(`[execution] unknown execution.matrix entry ${JSON.stringify(entry)} — ignored (known: ${KNOWN_PROJECTS.join(', ')})`);
    } else if (!matrix.includes(slug)) {
      matrix.push(slug);
    }
  }

  let attr: unknown = has('test_id_attribute') ? block.test_id_attribute : DEFAULTS.test_id_attribute;
  if (!(typeof attr === 'string' && ATTR_RE.test(attr.trim()))) {
    bad('test_id_attribute', attr, DEFAULTS.test_id_attribute);
    attr = DEFAULTS.test_id_attribute;
  }

  const tg = isMapping(project.test_generation) ? project.test_generation : {};
  const profile = tg.profile ? String(tg.profile).trim().toLowerCase() : null;

  const cfg: Omit<ExecutionConfig, 'projects'> = {
    matrix,
    test_id_attribute: (attr as string).trim(),
    locale: optStr('locale'),
    timezone_id: optStr('timezone_id'),
    trace: enumOf('trace', TRACE_MODES),
    video: enumOf('video', VIDEO_MODES),
    screenshot: enumOf('screenshot', SCREENSHOT_MODES),
    junit: bool('junit'),
    mta_reporter: bool('mta_reporter'),
    role_auth: bool('role_auth'),
    role_auth_max_age_minutes: int('role_auth_max_age_minutes', 0, 100_000),
    suite_mode: enumOf('suite_mode', SUITE_MODES),
    shards: int('shards', 1, 64),
    max_parallel_shards: int('max_parallel_shards', 1, 16),
    retries: autoInt('retries', 0, 5),
    fail_on_flaky_tests: autoBool('fail_on_flaky_tests'),
    data_isolation: bool('data_isolation'),
    console_guard: enumOf('console_guard', CONSOLE_GUARD_MODES),
    network: enumOf('network', NETWORK_MODES),
    cleanup_failure: enumOf('cleanup_failure', CLEANUP_FAILURE_MODES),
    test_steps: bool('test_steps'),
    module_roles: bool('module_roles'),
  };
  return { ...cfg, projects: resolveProjects(matrix, profile, warn) };
}
