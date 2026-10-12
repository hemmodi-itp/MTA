import fs from 'fs';
import path from 'path';
import { describe, expect, it } from 'vitest';

import { buildMergeConfig, buildPlaywrightConfig, buildReporters, projectNames } from './buildConfig';
import { resolveExecutionConfig } from './execution';
import { parseProjectYaml } from './projectYaml';

const CASES = JSON.parse(
  fs.readFileSync(path.join(process.cwd(), 'tests', 'fixtures', 'execution_config_cases.json'), 'utf8'),
) as Array<{ name: string; project: unknown; expected: Record<string, unknown> }>;

const REPORTER = '/abs/mta-reporter.ts';

function build(env: Record<string, string> = {}, project: any = null, exists = () => false) {
  return buildPlaywrightConfig({ env, project, baseURL: 'http://127.0.0.1:8765', mtaReporterPath: REPORTER, exists, warn: () => {} });
}

const reporterNames = (cfg: any) => (cfg.reporter as any[]).map((r) => r[0]);

describe('resolveExecutionConfig — shared cases with tools/execution/config.py', () => {
  for (const c of CASES) {
    it(c.name, () => {
      expect(resolveExecutionConfig(c.project, () => {})).toEqual(c.expected);
    });
  }

  it('warns once per invalid value', () => {
    const warnings: string[] = [];
    resolveExecutionConfig({ execution: { trace: 'always', shards: 0 } }, (m) => warnings.push(m));
    expect(warnings).toHaveLength(2);
    expect(warnings[0]).toContain('execution.trace');
  });
});

describe('buildPlaywrightConfig', () => {
  it('without an execution block keeps today\'s shape: chromium only, retries 0, no fullyParallel', () => {
    const cfg = build();
    expect((cfg.projects ?? []).map((p) => p.name)).toEqual(['chromium']);
    expect(cfg.retries).toBe(0);
    expect(cfg.fullyParallel).toBeUndefined();
    expect(cfg.testMatch).toBe('**/test_scripts/**/*.spec.ts');
    expect(cfg.use?.baseURL).toBe('http://127.0.0.1:8765');
    expect(cfg.timeout).toBe(60_000);
  });

  it('defaults: retain-on-failure evidence, data-testid, no locale/timezone', () => {
    const use = build().use!;
    expect(use.trace).toBe('retain-on-failure');
    expect(use.video).toBe('retain-on-failure');
    expect(use.screenshot).toBe('only-on-failure');
    expect(use.testIdAttribute).toBe('data-testid');
    expect('locale' in use).toBe(false);
    expect('timezoneId' in use).toBe(false);
  });

  it('matrix -> projects with device descriptors, chromium first', () => {
    const cfg = build({}, { execution: { matrix: ['iPhone 14', 'firefox', 'Pixel 7', 'webkit'] } });
    const projects = cfg.projects ?? [];
    expect(projects.map((p) => p.name)).toEqual(['chromium', 'firefox', 'webkit', 'pixel-7', 'iphone-14']);
    expect(projects[0].use?.defaultBrowserType).toBe('chromium');
    expect(projects[1].use?.defaultBrowserType).toBe('firefox');
    expect(projects[3].use?.isMobile).toBe(true);
    expect(projects[4].use?.defaultBrowserType).toBe('webkit');
    for (const p of projects) expect(p.name).toMatch(/^[\w-]+$/); // UIExecution's list-reporter regex
  });

  it('profile smoke -> chromium only', () => {
    const cfg = build({}, { execution: { matrix: ['firefox'] }, test_generation: { profile: 'smoke' } });
    expect((cfg.projects ?? []).map((p) => p.name)).toEqual(['chromium']);
  });

  it('MTA_PROJECTS overrides the matrix with an exact list of known projects', () => {
    const cfg = build({ MTA_PROJECTS: 'firefox,bogus' }, { execution: { matrix: ['chromium'] } });
    expect((cfg.projects ?? []).map((p) => p.name)).toEqual(['firefox']);
    expect(projectNames({ MTA_PROJECTS: '' }, resolveExecutionConfig({}, () => {}))).toEqual(['chromium']);
  });

  it('test id attribute, locale and timezone from the project', () => {
    const use = build({}, { execution: { test_id_attribute: 'data-test', locale: 'en-GB', timezone_id: 'Europe/London' } }).use!;
    expect(use.testIdAttribute).toBe('data-test');
    expect(use.locale).toBe('en-GB');
    expect(use.timezoneId).toBe('Europe/London');
  });

  it('storageState only when PW_STORAGE_STATE exists', () => {
    expect(build({ PW_STORAGE_STATE: '/x/auth.json' }).use?.storageState).toBeUndefined();
    expect(build({ PW_STORAGE_STATE: '/x/auth.json' }, null, () => true).use?.storageState).toBe('/x/auth.json');
  });

  it('forbidOnly and workers follow CI', () => {
    expect(build({ CI: '1' }).forbidOnly).toBe(true);
    expect(build({ CI: '1' }).workers).toBe(1);
    expect(build().forbidOnly).toBe(false);
    expect(build().workers).toBe(2);
  });

  it('testDir from PW_TEST_DIR', () => {
    expect(build({ PW_TEST_DIR: '/assets' }).testDir).toBe('/assets');
    expect(build().testDir).toBe('./application_assets');
  });
});

describe('reporters', () => {
  const exec = resolveExecutionConfig({}, () => {});

  it('list, json, html, junit and the MTA reporter by default, with env paths', () => {
    const r = buildReporters(
      { PW_JSON_REPORT: 'j.json', PW_HTML_REPORT: 'h', PW_JUNIT_REPORT: 'u.xml', MTA_RESULTS_FILE: 'm.json' },
      exec, REPORTER,
    ) as any[];
    expect(r.map((x) => x[0])).toEqual(['list', 'json', 'html', 'junit', REPORTER]);
    expect(r[1][1]).toEqual({ outputFile: 'j.json' });
    expect(r[2][1]).toEqual({ outputFolder: 'h', open: 'never' });
    expect(r[3][1]).toEqual({ outputFile: 'u.xml' });
    expect(r[4][1]).toEqual({ outputFile: 'm.json' });
  });

  it('junit and the MTA reporter can be switched off', () => {
    const cfg = build({}, { execution: { junit: false, mta_reporter: false } });
    expect(reporterNames(cfg)).toEqual(['list', 'json', 'html']);
  });

  it('PW_BLOB_DIR adds the blob reporter; MTA_BLOB_ONLY leaves only list + blob', () => {
    expect(reporterNames(build({ PW_BLOB_DIR: 'b' }))).toEqual(['list', 'json', 'html', 'junit', REPORTER, 'blob']);
    const shard = build({ PW_BLOB_DIR: 'b/shard-1', MTA_BLOB_ONLY: '1' });
    expect(shard.reporter).toEqual([['list'], ['blob', { outputDir: 'b/shard-1' }]]);
    expect(reporterNames(build({ MTA_BLOB_ONLY: '1' }))).toContain('json'); // no blob dir -> ignored
  });

  it('merge config: reporters only, no baseURL, junit/mta only when their path is set', () => {
    const m = buildMergeConfig({ PW_JSON_REPORT: 'j', PW_HTML_REPORT: 'h', PW_JUNIT_REPORT: 'u', MTA_RESULTS_FILE: 'm' }, REPORTER);
    expect(reporterNames(m)).toEqual(['list', 'json', 'html', 'junit', REPORTER]);
    expect(m.use).toBeUndefined();
    expect(reporterNames(buildMergeConfig({}, REPORTER))).toEqual(['list', 'json', 'html']);
  });
});

describe('parseProjectYaml', () => {
  it('parses a mapping, rejects junk', () => {
    expect(parseProjectYaml('execution:\n  matrix: [chromium, firefox]\n')).toEqual({ execution: { matrix: ['chromium', 'firefox'] } });
    expect(parseProjectYaml('- a\n- b\n')).toBeNull();
    expect(parseProjectYaml('a: [unclosed')).toBeNull();
    expect(parseProjectYaml(null)).toBeNull();
  });
});
