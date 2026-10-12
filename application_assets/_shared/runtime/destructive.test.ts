import fs from 'fs';
import path from 'path';
import { describe, expect, it } from 'vitest';

import { classifyStep, destructivePolicy, loadRules, normalizeEnvironment, wordsOf } from './destructive';
import { ActionEngine, RuntimeSafety } from './ActionEngine';

const SHARED = JSON.parse(fs.readFileSync(path.join(process.cwd(), 'tests', 'fixtures', 'destructive_cases.json'), 'utf8'));
const rules = loadRules()!;
const entryOf = (key: string) => SHARED.locator_map[key];

describe('classifyStep — shared cases with tools/safety/action_classifier.py', () => {
  it('reads tools/safety/destructive_rules.yaml', () => {
    expect(rules).not.toBeNull();
    expect(rules.phrases.length).toBeGreaterThan(10);
  });
  for (const c of SHARED.cases) {
    it(c.name, () => {
      const v = classifyStep(c.step, entryOf, rules);
      expect({ destructive: v.destructive, category: v.category }).toEqual({ destructive: c.destructive, category: c.category });
    });
  }
  it('wordsOf splits camelCase, kebab, snake and selectors', () => {
    expect(wordsOf('deleteAccountBtn')).toBe('delete account btn');
    expect(wordsOf('#delete_account')).toBe('delete account');
  });
});

describe('destructivePolicy', () => {
  it('env from UIExecutionAgent wins', () => {
    expect(destructivePolicy({ MTA_DESTRUCTIVE_ALLOWED: '0', MTA_SAFETY_ENVIRONMENT: 'prod' }, null))
      .toEqual({ enforced: true, allowed: false, environment: 'prod', source: 'env' });
    expect(destructivePolicy({ MTA_DESTRUCTIVE_ALLOWED: '1' }, { environment: 'prod' }).allowed).toBe(true);
  });
  it('project.yaml: allow_destructive AND a non-prod environment (policy.py rule)', () => {
    expect(destructivePolicy({}, { environment: 'local', safety: { allow_destructive: true } }).allowed).toBe(true);
    expect(destructivePolicy({}, { environment: 'production', safety: { allow_destructive: true } }).allowed).toBe(false);
    expect(destructivePolicy({}, { safety: { allow_destructive: 'yes' } }).allowed).toBe(false);   // unspecified env
    expect(destructivePolicy({}, { environment: 'dev' }).allowed).toBe(false);
  });
  it('no env and no project -> not enforced', () => {
    expect(destructivePolicy({}, null)).toMatchObject({ enforced: false, source: 'none' });
  });
  it('normalizes environment aliases like policy.py', () => {
    expect(normalizeEnvironment('Live')).toBe('prod');
    expect(normalizeEnvironment('stage')).toBe('staging');
    expect(normalizeEnvironment('qa')).toBe('unspecified');
    expect(normalizeEnvironment(undefined)).toBe('unspecified');
  });
});

describe('ActionEngine destructive guard', () => {
  function engine(allowed: boolean) {
    const clicked: string[] = [];
    const loc = (name: string) => ({ click: async () => clicked.push(name), getAttribute: async () => null });
    const pageObject: Record<string, any> = { delete_account_btn: loc('delete'), save_product_button: loc('save') };
    const safety: RuntimeSafety = {
      allowedHosts: null, violations: [],
      destructive: { policy: { enforced: true, allowed, environment: allowed ? 'local' : 'prod', source: 'env' }, rules, entryOf },
    };
    const page: any = { goto: async () => {}, waitForLoadState: async () => {}, context: () => ({}) };
    return { ae: new ActionEngine(page, pageObject, [], safety), clicked };
  }

  it('refuses a destructive click when the policy does not allow it, and never performs it', async () => {
    const { ae, clicked } = engine(false);
    await expect(ae.click('delete_account_btn')).rejects.toThrow(/destructive action refused: click 'delete_account_btn'/);
    expect(clicked).toEqual([]);
  });
  it('lets harmless clicks through', async () => {
    const { ae, clicked } = engine(false);
    await ae.click('save_product_button');
    expect(clicked).toEqual(['save']);
  });
  it('allows the destructive click when the policy allows it', async () => {
    const { ae, clicked } = engine(true);
    await ae.click('delete_account_btn');
    expect(clicked).toEqual(['delete']);
  });
  it('refuses a destructive navigate URL', async () => {
    const { ae } = engine(false);
    await expect(ae.navigate('/users/7/delete')).rejects.toThrow(/destructive action refused: navigate/);
  });
});
