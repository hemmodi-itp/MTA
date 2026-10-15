import { describe, expect, it, vi } from 'vitest';
import { ActionEngine, jsonAtPath, OracleSources, statusMatches } from './ActionEngine';
import { NetworkLog } from './fixtures/network';
import { validateSchema } from './fixtures/jsonSchema';

// Phase 5 oracle actions against fake Playwright objects (the real-browser checks are in
// tests/integration/test_phase5_oracles_e2e.py).

const SAFE = { allowedHosts: null, violations: [] };

function engine(page: any = {}, pageObject: Record<string, any> = {}, oracles: OracleSources = {}) {
  return new ActionEngine(page, pageObject, [], SAFE, oracles);
}

function req(method: string, url: string, postData: string | null = null) {
  return {
    method: () => method, url: () => url, resourceType: () => 'fetch', headers: () => ({}),
    postData: () => postData, failure: () => null,
  };
}

function res(r: ReturnType<typeof req>, status: number, body?: string) {
  return {
    request: () => r, status: () => status, statusText: () => '', text: async () => body ?? '',
    headers: () => (body !== undefined ? { 'content-type': 'application/json' } : {}),
  };
}

function logWith(...calls: Array<[string, string, number | null, string | null, string?]>): NetworkLog {
  const log = new NetworkLog();
  for (const [method, url, status, post, body] of calls) {
    const r = req(method, url, post);
    log.onRequest(r);
    if (status !== null) log.onResponse(res(r, status, body));
  }
  return log;
}

describe('statusMatches / jsonAtPath', () => {
  it('matches exact numbers and Nxx classes', () => {
    expect(statusMatches(201, 201)).toBe(true);
    expect(statusMatches(201, '2xx')).toBe(true);
    expect(statusMatches(302, '2xx')).toBe(false);
    expect(statusMatches(null, '2xx')).toBe(false);
    expect(statusMatches(404, '404')).toBe(true);
  });

  it('reads dot paths with array indexes', () => {
    expect(jsonAtPath({ items: [{ name: 'Lamp' }] }, 'items.0.name')).toBe('Lamp');
    expect(jsonAtPath({ items: [] }, 'items.3.name')).toBeUndefined();
  });
});

describe('verifyRequest (Phase 5 complete: 2xx + bodyContains)', () => {
  it('passes on a 2xx class and a matching request body', async () => {
    const network = logWith(['POST', 'http://a/products', 303, 'name=Lamp&price=3']);
    await engine({}, {}, { network }).verifyRequest('POST', '/products', '3xx', undefined, 'name=Lamp');
  });

  it('"success" accepts 2xx and 3xx, never 4xx', async () => {
    await engine({}, {}, { network: logWith(['POST', 'http://a/login', 303, 'u=a']) }).verifyRequest('POST', '/login', 'success');
    await engine({}, {}, { network: logWith(['POST', 'http://a/login', 200, 'u=a']) }).verifyRequest('POST', '/login', 'success');
    await expect(engine({}, {}, { network: logWith(['POST', 'http://a/login', 401, 'u=a']) })
      .verifyRequest('POST', '/login', 'success')).rejects.toThrow(/status success/);
  }, 10_000);

  it('fails when the body does not contain the text', async () => {
    const network = logWith(['POST', 'http://a/products', 201, 'name=Desk']);
    await expect(engine({}, {}, { network }).verifyRequest('POST', '/products', '2xx', undefined, 'Lamp'))
      .rejects.toThrow(/body contains 'Lamp'/);
  }, 10_000);
});

describe('validateSchema', () => {
  const schema = {
    type: 'object', required: ['items'], additionalProperties: false,
    properties: { items: { type: 'array', items: { type: 'object', required: ['id'], properties: { id: { type: 'integer' } } } } },
  };
  it('accepts a matching document and reports each violation', () => {
    expect(validateSchema({ items: [{ id: 1 }] }, schema)).toEqual([]);
    const errs = validateSchema({ items: [{ id: 'x' }, {}], extra: 1 }, schema);
    expect(errs).toContain('$.items[0].id: expected integer, got string');
    expect(errs).toContain("$.items[1]: missing required 'id'");
    expect(errs).toContain("$: unexpected property 'extra'");
  });
  it('checks enum, ranges and string rules', () => {
    expect(validateSchema(5, { type: 'number', minimum: 6 })).toHaveLength(1);
    expect(validateSchema('b', { enum: ['a'] })).toHaveLength(1);
    expect(validateSchema('abc', { type: 'string', maxLength: 2, pattern: '^a' })).toEqual(['$: longer than 2']);
  });
});

describe('verifyResponseSchema', () => {
  it('validates every captured JSON body matching the pattern', async () => {
    const network = logWith(['GET', 'http://a/api/products', 200, null, '{"items":[{"id":1}]}']);
    await engine({}, {}, { network }).verifyResponseSchema('/api/products', { type: 'object', required: ['items'] });
  });

  it('fails with the violating path', async () => {
    const network = logWith(['GET', 'http://a/api/products', 200, null, '{"items":"nope"}']);
    await expect(engine({}, {}, { network })
      .verifyResponseSchema('/api/products', { type: 'object', properties: { items: { type: 'array' } } }))
      .rejects.toThrow(/items: expected array/);
  });

  it('loads a schemaRef relative to the project dir', async () => {
    const fs = await import('fs');
    const os = await import('os');
    const path = await import('path');
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'mta-schema-'));
    fs.writeFileSync(path.join(dir, 'p.json'), JSON.stringify({ type: 'object', required: ['id'] }));
    const network = logWith(['GET', 'http://a/api/p/1', 200, null, '{"name":"x"}']);
    await expect(engine({}, {}, { network, projectDir: dir }).verifyResponseSchema('/api/p/', 'p.json'))
      .rejects.toThrow(/missing required 'id'/);
  });
});

describe('verifyApiState', () => {
  function api(status: number, body: string) {
    return { fetch: vi.fn().mockResolvedValue({ status: () => status, text: async () => body }) } as any;
  }

  it('checks status, body text and a JSON path', async () => {
    const a = api(200, '{"items":[{"name":"Lamp"}]}');
    await engine({}, {}, { api: a }).verifyApiState('GET', '/api/products',
      { status: '2xx', bodyContains: 'Lamp', path: 'items', length: 1 });
    await engine({}, {}, { api: a }).verifyApiState('GET', '/api/products', { path: 'items.0.name', equals: 'Lamp' });
    expect(a.fetch).toHaveBeenCalledWith('/api/products', { method: 'GET', failOnStatusCode: false });
  });

  it('fails on the wrong status (e.g. a deleted product still found)', async () => {
    await expect(engine({}, {}, { api: api(200, '{}') }).verifyApiState('GET', '/api/products/7', { status: 404 }))
      .rejects.toThrow(/returned 200, expected 404/);
  });

  it('needs the api fixture', async () => {
    await expect(engine().verifyApiState('GET', '/x', {})).rejects.toThrow(/api oracle unavailable/);
  });
});

describe('rememberCount / verifyCountChangedBy', () => {
  it('compares against the remembered baseline', async () => {
    let n = 3;
    const rows = { count: vi.fn(async () => n) };
    const ae = engine({}, { rows });
    await ae.rememberCount('rows');
    n = 4;
    await ae.verifyCountChangedBy('rows', 1);
    await expect(ae.verifyCountChangedBy('rows', 0)).rejects.toThrow(/change by 0 \(from 3\)/);
  }, 15_000);

  it('refuses without a baseline', async () => {
    await expect(engine({}, { rows: { count: async () => 1 } }).verifyCountChangedBy('rows', 1))
      .rejects.toThrow(/needs an earlier rememberCount/);
  });
});

describe('verifyStorage', () => {
  const cookies = [{ name: 'sid', value: 'abc', httpOnly: true, secure: false, sameSite: 'Lax' }];
  const page = (store: Record<string, string | null> = {}) => ({
    context: () => ({ cookies: async () => cookies }),
    evaluate: async (_fn: unknown, [key]: [string, string]) => store[key] ?? null,
  });

  it('checks cookie flags', async () => {
    const ae = engine(page());
    await ae.verifyStorage('cookie', 'sid', 'httpOnly');
    await ae.verifyStorage('cookie', 'sid', 'sameSite');
    await ae.verifyStorage('cookie', 'other', 'absent');
    await expect(ae.verifyStorage('cookie', 'sid', 'secure')).rejects.toThrow(/secure/);
  });

  it('checks local/session storage values', async () => {
    const ae = engine(page({ cart: '[7]' }));
    await ae.verifyStorage('localStorage', 'cart', 'contains', '7');
    await expect(ae.verifyStorage('sessionStorage', 'token', 'present')).rejects.toThrow();
    await expect(ae.verifyStorage('localStorage', 'cart', 'httpOnly')).rejects.toThrow(/cookies only/);
  });
});

describe('verifyValidationMessage', () => {
  it('passes on the native message, case-insensitive', async () => {
    const name = { evaluate: vi.fn().mockResolvedValue(['Please fill out this field.']) };
    await engine({}, { name }).verifyValidationMessage('name', 'fill out');
  });

  it('fails listing what it found', async () => {
    const name = { evaluate: vi.fn().mockResolvedValue([]) };
    await expect(engine({}, { name }).verifyValidationMessage('name', 'required')).rejects.toThrow(/found \[\]/);
  }, 15_000);
});

describe('verifyDownload / verifyNewTab', () => {
  it('clicks and checks the download name and size', async () => {
    const fs = await import('fs');
    const os = await import('os');
    const path = await import('path');
    const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'mta-dl-')), 'f');
    fs.writeFileSync(file, 'a,b\n1,2\n');
    const download = { suggestedFilename: () => 'products.csv', path: async () => file };
    const page = { waitForEvent: vi.fn().mockResolvedValue(download) };
    const exportBtn = { click: vi.fn().mockResolvedValue(undefined) };
    await engine(page, { export: exportBtn }).verifyDownload('export', '\\.csv$', 5);
    expect(exportBtn.click).toHaveBeenCalled();
    await expect(engine(page, { export: exportBtn }).verifyDownload('export', '\\.pdf$')).rejects.toThrow(/should match/);
    await expect(engine(page, { export: exportBtn }).verifyDownload('export', undefined, 1000)).rejects.toThrow(/at least 1000/);
  });

  it('closes the new tab even when the URL check fails', async () => {
    const popup = { waitForLoadState: vi.fn().mockResolvedValue(undefined), close: vi.fn().mockResolvedValue(undefined),
                    url: () => 'http://a/elsewhere' };
    const page = { context: () => ({ waitForEvent: vi.fn().mockResolvedValue(popup) }) };
    const link = { click: vi.fn().mockResolvedValue(undefined) };
    await expect(engine(page, { link }).verifyNewTab('link', '/help')).rejects.toThrow();
    expect(popup.close).toHaveBeenCalled();
  }, 15_000);
});

describe('fault injection', () => {
  it('mockRoute fulfils matching requests with the given status and JSON body', async () => {
    let handler: any;
    const page = { route: vi.fn(async (_re: RegExp, h: any) => { handler = h; }) };
    await engine(page).mockRoute('/api/*', { status: 500, body: { error: 'boom' } });
    const [re] = page.route.mock.calls[0];
    expect((re as RegExp).test('http://a/api/products')).toBe(true);
    const route = { fulfill: vi.fn(), continue: vi.fn() };
    await handler(route);
    expect(route.fulfill).toHaveBeenCalledWith({ status: 500, body: '{"error":"boom"}', contentType: 'application/json' });
  });

  it('mockRoute with only a delay lets the request through', async () => {
    let handler: any;
    const page = { route: vi.fn(async (_re: RegExp, h: any) => { handler = h; }) };
    await engine(page).mockRoute('/slow', { delayMs: 5 });
    const route = { fulfill: vi.fn(), continue: vi.fn() };
    await handler(route);
    expect(route.continue).toHaveBeenCalled();
    expect(route.fulfill).not.toHaveBeenCalled();
  });

  it('setOffline and setClock delegate; a bad date is refused', async () => {
    const ctx = { setOffline: vi.fn() };
    const page = { context: () => ctx, clock: { setFixedTime: vi.fn() } };
    await engine(page).setOffline(true);
    expect(ctx.setOffline).toHaveBeenCalledWith(true);
    await engine(page).setClock('2030-01-01T00:00:00Z');
    expect(page.clock.setFixedTime).toHaveBeenCalledWith(new Date('2030-01-01T00:00:00Z'));
    await expect(engine(page).setClock('not a date')).rejects.toThrow(/not a valid date/);
  });
});

describe('identity probe on a missing element (Phase 6.1)', () => {
  it('builds a syntactically valid in-page expression from fingerprint.js', async () => {
    const fs = await import('fs');
    const path = await import('path');
    const { probeExpression } = await import('./ActionEngine');
    const src = fs.readFileSync(path.join(__dirname, 'fixtures', 'fingerprint.js'), 'utf8');
    const expr = probeExpression(src, { role: 'button', name: 'Save product', tag: 'button' });
    expect(() => new Function(`return ${expr.replace(/\(\)\s*$/, '')}`)).not.toThrow();
    expect(expr).toContain('replace(/\\s+/g');
  });

  it('records present / absent / no identity, and still throws the original error', async () => {
    const missing = {
      getAttribute: vi.fn().mockResolvedValue(null),
      click: vi.fn().mockRejectedValue(new Error("Timeout 5000ms exceeded. waiting for getByTestId('save')")),
    };
    const mk = (present: boolean | null, fp?: object) => new ActionEngine(
      { evaluate: vi.fn().mockResolvedValue(present) } as any, { save: missing }, [], SAFE,
      { entryOf: () => (fp ? { _fingerprint: fp } : {}) });
    const engines = [mk(true, { role: 'button', name: 'Save' }), mk(false, { role: 'button', name: 'Save' }), mk(null)];
    for (const e of engines) await expect(e.click('save')).rejects.toThrow(/locator_key=save/);
    expect(engines.map((e) => e.probes[0])).toEqual([
      'save: an element with the same identity is on the page — the locator drifted',
      'save: no element with this identity on the page',
      'save: no recorded identity',
    ]);
  });
});

describe('verifyNoNewConsoleErrors', () => {
  it('ignores 4xx resource lines (an expected rejection), fails on 5xx and JS errors', async () => {
    const mk = (entries: Array<{ kind: string; text: string }>) =>
      engine({}, {}, { consoleGuard: { newErrors: () => entries } as any });
    await mk([{ kind: 'console', text: 'Failed to load resource: the server responded with a status of 400 (Bad Request)' }])
      .verifyNoNewConsoleErrors();
    await expect(mk([{ kind: 'console', text: 'Failed to load resource: the server responded with a status of 500 ()' }])
      .verifyNoNewConsoleErrors()).rejects.toThrow(/No new console errors/);
    await expect(mk([{ kind: 'pageerror', text: 'TypeError: x is undefined' }]).verifyNoNewConsoleErrors()).rejects.toThrow();
  });
});
