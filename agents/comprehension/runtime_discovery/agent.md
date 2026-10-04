# RuntimeDiscoveryAgent

**Runtime Discovery Engine** of the evaluation workflow. It opens the live deployment in a real browser and describes what
a user can do there. Later engines build on this profile: App Classification refines `app_type`, and Action
Generation turns `user_flows` into browser actions. It makes no LLM calls; the logic lives in `engines/runtime/discovery.py`.

## Inputs
| Key | Type | Required | Notes |
|---|---|---|---|
| `live_url` | string | yes (live modes) | Skipped for `brd_only` or when empty |
| `repo_graph` | object | no | Page routes and API routes from RepoIntelligenceAgent, used as crawl hints |
| `live_credentials` | object | no | `{username, password}`, decrypted by the pipeline from the project's encrypted `liveAuth` |

## Output: `runtime_profile`
```json
{"app_type": "Document Generator", "forms": 3, "buttons": 8, "downloads": true,
 "chat_interface": false, "authentication": false,
 "pages_inspected": 5, "gated_pages": [], "needs_credentials": false, "login": {"attempted": false},
 "classification_signals": ["..."], "authentication_signals": ["..."], "file_uploads": 0,
 "frameworks": ["nextjs"], "api_calls": [{"method": "POST", "path": "/api/generate", "status": 200}],
 "user_flows": [{"name": "Submit form on /new", "entry": "/new", "steps": ["..."], "form_fields": ["..."]}],
 "pages": [{"path": "/new", "forms": ["..."], "buttons": ["..."], "downloads": {}, "auth": {}, "...": "..."}]}
```

## Behaviour
1. **Login (optional).** If a test account is configured, MTA finds the login form, fills the username and password, submits,
   and confirms the login worked. The crawl then continues from the page the login landed on.
   - **Cold starts:** the first request gets 120 s and one retry, because scale-to-zero hosts such as Azure Container Apps can take
     over a minute to answer.
   - **Client-rendered forms:** MTA waits up to 25 s for a visible password field rather than sleeping a fixed time.
   - **Where it looks:** the live URL, then the page's own "Log in" / "Sign in" link or button, then `/login`, `/signin`,
     `/sign-in`, `/auth/login`, `/account/login` and `/users/sign_in`.
   - **Success** means the URL left the login page or the password field disappeared, within 25 s.
   - **Failure** reports the app's own error message, or "still on the login page", or "no login form found", with the pages
     tried. Reports and gates then say "login failed (reason)", not "no test account".
   - **Without credentials**, the first request still gets the long wake-up timeout.
2. **List rows.** On each page, every "+ Add" / "Add row" / "Add item" button is clicked once, up to 20. This is client-side
   only and nothing is submitted. The input rows they create (repeater fields that start empty) are then scanned, and each
   such field records `revealed_by`: the button text, its position among same-text buttons, and its context.
3. **Item pages.** Parameterised routes such as `/runs/<id>` and `/orders/123` are sampled once, not once per record.
   Elements on them are never used as test targets (see Action Generation).
4. **Crawl** up to 12 same-origin pages, in this order: the landing page, page routes from the code graph (unparameterised),
   links found, and routes the app prefetches (from network traffic). Repeated landings on the same final URL, such as
   several gated pages all showing `/login`, are counted once.
3. **Per page** (one in-page DOM scan):
   - real `<form>`s and *virtual forms* (inputs grouped under a shared container with a submit-like button, the usual
     React shape), with each field's label, type, required flag and options;
   - buttons, links, downloads, file uploads, tables, charts and framework markers;
   - chat interfaces: one or two editable boxes, a send control or a chat log region, chat wording, and never on a page
     with a password field;
   - authentication signals: password fields, redirects to `/login`, API 401/403s.
4. **Network:** every same-origin XHR/fetch is recorded (method, normalised path, status). This is the app's real API surface.
5. **Profile:** counts, a preliminary `app_type` (Chat Agent, Document Generator, Form Application, Dashboard, Hybrid Platform,
   Static Website), candidate `user_flows` (log in, submit form → expect download or output, converse). When only
   login screens were visible, `app_type` is `Behind login` with `needs_credentials: true` instead of a guess.

## Failure mode
A page that can't be opened is logged and skipped. A browser or launch failure returns `status: partial` with no
profile. Later steps then fall back to code-only evidence and the report says so.
