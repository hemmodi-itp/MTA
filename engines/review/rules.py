"""
rules.py — deterministic review findings over the knowledge graph and fetched code.

Each finding: {dimension, rule_id, severity, title, file, start_line, end_line, rationale, fix,
source: "scanner", confidence, verified: True}. These are facts a scanner can prove; the LLM reviewer only
adds interpretation on top (agents/evaluation/repository_review). Findings with `verified: False` (an LLM
finding that could not be placed at a real file:line) are reported but never penalise the scorecard.

The secret scan and the web rules run over every indexed chunk, i.e. every source language the indexer reads.
The missing-auth rule looks for real authentication constructs (middleware, decorators, dependencies, guards,
auth libraries), not for words such as "session" or "login".
"""

import re
from typing import Dict, List, Sequence

from engines.repo_intel.indexer import has_tests
from engines.repo_intel.model import Chunk, Graph

SEVERITY_PENALTY = {"critical": 40, "high": 20, "medium": 8, "low": 2, "info": 0}
DIMENSIONS = ("architecture", "security", "agent_design", "workflow", "performance", "production_readiness")

_SECRETS = [
    ("google-api-key", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("openai-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{32,}")),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{32,}")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("hardcoded-credential", re.compile(
        r"""(?i)\b(api[_-]?key|secret|password|passwd|token)\b\s*[:=]\s*["']([^"'\s]{12,})["']""")),
]
_ROUTE_CALL = re.compile(r"\.(get|post|put|patch|delete|all|route)\s*\(|@\w+\.(get|post|put|patch|delete|route)\(", re.I)
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

# App-wide authentication: middleware / global dependencies / framework security config.
_AUTH_GLOBAL = re.compile(
    r"(?i)\b(app|router|server)\.use\([^)]*\b(auth\w*|jwt\w*|passport\.\w+|requireAuth|protect\w*|clerkMiddleware|"
    r"expressjwt|session\(|ensureAuth\w*|isAuthenticated|verifyToken|authenticate)"
    r"|add_middleware\(\s*\w*(Auth|Session|JWT|OAuth)\w*"
    r"|@\w+\.before_request"
    r"|(FastAPI|APIRouter)\([^)]*dependencies\s*=\s*\[[^\]]*Depends\("
    r"|\bSecurityFilterChain\b|@EnableWebSecurity|\.authorizeHttpRequests\(|\.authorizeRequests\("
    r"|before_action\s+:authenticate\w*|DEFAULT_PERMISSION_CLASSES|DEFAULT_AUTHENTICATION_CLASSES"
    r"|LoginRequiredMiddleware|\bclerkMiddleware\(|\bwithAuth\(|export\s*\{\s*auth\s+as\s+middleware|NextAuth\("
    r"|\.UseAuthentication\(\)|\.RequireAuthorization\(|\bAuthMiddleware\b|jwtauth\.Verifier"
    r"|\bAPP_GUARD\b|useGlobalGuards\("
)
# Per-handler authentication: decorators, dependencies, guards, explicit token checks.
_AUTH_LOCAL = re.compile(
    r"(?i)Depends\(\s*\w*(auth|user|token|current|verify|api_?key|security|oauth|session|jwt|principal)\w*"
    r"|\bSecurity\(|HTTPBearer\(|OAuth2PasswordBearer\(|APIKey(Header|Query|Cookie)\("
    r"|@\w*(login_required|jwt_required|auth_required|requires_auth|token_required|permission_required|"
    r"authenticated|roles_required|admin_required)\b"
    r"|@\w+\.login_required|LoginRequiredMixin|permission_classes|IsAuthenticated"
    r"|@UseGuards\(|@PreAuthorize|@Secured|@RolesAllowed|\[Authorize"
    r"|passport\.authenticate\(|\brequireAuth\b|\bisAuthenticated\b|\bensureAuth\w*|\bverifyToken\b|"
    r"jwt\.verify\(|jwt\.decode\(|getServerSession\(|\bauth\(\s*\)|currentUser\(|getAuth\(|"
    r"supabase\.auth\.getUser|verifyIdToken\(|authenticate_user!|request\.user\.is_authenticated|"
    r"current_user\.is_authenticated|get_current_user|verify_api_key|check_api_key|x-api-key"
)
_AUTH_DEPS = re.compile(r"(?i)^(flask[-_]login|flask[-_]jwt[-_]extended|flask[-_]httpauth|fastapi[-_]users|"
                        r"django[-_]allauth|djangorestframework[-_]simplejwt|authlib|python[-_]jose|pyjwt|passport\S*|"
                        r"next-auth|@auth/\S+|@clerk/\S+|express-jwt|jsonwebtoken|@auth0/\S+|firebase-admin|"
                        r"@supabase/\S+|express-session|@nestjs/passport|lucia|better-auth)$")

_PLACEHOLDER = re.compile(r"(?i)(your|xxx|changeme|example|placeholder|dummy|test|<|\$\{|process\.env|os\.environ)")


def rule_findings(graph: Graph, chunks: Sequence[Chunk], all_paths: Sequence[str]) -> List[Dict]:
    out: List[Dict] = []
    seen = set()

    def add(**f):
        key = (f["rule_id"], f.get("file"), f.get("start_line"))
        if key not in seen:
            seen.add(key)
            out.append({"source": "scanner", "confidence": 1.0, "verified": True, "end_line": f.get("start_line"), **f})

    text_all = "\n".join(c.content for c in chunks)

    # ── secrets ──
    for c in chunks:
        if c.file_path.endswith((".md", ".example", ".sample", ".txt")) or "/test" in f"/{c.file_path}":
            continue
        for i, line in enumerate(c.content.splitlines()):
            for rule, rx in _SECRETS:
                m = rx.search(line)
                if not m or (rule == "hardcoded-credential" and _PLACEHOLDER.search(m.group(0))):
                    continue
                add(dimension="security", rule_id=f"secret/{rule}", severity="critical",
                    title=f"Hard-coded secret ({rule.replace('-', ' ')})", file=c.file_path, start_line=c.start_line + i,
                    rationale="A credential is committed to the repository and is readable by anyone with access.",
                    fix="Revoke the credential, load it from an environment variable or secret manager, and purge it from git history.")
    for p in all_paths:
        name = p.rsplit("/", 1)[-1]
        if name in (".env", ".env.local", ".env.production") or name.endswith(".pem"):
            add(dimension="security", rule_id="secret/committed-env-file", severity="high",
                title=f"Environment/secret file committed: {p}", file=p, start_line=1,
                rationale="Environment files usually contain credentials.",
                fix="Remove it from the repository, add it to .gitignore, rotate anything it contained.")

    # ── web security hygiene ──
    for c in chunks:
        for i, line in enumerate(c.content.splitlines()):
            if re.search(r"allow_origins\s*=\s*\[\s*[\"']\*[\"']\s*\]|cors\(\s*\)|origin:\s*[\"']\*[\"']|Access-Control-Allow-Origin[\"']?\s*[:,]\s*[\"']\*", line):
                add(dimension="security", rule_id="web/cors-wildcard", severity="medium",
                    title="CORS allows any origin", file=c.file_path, start_line=c.start_line + i,
                    rationale="Any website can call this API from a user's browser.",
                    fix="Restrict allowed origins to the deployed frontend's domains.")
            if re.search(r"\.run\([^)]*debug\s*=\s*True|^\s*DEBUG\s*=\s*True", line):
                add(dimension="security", rule_id="web/debug-mode", severity="medium",
                    title="Debug mode enabled in code", file=c.file_path, start_line=c.start_line + i,
                    rationale="Debug mode exposes stack traces and, for Flask/Werkzeug, an interactive console.",
                    fix="Drive debug mode from configuration and keep it off in production.")

    writes = [n for n in graph.of_kind("route") if n.props.get("method") in ("POST", "PUT", "PATCH", "DELETE")]
    if writes and not _AUTH_GLOBAL.search(text_all):
        open_routes = [r for r in writes if not _route_authenticated(r, graph, chunks)]
        any_auth = len(open_routes) < len(writes) or any(_AUTH_DEPS.match(n.name or "") for n in graph.of_kind("dependency"))
        if open_routes and not any_auth:
            first = open_routes[0]
            add(dimension="security", rule_id="web/no-auth", severity="high",
                title=f"No authentication on {len(open_routes)} state-changing route(s)", file=first.file_path,
                start_line=first.start_line or 1,
                rationale="No authentication middleware, guard, decorator, dependency or auth library was found anywhere "
                          f"in the fetched code; e.g. {', '.join(r.name or r.key for r in open_routes[:4])}.",
                fix="Require authentication (session, token or API key) on every route that changes state or spends LLM budget.")
        elif open_routes:
            first = open_routes[0]
            add(dimension="security", rule_id="web/unauthenticated-routes", severity="medium",
                title=f"{len(open_routes)} of {len(writes)} state-changing route(s) have no visible authentication",
                file=first.file_path, start_line=first.start_line or 1, confidence=0.6,
                rationale="The app authenticates some routes, but these show no auth decorator, dependency or guard and no "
                          f"app-wide middleware was found: {', '.join(r.name or r.key for r in open_routes[:6])}. "
                          "Intentionally public endpoints are fine; confirm each one is.",
                fix="Protect these routes, or document why each is public.")

    # ── workflow / agent reliability ──
    llm_nodes = graph.of_kind("model_call") + graph.of_kind("agent")
    if llm_nodes and not re.search(r"(?i)\b(retry|retries|tenacity|backoff|max_retries|with_retry)\b", text_all):
        n = llm_nodes[0]
        add(dimension="workflow", rule_id="llm/no-retry", severity="medium",
            title="LLM calls have no retry or backoff", file=n.file_path, start_line=n.start_line or 1,
            rationale=f"{len(llm_nodes)} LLM call site(s)/agent(s) found and no retry mechanism anywhere; "
                      "transient provider errors fail the whole request.",
            fix="Wrap LLM calls with bounded retries and exponential backoff, and surface a clear error after the last attempt.")
    if llm_nodes and not re.search(r"(?i)\btimeout\b", text_all):
        n = llm_nodes[0]
        add(dimension="performance", rule_id="llm/no-timeout", severity="low",
            title="No timeouts configured for LLM or HTTP calls", file=n.file_path, start_line=n.start_line or 1,
            rationale="A hung provider call blocks the request indefinitely.",
            fix="Set explicit timeouts on LLM clients and outbound HTTP calls.")

    # ── production readiness ──
    if not has_tests(graph, list(all_paths)):
        add(dimension="production_readiness", rule_id="ready/no-tests", severity="medium", title="No automated tests",
            file=None, start_line=None, rationale="No test files or test functions were found.",
            fix="Add unit tests for the core logic and at least one end-to-end test per main user flow.")
    if graph.of_kind("route") and not any(re.search(r"health|status|ping|ready", n.key) for n in graph.of_kind("route")):
        add(dimension="production_readiness", rule_id="ready/no-health", severity="low", title="No health-check endpoint",
            file=None, start_line=None, rationale="Load balancers and orchestrators cannot probe the service.",
            fix="Add a lightweight GET /health route.")
    names = {p.rsplit("/", 1)[-1].lower() for p in all_paths}
    if not names & {"readme.md", "readme.rst", "readme"}:
        add(dimension="production_readiness", rule_id="ready/no-readme", severity="low", title="No README",
            file=None, start_line=None, rationale="No setup or usage documentation.", fix="Add a README with setup, configuration and run steps.")
    for c in chunks:
        if c.file_path.rsplit("/", 1)[-1] == "requirements.txt":
            unpinned = [l.strip() for l in c.content.splitlines()
                        if l.strip() and not l.lstrip().startswith(("#", "-")) and not re.search(r"[=<>~]", l)]
            if unpinned:
                add(dimension="production_readiness", rule_id="deps/unpinned", severity="low",
                    title=f"{len(unpinned)} unpinned Python dependencies", file=c.file_path, start_line=c.start_line,
                    rationale=f"e.g. {', '.join(unpinned[:5])}: builds are not reproducible.",
                    fix="Pin versions (or use a lock file).")
    return out


def _route_authenticated(route, graph: Graph, chunks: Sequence[Chunk]) -> bool:
    """Auth markers on the route's handler (decorators / signature / body) or around its registration line."""
    spans: List[tuple] = []
    handler = graph.nodes.get(route.props.get("handler") or "")
    if handler and handler.start_line:
        spans.append((handler.file_path, max(1, handler.start_line - 6), handler.end_line or handler.start_line))
    if route.start_line:  # the registration call itself (router.post("/x", requireAuth, h)), up to 3 lines
        spans.append((route.file_path, route.start_line, route.start_line + 2))
    for c in chunks:
        for i, (path, a, b) in enumerate(spans):
            if c.file_path == path and c.start_line <= b and c.end_line >= a:
                lines = c.content.splitlines()[max(0, a - c.start_line): max(0, b - c.start_line + 1)]
                if i == len(spans) - 1 and route.start_line:  # stop at the next route registration
                    cut = next((j for j, l in enumerate(lines[1:], 1) if _ROUTE_CALL.search(l)), len(lines))
                    lines = lines[:cut]
                if _AUTH_LOCAL.search("\n".join(lines)):
                    return True
    return False


def sort_findings(findings: Sequence[Dict]) -> List[Dict]:
    """Most severe first; verified before unverified; then higher confidence."""
    return sorted(findings, key=lambda f: (SEVERITY_ORDER.get(f.get("severity"), 5), f.get("verified") is False,
                                           -float(f.get("confidence") or 0)))


def scorecard(findings: Sequence[Dict]) -> Dict[str, int]:
    """100 minus severity penalties per dimension; unverified findings are reported, never penalised."""
    card = {d: 100 for d in DIMENSIONS}
    for f in findings:
        d = f.get("dimension")
        if f.get("verified") is False:
            continue
        if d in card:
            card[d] = max(0, card[d] - SEVERITY_PENALTY.get(f.get("severity"), 0))
    return card
