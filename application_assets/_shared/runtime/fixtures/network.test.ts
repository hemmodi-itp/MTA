import { describe, expect, it } from 'vitest';
import { buildHar, NetworkLog, redactHeaders, redactPostData, redactUrl, REDACTED, shouldAttachHar } from './network';

function req(method: string, url: string, headers: Record<string, string> = {}, post: string | null = null, type = 'document') {
  return { method: () => method, url: () => url, resourceType: () => type, headers: () => headers, postData: () => post, failure: () => null };
}

describe('network log', () => {
  it('records requests, responses, timing and failures; filters', () => {
    let t = 1000;
    const log = new NetworkLog(() => t);
    const login = req('POST', 'http://127.0.0.1:8765/login', { 'content-type': 'application/x-www-form-urlencoded' }, 'username=alice&password=alice-pass-1');
    const css = req('GET', 'http://127.0.0.1:8765/app.css', {}, null, 'stylesheet');
    log.onRequest(login);
    log.onRequest(css);
    t = 1040;
    log.onResponse({ request: () => login, status: () => 303, statusText: () => 'See Other', headers: () => ({ location: '/products', 'set-cookie': 'sid=abc' }) });
    log.onFinished(login);
    log.onFailed(req('GET', 'http://unknown/') as any);   // a request the log never saw: ignored
    log.onFailed(css as any);                              // failure() returns null -> recorded as 'failed'
    expect(log.requests({ method: 'post' })).toHaveLength(1);
    expect(log.responses()).toHaveLength(1);
    const entry = log.last('/login')!;
    expect(entry.status).toBe(303);
    expect(entry.duration_ms).toBe(40);
    expect(log.entries({ resourceType: 'stylesheet' })[0].failure).toBe('failed');
    expect(log.entries({ url: /\.css$/ })).toHaveLength(1);
  });
});

describe('redaction', () => {
  it('credential headers', () => {
    expect(redactHeaders({ Cookie: 'sid=1', Authorization: 'Bearer x', accept: 'text/html' }))
      .toEqual({ Cookie: REDACTED, Authorization: REDACTED, accept: 'text/html' });
  });
  it('form, JSON, multipart and query fields with secret-looking names', () => {
    expect(redactPostData('username=alice&password=alice-pass-1', 'application/x-www-form-urlencoded'))
      .toBe(`username=alice&password=${encodeURIComponent(REDACTED)}`);
    expect(JSON.parse(redactPostData('{"user":"a","creds":{"apiToken":"t","n":1}}', 'application/json')!))
      .toEqual({ user: 'a', creds: { apiToken: REDACTED, n: 1 } });
    expect(redactPostData('not json', 'application/json')).toBe(REDACTED);
    expect(redactPostData('--b\r\nContent-Disposition: form-data; name="password"\r\n\r\nhunter2\r\n--b--', 'multipart/form-data; boundary=b'))
      .not.toContain('hunter2');
    expect(redactUrl('http://h/cb?code=1&access_token=abc')).toContain(`access_token=${encodeURIComponent(REDACTED)}`);
    expect(redactUrl('http://h/products?q=pen')).toBe('http://h/products?q=pen');
  });
});

describe('HAR', () => {
  it('is HAR 1.2, redacted, without response bodies', () => {
    const log = new NetworkLog(() => 5);
    const r = req('POST', 'http://h/login?token=zzz', { 'content-type': 'application/x-www-form-urlencoded', cookie: 'sid=1' }, 'password=secret1');
    log.onRequest(r);
    log.onResponse({ request: () => r, status: () => 200, statusText: () => 'OK', headers: () => ({ 'set-cookie': 'sid=2', 'content-type': 'text/html' }) });
    const har = log.har() as any;
    expect(har.log.version).toBe('1.2');
    const text = JSON.stringify(har);
    for (const secret of ['secret1', 'sid=1', 'sid=2', 'zzz']) expect(text).not.toContain(secret);
    const e = har.log.entries[0];
    expect(e.request.method).toBe('POST');
    expect(e.response.status).toBe(200);
    expect(e.response.content).toEqual({ size: -1, mimeType: 'text/html' });
    expect(buildHar([]).log).toMatchObject({ entries: [] });
  });

  it('attach policy: on-failure only when failed, on always, off never', () => {
    expect(shouldAttachHar('on-failure', true)).toBe(true);
    expect(shouldAttachHar('on-failure', false)).toBe(false);
    expect(shouldAttachHar('on', false)).toBe(true);
    expect(shouldAttachHar('off', true)).toBe(false);
  });
});
