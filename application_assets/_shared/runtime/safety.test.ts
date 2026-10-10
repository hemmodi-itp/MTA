import { describe, expect, it, vi } from 'vitest';
import { ActionEngine } from './ActionEngine';
import { assertUrlAllowed, isUrlAllowed, parseAllowedHosts, SafetyError } from './safety';

describe('parseAllowedHosts', () => {
  it('distinguishes unset (not enforced) from an empty list (nothing allowed)', () => {
    expect(parseAllowedHosts(undefined)).toBeNull();
    expect(parseAllowedHosts('')).toEqual([]);
    expect(parseAllowedHosts(' A.com , b.com:81 ,')).toEqual(['a.com', 'b.com:81']);
  });
});

describe('isUrlAllowed — mirrors tools/safety/hosts.py', () => {
  const allowed = ['app.test', '127.0.0.1:8765', '*.cdn.test'];
  it.each([
    ['https://app.test/x', true],
    ['https://APP.test/x', true],
    ['https://evil.test/', false],
    ['https://app.test.evil.net/', false],
    ['http://127.0.0.1:8765/p', true],
    ['http://127.0.0.1:9999/p', false],
    ['https://img.cdn.test/a.png', true],
    ['https://cdn.test/', false],
    ['/relative', true],
    ['', true],
    ['about:blank', true],
    ['javascript:alert(1)', false],
    ['file:///etc/passwd', false],
  ])('%s -> %s', (url, expected) => {
    expect(isUrlAllowed(url, allowed)).toBe(expected);
  });

  it('enforces nothing when the allow-list is null', () => {
    expect(isUrlAllowed('https://anything.test', null)).toBe(true);
  });

  it('resolves relative urls against a base when given', () => {
    expect(isUrlAllowed('/x', ['app.test'], 'https://other.test/')).toBe(false);
  });

  it('assertUrlAllowed throws a SafetyError', () => {
    expect(() => assertUrlAllowed('https://evil.test', ['app.test'])).toThrow(SafetyError);
  });
});

describe('ActionEngine safety rails', () => {
  function engine(allowedHosts: string[] | null, violations: string[] = []) {
    const goto = vi.fn().mockResolvedValue(undefined);
    const page = { goto, waitForLoadState: vi.fn().mockResolvedValue(undefined) } as any;
    return { goto, engine: new ActionEngine(page, {}, [], { allowedHosts, violations }) };
  }

  it('navigate to a host outside the allow-list fails the step without navigating', async () => {
    const { goto, engine: e } = engine(['app.test']);
    await expect(e.navigate('https://evil.test/')).rejects.toThrow(/outside safety.allowed_hosts/);
    expect(goto).not.toHaveBeenCalled();
  });

  it('navigate inside the allow-list (or relative) proceeds', async () => {
    const { goto, engine: e } = engine(['app.test']);
    await e.navigate('https://app.test/home');
    await e.navigate('/cart');
    await e.navigate();
    expect(goto).toHaveBeenCalledTimes(3);
  });

  it('a recorded top-level violation fails the next action', async () => {
    const { goto, engine: e } = engine(['app.test'], ['https://evil.test/landing']);
    await expect(e.navigate('/home')).rejects.toThrow(/page left safety.allowed_hosts/);
    expect(goto).not.toHaveBeenCalled();
  });

  it('nothing is enforced when MTA_ALLOWED_HOSTS is not configured', async () => {
    const { goto, engine: e } = engine(null);
    await e.navigate('https://anywhere.test/');
    expect(goto).toHaveBeenCalledOnce();
  });
});
