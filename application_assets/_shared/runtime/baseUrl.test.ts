import { describe, expect, it } from 'vitest';
import { resolveBaseUrl, scanProjectYaml } from './baseUrl';

const MODULAR = `
project:
  name: shop
  application_name: Shop   # url: in a comment must not count
auth:
  enabled: true
  setup_url: https://idp.example.com/login
  wait_for_url: https://shop.example.com/dash
modules:
  - id: M01
    name: Login
    url: https://shop.example.com/login
    setup:
      - goto: https://shop.example.com/
  - id: M02
    url: "https://shop.example.com/cart"
`;

describe('scanProjectYaml', () => {
  it('reads module urls but not setup_url / wait_for_url / goto', () => {
    expect(scanProjectYaml(MODULAR)).toEqual({
      projectUrl: null,
      moduleUrls: ['https://shop.example.com/login', 'https://shop.example.com/cart'],
    });
  });

  it('reads project.url and inline "- url:" items', () => {
    const yaml = 'project:\n  url: https://p.test\nmodules:\n  - url: https://m.test\n    id: M01\n';
    expect(scanProjectYaml(yaml)).toEqual({ projectUrl: 'https://p.test', moduleUrls: ['https://m.test'] });
  });
});

describe('resolveBaseUrl — no localhost default', () => {
  const none = () => null;

  it('prefers BASE_URL', () => {
    expect(resolveBaseUrl({ BASE_URL: 'https://x.test' }, none)).toBe('https://x.test');
  });

  it('uses project.url, then the single distinct module url', () => {
    expect(resolveBaseUrl({ PW_PROJECT: 'p' }, () => 'project:\n  url: https://p.test\n')).toBe('https://p.test');
    const one = 'modules:\n  - id: A\n    url: https://one.test\n  - id: B\n    url: https://one.test\n';
    expect(resolveBaseUrl({ PW_PROJECT: 'p' }, () => one)).toBe('https://one.test');
  });

  it('throws when several module urls are ambiguous', () => {
    expect(() => resolveBaseUrl({ PW_PROJECT: 'shop' }, () => MODULAR)).toThrow(/ambiguous/);
  });

  it('throws when nothing resolves — never localhost:3000', () => {
    expect(() => resolveBaseUrl({}, none)).toThrow(/unresolved/);
    expect(() => resolveBaseUrl({ PW_PROJECT: 'missing' }, none)).toThrow(/unresolved/);
    expect(() => resolveBaseUrl({ PW_PROJECT: 'p' }, () => 'project:\n  name: p\n')).toThrow(/unresolved/);
  });
});
