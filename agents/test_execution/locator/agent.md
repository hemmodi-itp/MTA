# LocatorAgent

Gap-filler agent — assigns CSS locators to intents that don't already have one.

## Why this exists

When `DiscoveryAgent` runs with a URL (modes `both`/`url_only`), most intents already have
`locator_id` set from the DOM scan. When it runs in `brd_only` mode (no URL at discovery time),
none of the intents have a locator. `LocatorAgent` only fills in the gap — it never re-scans intents
that already have a locator.

## Inputs
- `test_creation/intents.yaml`
- `url` (request field — if absent, the agent skips entirely)

## Outputs
- `test_creation/intents.yaml` (patched in place — missing `locator_id`s filled in)
- `test_creation/locators.json` (LOC-ID → resolved CSS selector map)

## Behavior

1. Skip immediately (`status: skipped`) if no `url` in the request, or `intents.yaml` doesn't exist,
   or every intent already has a `locator_id`.
2. Otherwise, run a live DOM scan (`PlaywrightScanner.scan_page`) and generate fresh intent
   suggestions from it (`generate_intent_suggestions`).
3. Match each locator-less intent against the freshly scanned DOM intents by exact name, then by a
   prefix-stripped normalized name (`fill_`/`click_`/`enter_`/`select_`/`verify_`/`navigate_`/
   `hover_`), then by substring match — first hit wins.
4. Write the patched `intents.yaml` back, and resolve every grounded `locator_id` to an actual CSS
   selector (`_build_loc_to_css_map`, preferring `recommended_locator` — id/name/css/testid/
   placeholder, in that priority — falling back to `technical_locators.css`) into `locators.json`.

## Failure mode

No tiered fallback (`_run_primary`/`_run_ns_fallback`/`_run_py_fallback`) — a DOM scan failure
returns `status: failed` directly with the exception message; a missing URL or already-fully-grounded
intents file returns `status: skipped` with a `reason`.
