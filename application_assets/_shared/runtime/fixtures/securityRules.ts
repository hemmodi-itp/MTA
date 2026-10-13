// securityRules.ts — pure passive-security rules (Phase 7-mini). Inspect headers / cookies / URLs / storage only; no payloads.

export interface Finding { rule: string; message: string }

export function checkHeaders(h: Record<string, string>, opts: { https?: boolean } = {}): Finding[] {
  const g: Record<string, string> = {};
  for (const [k, v] of Object.entries(h)) g[k.toLowerCase()] = v;
  const out: Finding[] = [];
  const csp = g['content-security-policy'];
  if (!csp) out.push({ rule: 'csp', message: 'Content-Security-Policy header is missing' });
  if (opts.https && !/max-age=\d+/i.test(g['strict-transport-security'] ?? '')) {
    out.push({ rule: 'hsts', message: 'Strict-Transport-Security header is missing or has no max-age' });
  }
  if ((g['x-content-type-options'] ?? '').toLowerCase().trim() !== 'nosniff') {
    out.push({ rule: 'x-content-type-options', message: 'X-Content-Type-Options must be "nosniff"' });
  }
  if (!g['x-frame-options'] && !/frame-ancestors/i.test(csp ?? '')) {
    out.push({ rule: 'framing', message: 'Neither X-Frame-Options nor CSP frame-ancestors is set' });
  }
  if (!g['referrer-policy']) out.push({ rule: 'referrer-policy', message: 'Referrer-Policy header is missing' });
  return out;
}

export interface CookieLike { name: string; httpOnly?: boolean; secure?: boolean; sameSite?: string }

const SESSION_NAME = /sess|sid|token|auth|jwt/i;

export function checkCookies(cookies: CookieLike[], opts: { https?: boolean } = {}): Finding[] {
  const out: Finding[] = [];
  for (const c of cookies.filter((c) => SESSION_NAME.test(c.name))) {
    if (!c.httpOnly) out.push({ rule: 'cookie-httponly', message: `cookie "${c.name}" lacks HttpOnly` });
    if (opts.https && !c.secure) out.push({ rule: 'cookie-secure', message: `cookie "${c.name}" lacks Secure` });
    if (!c.sameSite || c.sameSite.toLowerCase() === 'none') {
      out.push({ rule: 'cookie-samesite', message: `cookie "${c.name}" lacks SameSite=Lax/Strict` });
    }
  }
  return out;
}

const JWT = /\beyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}/;
const SECRET_KEY = /(^|[^a-z])(token|access_token|api[_-]?key|apikey|secret|password|passwd|session(id)?|auth)([^a-z]|$)/i;
const PII = /[\w.+-]+@[\w-]+\.[\w.-]+|\b\d{3}-\d{2}-\d{4}\b|\b(?:\d[ -]?){13,16}\b/;

function sensitive(key: string, value: string): boolean {
  return JWT.test(value) || PII.test(value) || (SECRET_KEY.test(key) && value.length >= 8);
}

export function checkUrl(url: string): Finding[] {
  let u: URL;
  try { u = new URL(url); } catch { return []; }
  const out: Finding[] = [];
  for (const [k, v] of u.searchParams) {
    if (sensitive(k, v)) out.push({ rule: 'url-secret', message: `URL query parameter "${k}" looks like a token or PII` });
  }
  if (JWT.test(u.pathname) || PII.test(decodeURIComponent(u.pathname))) {
    out.push({ rule: 'url-secret', message: 'URL path contains a token or PII-like value' });
  }
  return out;
}

export function checkStorage(store: Record<string, string>, name = 'localStorage'): Finding[] {
  const out: Finding[] = [];
  for (const [k, v] of Object.entries(store)) {
    if (sensitive(k, String(v))) out.push({ rule: 'storage-secret', message: `${name} key "${k}" holds a token or PII-like value` });
  }
  return out;
}
