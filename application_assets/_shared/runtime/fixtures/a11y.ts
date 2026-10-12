// a11y.ts — the `a11y` fixture: wiring for @axe-core/playwright's AxeBuilder (Phase 4.4).
//
// TODO(Phase 7.1): WCAG 2.2 AA checks, severity mapping and a baseline of accepted issues. Until then this only
// runs AxeBuilder when the package is installed and attaches the raw results — no assertions. The dependency is
// deliberately not added yet: nothing in Phase 4 checks accessibility.

export const AXE_PACKAGE = '@axe-core/playwright';
export const DEFAULT_TAGS = ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'];

export type ModuleLoader = (name: string) => any;

// eslint-disable-next-line @typescript-eslint/no-var-requires
const defaultLoader: ModuleLoader = (name) => require(name);

export class A11yUnavailableError extends Error {
  constructor() {
    super(`a11y: ${AXE_PACKAGE} is not installed — accessibility checks arrive with Phase 7; ` +
      `run \`npm i -D ${AXE_PACKAGE}\` to use AxeBuilder now`);
    this.name = 'A11yUnavailableError';
  }
}

export interface A11yScanOptions {
  tags?: string[];
  include?: string;
  exclude?: string;
}

/** AxeBuilder(page).withTags(tags)[.include][.exclude].analyze(), or A11yUnavailableError. */
export async function axeScan(page: unknown, opts: A11yScanOptions = {}, load: ModuleLoader = defaultLoader): Promise<any> {
  let mod: any;
  try {
    mod = load(AXE_PACKAGE);
  } catch {
    throw new A11yUnavailableError();
  }
  const AxeBuilder = mod?.default ?? mod?.AxeBuilder ?? mod;
  let builder = new AxeBuilder({ page }).withTags(opts.tags ?? DEFAULT_TAGS);
  if (opts.include) builder = builder.include(opts.include);
  if (opts.exclude) builder = builder.exclude(opts.exclude);
  return builder.analyze();
}
