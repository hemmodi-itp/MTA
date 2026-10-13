# Phase 7-mini (lean) report
**Changed**
- `tools/nonfunctional/generate.py`: deterministic generator (CLI: `python -m tools.nonfunctional.generate <project_dir>`). Reads app_map.json, one state per url_template (least-privileged role, blocked/4xx skipped), emits `test_creation/test_scripts/nfr/nfr_a11y.spec.ts` (tag @a11y, axe wcag2a/2aa/21a/21aa, critical/serious fail, moderate/minor → annotations, violations JSON attached) and one `nfr_security_<origin>.spec.ts` per origin (tag @security).
- `fixtures/securityRules.ts`: passive rules — headers (CSP, HSTS on https, nosniff, X-Frame-Options/frame-ancestors, Referrer-Policy), session-cookie flags, tokens/PII in URL and localStorage. No payloads.
- NFR AC linking: AC ids matched by text (WCAG/accessib…; HSTS/cookie/token…) become tags; else `@nfr`.
- Flags `test_types.accessibility` / `test_types.security_passive` (absent = OFF); ON in benchmark `project.yaml.tmpl`.
**Tests**: vitest `securityRules.test.ts` 7/7; pytest `tests/unit/test_nonfunctional_generate.py` 3/3 (2-page app_map). Generated specs not executed in a browser; `@axe-core/playwright` must be installed (`npm i -D`) before running @a11y.
**Deferred**: see docs/backlog.md "Phase 7" (visual, perf, responsive, resilience, i18n, active security, pipeline wiring, keyboard a11y).
