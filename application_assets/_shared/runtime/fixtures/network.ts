// network.ts — request/response log + redacted HAR evidence (Phase 4.4 `network` fixture).
//
// Recorded from context events (every page and popup of the test): method, URL, resource type, status, headers,
// request post data (<= 4 KB), timing, failure. Phase 5 oracles (verifyRequest / verifyNoRequest) query it.
// The HAR is built here, not with Playwright's recordHar: recordHar stores cookies, Authorization headers and
// POST bodies (a login form's password) and is only written when the context closes. Ours is redacted:
// credential headers and secret-looking form / JSON / query fields become [REDACTED]. Response bodies are never
// kept. execution.network: off | on-failure (attach the HAR when the test failed; default) | on (always).

export type NetworkMode = 'off' | 'on-failure' | 'on';

export interface NetEntry {
  method: string;
  url: string;
  resource_type: string;
  status: number | null;
  status_text: string;
  request_headers: Record<string, string>;
  response_headers: Record<string, string>;
  post_data: string | null;
  started_at: string;
  duration_ms: number | null;
  failure: string | null;
}

export const REDACTED = '[REDACTED]';
export const SENSITIVE_HEADERS = new Set([
  'cookie', 'set-cookie', 'authorization', 'proxy-authorization', 'x-api-key', 'x-auth-token', 'x-csrf-token',
  'x-xsrf-token',
]);
export const SENSITIVE_FIELD = /pass|secret|token|otp|pin|cvv|card|ssn|auth|session/i;
const MAX_POST = 4096;

export function redactHeaders(headers: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(headers || {})) out[k] = SENSITIVE_HEADERS.has(k.toLowerCase()) ? REDACTED : v;
  return out;
}

export function redactUrl(url: string): string {
  try {
    const u = new URL(url);
    let changed = false;
    for (const key of [...u.searchParams.keys()]) {
      if (SENSITIVE_FIELD.test(key)) {
        u.searchParams.set(key, REDACTED);
        changed = true;
      }
    }
    return changed ? u.toString() : url;
  } catch {
    return url;
  }
}

function redactJson(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(redactJson);
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      out[k] = SENSITIVE_FIELD.test(k) ? REDACTED : redactJson(v);
    }
    return out;
  }
  return value;
}

export function redactPostData(data: string | null, contentType = ''): string | null {
  if (data === null || data === undefined) return null;
  const ct = contentType.toLowerCase();
  if (ct.includes('application/x-www-form-urlencoded')) {
    const params = new URLSearchParams(data);
    for (const key of [...params.keys()]) if (SENSITIVE_FIELD.test(key)) params.set(key, REDACTED);
    return params.toString();
  }
  if (ct.includes('json')) {
    try {
      return JSON.stringify(redactJson(JSON.parse(data)));
    } catch {
      return REDACTED;
    }
  }
  if (ct.includes('multipart/form-data')) {
    return data.replace(/(name="([^"]*)"\r?\n\r?\n)([^\r\n]*)/g, (m, head, name) =>
      SENSITIVE_FIELD.test(name) ? `${head}${REDACTED}` : m);
  }
  return data;
}

function headerList(h: Record<string, string>) {
  return Object.entries(h).map(([name, value]) => ({ name, value }));
}

/** HAR 1.2 from recorded entries, redacted. */
export function buildHar(entries: NetEntry[]): Record<string, unknown> {
  return {
    log: {
      version: '1.2',
      creator: { name: 'mta-network-fixture', version: '1' },
      pages: [],
      entries: entries.map((e) => {
        const url = redactUrl(e.url);
        let query: Array<{ name: string; value: string }> = [];
        try {
          query = [...new URL(url).searchParams.entries()].map(([name, value]) => ({ name, value }));
        } catch { /* relative / opaque URL */ }
        const contentType = e.request_headers['content-type'] ?? '';
        const post = redactPostData(e.post_data, contentType);
        return {
          startedDateTime: e.started_at,
          time: e.duration_ms ?? -1,
          request: {
            method: e.method,
            url,
            httpVersion: 'HTTP/1.1',
            headers: headerList(redactHeaders(e.request_headers)),
            queryString: query,
            cookies: [],
            headersSize: -1,
            bodySize: post ? post.length : 0,
            ...(post !== null ? { postData: { mimeType: contentType, text: post } } : {}),
          },
          response: {
            status: e.status ?? 0,
            statusText: e.status_text,
            httpVersion: 'HTTP/1.1',
            headers: headerList(redactHeaders(e.response_headers)),
            cookies: [],
            content: { size: -1, mimeType: e.response_headers['content-type'] ?? '' },
            redirectURL: e.response_headers.location ?? '',
            headersSize: -1,
            bodySize: -1,
          },
          cache: {},
          timings: { send: 0, wait: e.duration_ms ?? -1, receive: 0 },
          _resourceType: e.resource_type,
          ...(e.failure ? { _failure: e.failure } : {}),
        };
      }),
    },
  };
}

/** The minimal surface of Playwright's Request / Response this log needs (so tests can fake it). */
export interface ReqLike {
  method(): string;
  url(): string;
  resourceType(): string;
  headers(): Record<string, string>;
  postData(): string | null;
  failure(): { errorText: string } | null;
}
export interface ResLike {
  request(): ReqLike;
  status(): number;
  statusText(): string;
  headers(): Record<string, string>;
  /** Present on real responses; JSON bodies are read for verifyResponseSchema (kept in memory, never in the HAR). */
  text?(): Promise<string>;
}

const MAX_BODY = 256 * 1024;

export interface ResponseBody {
  method: string;
  url: string;
  status: number | null;
  body: string | null;
}

type Filter = { method?: string; url?: string | RegExp; resourceType?: string };

function matches(e: NetEntry, f: Filter = {}): boolean {
  if (f.method && e.method.toUpperCase() !== f.method.toUpperCase()) return false;
  if (f.resourceType && e.resource_type !== f.resourceType) return false;
  if (f.url !== undefined) {
    if (f.url instanceof RegExp ? !f.url.test(e.url) : !e.url.includes(f.url)) return false;
  }
  return true;
}

export class NetworkLog {
  private readonly byReq = new Map<ReqLike, NetEntry & { t0: number }>();
  private readonly order: Array<NetEntry & { t0: number }> = [];
  private readonly bodies = new Map<NetEntry, Promise<string | null>>();

  constructor(private readonly now: () => number = Date.now) {}

  onRequest(req: ReqLike): void {
    const t0 = this.now();
    const post = req.postData();
    const entry = {
      method: req.method(), url: req.url(), resource_type: req.resourceType(), status: null, status_text: '',
      request_headers: req.headers(), response_headers: {}, post_data: post ? post.slice(0, MAX_POST) : null,
      started_at: new Date(t0).toISOString(), duration_ms: null, failure: null, t0,
    };
    this.byReq.set(req, entry);
    this.order.push(entry);
  }

  onResponse(res: ResLike): void {
    const e = this.byReq.get(res.request());
    if (!e) return;
    e.status = res.status();
    e.status_text = res.statusText();
    e.response_headers = res.headers();
    const ct = String(e.response_headers['content-type'] ?? '').toLowerCase();
    if (ct.includes('json') && typeof res.text === 'function') {
      this.bodies.set(e, res.text().then((t) => (t.length > MAX_BODY ? null : t), () => null));
    }
  }

  /** JSON response bodies (in request order) matching the filter — Phase 5 verifyResponseSchema. */
  async responseBodies(filter?: Filter): Promise<ResponseBody[]> {
    const hits = this.order.filter((e) => matches(e, filter) && this.bodies.has(e));
    return Promise.all(hits.map(async (e) => ({
      method: e.method, url: e.url, status: e.status, body: await this.bodies.get(e)!,
    })));
  }

  onFinished(req: ReqLike): void {
    const e = this.byReq.get(req);
    if (e) e.duration_ms = this.now() - e.t0;
  }

  onFailed(req: ReqLike): void {
    const e = this.byReq.get(req);
    if (!e) return;
    e.failure = req.failure()?.errorText ?? 'failed';
    e.duration_ms = this.now() - e.t0;
  }

  entries(filter?: Filter): NetEntry[] {
    return this.order.filter((e) => matches(e, filter)).map(({ t0, ...rest }) => rest);
  }

  requests(filter?: Filter): NetEntry[] {
    return this.entries(filter);
  }

  responses(filter?: Filter): NetEntry[] {
    return this.entries(filter).filter((e) => e.status !== null);
  }

  last(url: string | RegExp): NetEntry | null {
    const all = this.entries({ url });
    return all.length ? all[all.length - 1] : null;
  }

  har(): Record<string, unknown> {
    return buildHar(this.entries());
  }

  private readonly mocked: RegExp[] = [];

  /** Phase 5 mockRoute: responses for these URLs were made up by the test, not served by the app. */
  markMocked(pattern: RegExp): void {
    this.mocked.push(pattern);
  }

  isMocked(url: string): boolean {
    return this.mocked.some((re) => re.test(url));
  }

  /**
   * Phase 6.1: `network_error` annotations for a failed test — every >= 400 response (page loads and API calls
   * first, at most `limit`), URL redacted, "(mocked)" when the test answered it itself. Triage reads these.
   */
  errorAnnotations(limit = 10): Array<{ type: string; description: string }> {
    const bad = this.entries().filter((e) => (e.status ?? 0) >= 400);
    const rank = (e: NetEntry) => (['document', 'xhr', 'fetch'].includes(e.resource_type) ? 0 : 1);
    return bad.sort((a, b) => rank(a) - rank(b)).slice(0, limit).map((e) => ({
      type: 'network_error',
      description: `${e.method} ${redactUrl(e.url)} -> ${e.status}${this.isMocked(e.url) ? ' (mocked)' : ''}`,
    }));
  }
}

export function shouldAttachHar(mode: NetworkMode, failed: boolean): boolean {
  return mode === 'on' || (mode === 'on-failure' && failed);
}
