# Phase 7 non-functional benchmark — buggy_shop (2026-10-14)

Generated NFR specs (tools/nonfunctional/generate.py) from bench_buggy_shop's Phase 2 discovery, run through UIExecutionAgent on the correct app and with each seeded non-functional bug. Detected = the bug run has a failing finding the clean run does not.

Types: accessibility, visual, performance, security_passive, compatibility, resilience, i18n. Tests: 104.

| Seeded bug | Checked by | Detected | New finding(s) |
|---|---|---|---|
| BUG_08 | accessibility | yes | axe:label — Form elements must have labels (critical, 1 node(s)) @ a11y: /login (guest) @a11y @AC-01.4 |
| BUG_09 | performance | yes | budget:load_ms @ perf: /products (user) @perf @nfr<br>budget:load_ms @ perf: /products?page (user) @perf @nfr<br>budget:ttfb_ms @ perf: /products (user) @perf @nfr |
| BUG_07 | resilience | yes | server-error @ resilience: /products (user) #search-form handles unusual input @resilience @nfr<br>server-error @ resilience: /products?page (user) #search-form handles unusual input @resilience @nfr |

**3/3 detected.**

## Findings on the correct app (44; 11 failing test(s))

Real issues of the benchmark app itself (not seeded bugs) — e.g. missing security headers:

- csp — Content-Security-Policy header is missing @ security: /admin (admin) @security @AC-01.3
- csp — Content-Security-Policy header is missing @ security: /cart (user) @security @AC-01.3
- csp — Content-Security-Policy header is missing @ security: /checkout (user) @security @AC-01.3
- csp — Content-Security-Policy header is missing @ security: /help (guest) @security @AC-01.3
- csp — Content-Security-Policy header is missing @ security: /login (guest) @security @AC-01.3
- csp — Content-Security-Policy header is missing @ security: /products (user) @security @AC-01.3
- csp — Content-Security-Policy header is missing @ security: /products/new (user) @security @AC-01.3
- csp — Content-Security-Policy header is missing @ security: /products/{id} (user) @security @AC-01.3
- csp — Content-Security-Policy header is missing @ security: /products/{id}/edit (user) @security @AC-01.3
- csp — Content-Security-Policy header is missing @ security: /products?page (user) @security @AC-01.3
- csp — Content-Security-Policy header is missing @ security: /upload (user) @security @AC-01.3
- framing — Neither X-Frame-Options nor CSP frame-ancestors is set @ security: /admin (admin) @security @AC-01.3
- framing — Neither X-Frame-Options nor CSP frame-ancestors is set @ security: /cart (user) @security @AC-01.3
- framing — Neither X-Frame-Options nor CSP frame-ancestors is set @ security: /checkout (user) @security @AC-01.3
- framing — Neither X-Frame-Options nor CSP frame-ancestors is set @ security: /help (guest) @security @AC-01.3
- framing — Neither X-Frame-Options nor CSP frame-ancestors is set @ security: /login (guest) @security @AC-01.3
- framing — Neither X-Frame-Options nor CSP frame-ancestors is set @ security: /products (user) @security @AC-01.3
- framing — Neither X-Frame-Options nor CSP frame-ancestors is set @ security: /products/new (user) @security @AC-01.3
- framing — Neither X-Frame-Options nor CSP frame-ancestors is set @ security: /products/{id} (user) @security @AC-01.3
- framing — Neither X-Frame-Options nor CSP frame-ancestors is set @ security: /products/{id}/edit (user) @security @AC-01.3
- framing — Neither X-Frame-Options nor CSP frame-ancestors is set @ security: /products?page (user) @security @AC-01.3
- framing — Neither X-Frame-Options nor CSP frame-ancestors is set @ security: /upload (user) @security @AC-01.3
- referrer-policy — Referrer-Policy header is missing @ security: /admin (admin) @security @AC-01.3
- referrer-policy — Referrer-Policy header is missing @ security: /cart (user) @security @AC-01.3
- referrer-policy — Referrer-Policy header is missing @ security: /checkout (user) @security @AC-01.3
- referrer-policy — Referrer-Policy header is missing @ security: /help (guest) @security @AC-01.3
- referrer-policy — Referrer-Policy header is missing @ security: /login (guest) @security @AC-01.3
- referrer-policy — Referrer-Policy header is missing @ security: /products (user) @security @AC-01.3
- referrer-policy — Referrer-Policy header is missing @ security: /products/new (user) @security @AC-01.3
- referrer-policy — Referrer-Policy header is missing @ security: /products/{id} (user) @security @AC-01.3
- referrer-policy — Referrer-Policy header is missing @ security: /products/{id}/edit (user) @security @AC-01.3
- referrer-policy — Referrer-Policy header is missing @ security: /products?page (user) @security @AC-01.3
- referrer-policy — Referrer-Policy header is missing @ security: /upload (user) @security @AC-01.3
- x-content-type-options — X-Content-Type-Options must be "nosniff" @ security: /admin (admin) @security @AC-01.3
- x-content-type-options — X-Content-Type-Options must be "nosniff" @ security: /cart (user) @security @AC-01.3
- x-content-type-options — X-Content-Type-Options must be "nosniff" @ security: /checkout (user) @security @AC-01.3
- x-content-type-options — X-Content-Type-Options must be "nosniff" @ security: /help (guest) @security @AC-01.3
- x-content-type-options — X-Content-Type-Options must be "nosniff" @ security: /login (guest) @security @AC-01.3
- x-content-type-options — X-Content-Type-Options must be "nosniff" @ security: /products (user) @security @AC-01.3
- x-content-type-options — X-Content-Type-Options must be "nosniff" @ security: /products/new (user) @security @AC-01.3
- … 4 more (see the .json)
