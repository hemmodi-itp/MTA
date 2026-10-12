// destructive.ts — run-time destructive-action guard (Phase 4.4 `safety` fixture), TypeScript side.
//
// A port of tools/safety/action_classifier.py::classify_step that reads the SAME rule file,
// tools/safety/destructive_rules.yaml. Both classifiers are tested against tests/fixtures/destructive_cases.json,
// so they can't drift. ActionEngine classifies every interaction action (click, doubleClick, pressKey Enter,
// check/uncheck, select, dragAndDrop) by locator key + locator_map entry, and `navigate` by URL pattern.
//
// Policy (tools/safety/policy.py): destructive actions run only when safety.allow_destructive is true AND the
// environment is local/dev/staging. UIExecutionAgent passes the verdict as MTA_DESTRUCTIVE_ALLOWED=0|1
// (+ MTA_SAFETY_ENVIRONMENT). A hand run derives it from PW_PROJECT's project.yaml; with no project at all the
// guard is not enforced and one warning is printed.

import fs from 'fs';
import path from 'path';
import { parse } from 'yaml';

export interface Verdict {
  destructive: boolean;
  category: string | null;
  rule: string | null;
  text: string;
}

export interface Rules {
  phrases: Array<[string, string, RegExp]>;
  safe: RegExp[];
  urls: RegExp[];
}

export interface PlanStep {
  action: string;
  locator_key?: string | null;
  target_locator_key?: string | null;
  value?: unknown;
}

export interface LocatorEntryLike {
  type?: string;
  locator?: string;
  name?: string;
}

export const INTERACTION_ACTIONS = new Set([
  'click', 'doubleClick', 'pressKey', 'checkCheckbox', 'uncheckCheckbox',
  'selectDropdownByText', 'selectDropdownByValue', 'dragAndDrop',
]);
export const NAVIGATION_ACTIONS = new Set(['navigate']);

export const RULES_PATH = path.join('tools', 'safety', 'destructive_rules.yaml');

const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

function phraseRegex(phrase: string): RegExp {
  return new RegExp('\\b' + phrase.toLowerCase().split(/\s+/).filter(Boolean).map(esc).join('\\s+') + '\\b');
}

export function parseRules(text: string): Rules {
  const data = (parse(text) ?? {}) as Record<string, any>;
  const rules: Rules = { phrases: [], safe: [], urls: [] };
  for (const [category, phrases] of Object.entries(data.destructive ?? {})) {
    for (const phrase of (phrases as string[]) ?? []) rules.phrases.push([category, phrase, phraseRegex(phrase)]);
  }
  // longest phrases first (Python: sort by -len, stable)
  rules.phrases.sort((a, b) => b[1].length - a[1].length);
  rules.safe = ((data.safe as string[]) ?? []).map(phraseRegex);
  rules.urls = ((data.url_patterns as string[]) ?? []).map((p) => new RegExp(p, 'i'));
  return rules;
}

const cache = new Map<string, Rules | null>();

/** Rules from destructive_rules.yaml (relative to cwd = repo root), or null when the file is missing. */
export function loadRules(file: string = path.resolve(process.cwd(), RULES_PATH)): Rules | null {
  if (!cache.has(file)) {
    cache.set(file, fs.existsSync(file) ? parseRules(fs.readFileSync(file, 'utf8')) : null);
  }
  return cache.get(file) ?? null;
}

/** 'deleteAccountBtn' / 'delete-account' / '#delete_account' -> 'delete account btn'. */
export function wordsOf(identifier: string | null | undefined): string {
  if (!identifier) return '';
  const text = String(identifier).replace(/(?<=[a-z0-9])(?=[A-Z])/g, ' ');
  return text.replace(/[^A-Za-z0-9]+/g, ' ').trim().toLowerCase();
}

const normalize = (text: string) => (text || '').toLowerCase().replace(/\s+/g, ' ').trim();
const verdict = (destructive: boolean, text = '', category: string | null = null, rule: string | null = null): Verdict =>
  ({ destructive, category, rule, text });

export function classifyText(text: string, rules: Rules): Verdict {
  const norm = normalize(text);
  if (!norm) return verdict(false, norm);
  for (const safe of rules.safe) if (safe.test(norm)) return verdict(false, norm, null, `safe:${safe.source}`);
  for (const [category, phrase, rx] of rules.phrases) {
    if (rx.test(norm)) return verdict(true, norm, category, `phrase:${phrase}`);
  }
  return verdict(false, norm);
}

export function classifyUrl(url: unknown, rules: Rules): Verdict {
  if (!url) return verdict(false);
  for (const rx of rules.urls) if (rx.test(String(url))) return verdict(true, String(url), 'url', `url:${rx.source}`);
  return verdict(false, String(url));
}

function entryText(key: string | null | undefined, entry: LocatorEntryLike | null | undefined): [string, string[]] {
  const e = entry ?? {};
  const loc = e.locator ?? '';
  const extra = [key ?? ''];
  let name = '';
  if (e.type === 'role') name = e.name ?? '';
  else if (e.type === 'text' || e.type === 'label' || e.type === 'placeholder') name = loc;
  else if (e.type === 'testid' || e.type === 'css' || e.type === 'xpath') extra.push(loc);
  return [name, extra];
}

/** Same verdict as action_classifier.classify_step for an action-library step. */
export function classifyStep(step: PlanStep, entryOf: (key: string) => LocatorEntryLike | null | undefined, rules: Rules): Verdict {
  const action = step.action || '';
  if (NAVIGATION_ACTIONS.has(action)) return classifyUrl(step.value, rules);
  if (!INTERACTION_ACTIONS.has(action)) return verdict(false);
  if (action === 'pressKey' && !['enter', 'numpadenter'].includes(String(step.value ?? '').toLowerCase())) return verdict(false);
  let key = step.locator_key ?? null;
  if (action === 'dragAndDrop') key = step.target_locator_key || key;
  let [name, extra] = entryText(key, key ? entryOf(key) : null);
  if (action === 'selectDropdownByText' || action === 'selectDropdownByValue') {
    name = `${name} ${step.value ?? ''}`.trim();
  }
  const parts = [name, ...extra.filter(Boolean).map(wordsOf)].filter(Boolean);
  return classifyText(parts.join(' '), rules);
}

// ── policy ────────────────────────────────────────────────────────────────────

export interface DestructivePolicy {
  enforced: boolean;
  allowed: boolean;
  environment: string;
  source: 'env' | 'project.yaml' | 'none';
}

const ENVIRONMENTS = ['local', 'dev', 'staging', 'prod'];
const NON_PROD = new Set(['local', 'dev', 'staging']);
const ALIASES: Record<string, string> = {
  production: 'prod', live: 'prod', development: 'dev', develop: 'dev', stage: 'staging', localhost: 'local',
};

export function normalizeEnvironment(value: unknown): string {
  if (value === null || value === undefined) return 'unspecified';
  let text = String(value).trim().toLowerCase();
  text = ALIASES[text] ?? text;
  return ENVIRONMENTS.includes(text) ? text : 'unspecified';
}

function asBool(value: unknown): boolean {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') return ['1', 'true', 'yes', 'on'].includes(value.trim().toLowerCase());
  return !!value;
}

export function destructivePolicy(env: Record<string, string | undefined>, project: Record<string, any> | null): DestructivePolicy {
  const flag = env.MTA_DESTRUCTIVE_ALLOWED;
  if (flag === '0' || flag === '1') {
    return { enforced: true, allowed: flag === '1', environment: env.MTA_SAFETY_ENVIRONMENT || 'unspecified', source: 'env' };
  }
  if (project) {
    const environment = normalizeEnvironment(project.environment);
    const allow = asBool(project.safety?.allow_destructive ?? false);
    return { enforced: true, allowed: allow && NON_PROD.has(environment), environment, source: 'project.yaml' };
  }
  return { enforced: false, allowed: true, environment: 'unspecified', source: 'none' };
}

export function refusalMessage(step: PlanStep, v: Verdict, policy: DestructivePolicy): string {
  const target = step.action === 'navigate' ? String(step.value ?? '') : (step.locator_key ?? '');
  return `destructive action refused: ${step.action} '${target}' (${v.category}: ${v.rule}) — ` +
    `needs safety.allow_destructive: true and environment local/dev/staging (environment=${policy.environment})`;
}
