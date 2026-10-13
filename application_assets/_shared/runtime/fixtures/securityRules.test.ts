import { describe, expect, it } from 'vitest';
import { checkCookies, checkHeaders, checkStorage, checkUrl } from './securityRules';

const good = {
  'Content-Security-Policy': "default-src 'self'", 'Strict-Transport-Security': 'max-age=63072000',
  'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY', 'Referrer-Policy': 'no-referrer',
};

describe('checkHeaders', () => {
  it('passes a hardened response', () => expect(checkHeaders(good, { https: true })).toEqual([]));
  it('flags every missing header; HSTS only over https', () => {
    expect(checkHeaders({}, { https: true }).map((f) => f.rule).sort())
      .toEqual(['csp', 'framing', 'hsts', 'referrer-policy', 'x-content-type-options']);
    expect(checkHeaders({}).map((f) => f.rule)).not.toContain('hsts');
  });
  it('accepts frame-ancestors in place of X-Frame-Options', () => {
    const { ['X-Frame-Options']: _x, ...h } = good;
    expect(checkHeaders({ ...h, 'content-security-policy': "frame-ancestors 'none'" }, { https: true })).toEqual([]);
  });
});

describe('checkCookies', () => {
  it('flags weak session cookies, ignores others', () => {
    const r = checkCookies([{ name: 'sessionid' }, { name: 'theme' }], { https: true }).map((f) => f.rule);
    expect(r).toEqual(['cookie-httponly', 'cookie-secure', 'cookie-samesite']);
  });
  it('passes a hardened cookie', () => {
    expect(checkCookies([{ name: 'sid', httpOnly: true, secure: true, sameSite: 'Lax' }], { https: true })).toEqual([]);
  });
});

describe('checkUrl / checkStorage', () => {
  it('flags tokens and PII in URLs', () => {
    expect(checkUrl('http://x/a?token=abcdef123456')).toHaveLength(1);
    expect(checkUrl('http://x/a?email=a@b.com')).toHaveLength(1);
    expect(checkUrl('http://x/products?page=2')).toEqual([]);
  });
  it('flags secrets in storage', () => {
    expect(checkStorage({ auth_token: 'abcdefgh12345', theme: 'dark' })).toHaveLength(1);
  });
});
