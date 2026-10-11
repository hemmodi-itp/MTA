"""
crawl.py — multi-page, multi-role crawl and state model (tasks 2.4–2.7).

    result = DeepDiscovery(project, cfg, roles, seeds, policy, request).run()
    result["app_map"], result["form_model"], result["api_inventory"],
    result["permission_matrix"], result["baseline"]          # artifact bodies (no envelope keys)

Per role, breadth-first from the seeds (every module URL + project.url):
  * a URL is skipped when it is off the allow-list, matches the shared skip-link rules
    (logout, delete, assets, mailto …), the safety classifier calls it destructive, or its URL
    template already has `samples_per_template` visits;
  * each visit -> deep element extraction -> state = (URL template, structural hash);
  * links become transitions and queue entries (depth + 1, up to max_depth);
  * new states: non-destructive expanders are clicked (tabs, accordions, menus, dialog
    triggers) to reveal hidden states; forms are probed once per project (forms.py);
    console / page errors / timing are recorded (baseline.py);
  * every request goes through NetworkRecorder; WriteGuard aborts any write outside a
    full-mode form probe.
Then a union pass deep-links, for every role, the page templates other roles reached, and the
results are diffed into the permission matrix.

Bounds: max_pages per role, max_depth, and max_minutes for the whole pass (the crawl share is
split evenly across roles; the union pass uses what is left).
"""

import collections
import datetime as _dt
import logging
import time
import urllib.parse
from typing import Any, Callable, Dict, List, Optional, Tuple

from tools.discovery.deep import forms as F
from tools.discovery.deep.baseline import BaselineRecorder
from tools.discovery.deep.config import DiscoveryConfig, RoleConfig
from tools.discovery.deep.extract import LIMITATIONS, extract_page
from tools.discovery.deep.network import InflightTracker, NetworkRecorder, WriteGuard, aggregate
from tools.discovery.deep.permission import action_keys, build_matrix
from tools.discovery.deep.roles import classify_visit, open_role, redirected_to_login, relogin
from tools.discovery.deep.state_hash import SKELETON_JS, state_id, structural_hash
from tools.discovery.web.links import skip_link
from tools.discovery.web.ready import READY_JS, wait_for_render
from tools.discovery.web.urls import strip_fragment, template_url
from tools.safety.action_classifier import classify, classify_url
from tools.safety.policy import SafetyPolicy

_log = logging.getLogger("workflow.discovery.deep")

NAV_TIMEOUT_MS = 30_000
CRAWL_SHARE = 0.85


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def norm_url(url: str) -> str:
    u = strip_fragment(url or "")
    parts = urllib.parse.urlsplit(u)
    path = parts.path.rstrip("/") or "/"
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


def is_expander(el: Dict[str, Any]) -> bool:
    if not (el.get("quality") or {}).get("visible") or not (el.get("quality") or {}).get("enabled"):
        return False
    hints = el.get("state_hints") or {}
    href = el.get("href") or ""
    if href and not href.split("#", 1)[0].rstrip("/") == "" and "#" not in href:
        return False  # a real link navigates; it is crawled as a link, not clicked
    if el.get("tag_name") == "summary":
        return True
    if el.get("aria_role") == "tab":
        return True
    if hints.get("expanded") == "false":
        return True
    if hints.get("haspopup") not in (None, "", "false"):
        return True
    if hints.get("toggle"):
        return True
    return el.get("tag_name") == "button" and hints.get("type") == "button" and bool(hints.get("controls"))


class DeepDiscovery:
    def __init__(self, project: str, cfg: DiscoveryConfig, roles: List[RoleConfig], seeds: List[Dict[str, Any]],
                 policy: SafetyPolicy, browser: str = "chromium", headless: bool = True,
                 log: Optional[Callable[[str], None]] = None, config_hash: str = ""):
        self.project = project
        self.cfg = cfg
        self.roles = roles
        self.seeds = seeds
        self.policy = policy
        self.browser_name = browser
        self.headless = headless
        self.log = log or (lambda m: _log.info(m))
        self.config_hash = config_hash
        # results
        self.states: Dict[str, Dict[str, Any]] = {}
        self.template_state: Dict[str, str] = {}
        self.transitions: List[Dict[str, Any]] = []
        self._transition_index: Dict[Tuple[str, str, str, str], int] = {}
        self.skipped: List[Dict[str, Any]] = []
        self.forms: Dict[str, Dict[str, Any]] = {}
        self.skipped_forms: List[Dict[str, Any]] = []
        self.baseline: Dict[str, Dict[str, Any]] = {}
        self.network_records: List[Dict[str, Any]] = []
        self.role_pages: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.stopped_by: Dict[str, str] = {}
        self.browser_version = ""
        self.locale = ""

    # ── helpers ─────────────────────────────────────────────────────────
    def _refuse(self, url: str) -> Optional[str]:
        if not url.startswith(("http://", "https://")):
            return "not_http"
        if not self.policy.url_allowed(url):
            return "host_not_allowed"
        if skip_link(url):
            return "skip_link"
        if classify_url(url).destructive:
            return "destructive_url"
        return None

    def _settle(self, page) -> None:
        tracker = self._trackers.get(id(page.context))
        try:
            page.wait_for_load_state("load", timeout=5_000)
        except Exception:
            pass
        if tracker is not None:
            tracker.wait_quiet(page)
        else:
            try:
                page.wait_for_load_state("networkidle", timeout=5_000)
            except Exception:
                pass
        try:
            controls, _, _, headings = page.evaluate(READY_JS)
            if controls == 0 and headings == 0:
                wait_for_render(page, 10)
        except Exception:
            pass

    def _visit(self, page, recorder: NetworkRecorder, url: str) -> Dict[str, Any]:
        recorder.set_trigger(f"navigate {urllib.parse.urlsplit(url).path or '/'}", None)
        status = None
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            status = resp.status if resp else None
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}", "status": None, "final_url": page.url}
        self._settle(page)
        recorder.drain_json()          # response bodies are only readable while the page that loaded them is alive
        return {"ok": True, "status": status, "final_url": page.url}

    def _snapshot(self, page) -> Tuple[List[Dict[str, Any]], str, Dict[str, Any]]:
        out = extract_page(page, self.cfg, url_allowed=self.policy.url_allowed)
        try:
            skeleton = page.evaluate(SKELETON_JS)
        except Exception:
            skeleton = {}
        return out["elements"], structural_hash(out["elements"], skeleton), out["scan"]

    def _register_state(self, sid: str, url: str, tmpl: str, title: str, struct: str, elements: List[Dict[str, Any]],
                        role: str, status: Optional[int], access: str, depth: int, seed: Optional[str],
                        kind: str = "page", revealed_by: Optional[Dict[str, Any]] = None) -> bool:
        if sid in self.states:
            if role not in self.states[sid]["roles"]:
                self.states[sid]["roles"].append(role)
            return False
        els = []
        for i, el in enumerate(elements, 1):
            e = dict(el)
            e["locator_id"] = f"{sid}:E-{i:03d}"
            els.append(e)
        self.states[sid] = {
            "state_id": sid, "url": url, "url_template": tmpl, "title": title or "", "kind": kind,
            "revealed_by": revealed_by, "status": status, "access": access, "structural_hash": struct,
            "roles": [role], "elements": els, "forms": [], "first_seen_depth": depth, "seed": seed,
        }
        return True

    def _add_transition(self, t: Dict[str, Any]) -> int:
        key = (t["from_state"], t["action"], (t["element"] or {}).get("name") or "",
               norm_url((t["element"] or {}).get("href") or "") or str(t.get("to_state")))
        if key in self._transition_index:
            i = self._transition_index[key]
            for r in t["roles"]:
                if r not in self.transitions[i]["roles"]:
                    self.transitions[i]["roles"].append(r)
            return i
        self.transitions.append(t)
        self._transition_index[key] = len(self.transitions) - 1
        return len(self.transitions) - 1

    # ── one role ────────────────────────────────────────────────────────
    def _crawl_role(self, browser, role: RoleConfig, deadline: float) -> Tuple[Any, Any, NetworkRecorder]:
        pages_of_role: Dict[str, Dict[str, Any]] = self.role_pages.setdefault(role.name, {})
        ctx, page, info = open_role(browser, role)
        if not info.get("ok"):
            self.stopped_by[role.name] = f"login_failed: {info.get('error')}"
            self.log(f"[deep] role '{role.name}': sign-in failed — {info.get('error')}")
            if ctx is None:
                return None, None, NetworkRecorder(role.name, self.policy.url_allowed)
        recorder = NetworkRecorder(role.name, self.policy.url_allowed)
        recorder.attach(ctx)
        guard = WriteGuard(recorder)
        guard.install(ctx)
        self._guards[role.name] = guard
        tracker = InflightTracker()
        tracker.attach(ctx)
        self._trackers[id(ctx)] = tracker
        base_rec = BaselineRecorder(self.policy.url_allowed)
        base_rec.attach(page)
        self._recorders.append(recorder)
        if role.name in self.stopped_by:          # login failed but a context exists: crawl nothing
            return ctx, page, recorder

        queue: collections.deque = collections.deque()
        for s in self.seeds:
            queue.append((s["url"], 0, s))
        pending: Dict[str, List[int]] = collections.defaultdict(list)
        refused: Dict[str, str] = {}
        seen: set = set()
        template_counts: Dict[str, int] = collections.Counter()
        setups_done: set = set()
        visits = 0
        home_ok: Optional[str] = None
        relogged = False
        stop = "queue_empty"

        while queue:
            if time.monotonic() > deadline:
                stop = "max_minutes"
                break
            if visits >= self.cfg.max_pages:
                stop = "max_pages"
                break
            url, depth, seed = queue.popleft()
            n = norm_url(url)
            if n in seen:
                continue
            reason = self._refuse(url)
            if reason:
                self.skipped.append({"role": role.name, "url": url, "reason": reason})
                for i in pending.pop(n, []):
                    self.transitions[i]["unresolved_reason"] = reason
                refused[n] = reason
                seen.add(n)
                continue
            tmpl = template_url(url)
            if template_counts[tmpl] >= self.cfg.samples_per_template:
                for i in pending.pop(n, []):
                    if tmpl in self.template_state:
                        self.transitions[i]["to_state"] = self.template_state[tmpl]
                        self.transitions[i]["resolved_by_template"] = True
                seen.add(n)
                continue
            seen.add(n)
            template_counts[tmpl] += 1

            if role.name == "default" and seed and seed.get("setup_steps"):
                key = repr(seed["setup_steps"])
                if key not in setups_done:
                    from tools.playwright_scanner import execute_setup_steps
                    execute_setup_steps(page, seed["setup_steps"], _log)
                    setups_done.add(key)

            base_rec.begin()
            visit = self._visit(page, recorder, url)
            visits += 1
            if not visit["ok"]:
                self.skipped.append({"role": role.name, "url": url, "reason": f"visit_failed: {visit.get('error')}"})
                continue

            final = visit["final_url"]
            if (role.strategy != "anonymous" and home_ok and redirected_to_login(url, final)
                    and n != norm_url(home_ok)):
                # session lost? check a page that worked before
                probe = self._visit(page, recorder, home_ok)
                if probe["ok"] and redirected_to_login(home_ok, probe["final_url"]):
                    if relogged or not relogin(page, role):
                        stop = "session_lost"
                        break
                    relogged = True
                    self.log(f"[deep] role '{role.name}': session lost — signed in again")
                    base_rec.begin()
                    visit = self._visit(page, recorder, url)
                    final = visit["final_url"]

            access = classify_visit(url, final, visit["status"])
            recorder.refresh_cookies(ctx)
            try:
                elements, struct, _scan = self._snapshot(page)
                title = page.title()
            except Exception as exc:
                self.skipped.append({"role": role.name, "url": url, "reason": f"extract_failed: {type(exc).__name__}"})
                continue
            ftmpl = template_url(final)
            sid = state_id(ftmpl, struct)
            recorder.state_id = sid
            is_new = self._register_state(sid, final, ftmpl, title, struct, elements, role.name, visit["status"],
                                          access, depth, (seed or {}).get("url"))
            self.template_state.setdefault(tmpl, sid)
            self.template_state.setdefault(ftmpl, sid)
            if is_new and self.cfg.baseline:
                self.baseline[sid] = base_rec.snapshot(page, final, role.name)
            else:
                base_rec.begin()
            for i in pending.pop(n, []):
                self.transitions[i]["to_state"] = sid
            pages_of_role.setdefault(tmpl, {
                "sample_url": url, "access": access, "via": "crawl", "status": visit["status"],
                "final_url": final, "actions": action_keys(elements) if access == "reachable" else [],
            })
            if access == "reachable" and home_ok is None:
                home_ok = url
            if access != "reachable":
                continue

            if depth < self.cfg.max_depth:
                for el in elements:
                    href = el.get("href")
                    if not href or el.get("frame"):
                        continue
                    target = strip_fragment(href)
                    if not target or norm_url(target) == n:
                        continue
                    t = {"from_state": sid, "to_state": None, "action": "navigate", "via": "href",
                         "element": {"ref": el["locator_id"], "role": el.get("aria_role") or "link",
                                     "name": (el.get("display_text") or "")[:120], "href": target},
                         "roles": [role.name], "resolved_by_template": False, "unresolved_reason": None}
                    i = self._add_transition(t)
                    tn = norm_url(target)
                    if tn in seen:
                        st = self.template_state.get(template_url(target))
                        if self.transitions[i]["to_state"] is None:
                            if st and tn not in refused:
                                self.transitions[i]["to_state"] = st
                                self.transitions[i]["resolved_by_template"] = template_url(target) != template_url(final)
                            elif not self.transitions[i]["unresolved_reason"]:
                                self.transitions[i]["unresolved_reason"] = refused.get(tn, "not_visited")
                        continue
                    if self._refuse(target):
                        # refused targets are recorded once, without a queue round trip
                        reason = self._refuse(target)
                        self.transitions[i]["unresolved_reason"] = reason
                        if tn not in refused:
                            refused[tn] = reason
                            seen.add(tn)
                            self.skipped.append({"role": role.name, "url": target, "reason": reason})
                        continue
                    pending[tn].append(i)
                    queue.append((target, depth + 1, seed))

            if is_new:
                state_elements = self.states[sid]["elements"]
                if self.cfg.expanders and self.cfg.max_expanders_per_state:
                    self._expand(page, recorder, base_rec, sid, final, state_elements, role, depth, deadline)
                self._probe_forms(page, recorder, sid, role, deadline,
                                  restore=lambda u=final: self._restore(page, recorder, u))

        if stop == "queue_empty" and queue:
            stop = "max_minutes" if time.monotonic() > deadline else stop
        for idx_list in pending.values():
            for i in idx_list:
                if self.transitions[i]["to_state"] is None and not self.transitions[i]["unresolved_reason"]:
                    self.transitions[i]["unresolved_reason"] = f"not_visited: {stop}"
        self.stopped_by.setdefault(role.name, stop)
        self.log(f"[deep] role '{role.name}': {visits} page visit(s), stopped by {self.stopped_by[role.name]}")
        recorder.drain_json()
        return ctx, page, recorder

    def _restore(self, page, recorder, url: str, replay: Optional[Dict[str, Any]] = None) -> bool:
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        v = self._visit(page, recorder, url)
        if not v["ok"]:
            return False
        if replay:
            try:
                from tools.test_creation.script_generator.locator_resolve import resolve_entry
                resolve_entry(page, replay).first.click(timeout=3_000)
                page.wait_for_timeout(400)
            except Exception:
                return False
        return True

    # ── expanders ───────────────────────────────────────────────────────
    def _expander_locator(self, page, el: Dict[str, Any]):
        from tools.test_creation.script_generator.build_dom_locator_map import _best_locator_entry
        from tools.test_creation.script_generator.locator_resolve import resolve_entry
        entry = _best_locator_entry(el)
        for candidate in [entry, {"type": "css", "locator": (el.get("technical_locators") or {}).get("css", ""),
                                  **({"frame": el["frame"]["path"]} if el.get("frame") else {})}]:
            if not candidate or not candidate.get("locator"):
                continue
            try:
                loc = resolve_entry(page, candidate)
                if loc.count() == 1:
                    return loc, candidate
            except Exception:
                continue
        return None, None

    def _expand(self, page, recorder, base_rec, sid: str, url: str, elements: List[Dict[str, Any]],
                role: RoleConfig, depth: int, deadline: float) -> None:
        tmpl = template_url(url)
        base_struct = self.states[sid]["structural_hash"]
        done = 0
        for el in elements:
            if done >= self.cfg.max_expanders_per_state or time.monotonic() > deadline:
                break
            if not is_expander(el):
                continue
            name = (el.get("display_text") or "").strip()
            verdict = classify("click", accessible_name=name, role=el.get("aria_role"))
            if verdict.destructive:
                self.skipped.append({"role": role.name, "element": f"{sid}:{name[:80]}", "reason": "destructive"})
                continue
            loc, entry = self._expander_locator(page, el)
            if loc is None:
                self.skipped.append({"role": role.name, "element": f"{sid}:{name[:80]}", "reason": "expander_unresolvable"})
                continue
            done += 1
            base_rec.begin()
            recorder.set_trigger(f"expand {name[:60]}", sid)
            try:
                loc.click(timeout=3_000)
                page.wait_for_timeout(100)
                self._settle(page)
            except Exception:
                self._restore(page, recorder, url)
                continue
            recorder.drain_json()
            ref = {"ref": el["locator_id"], "role": el.get("aria_role"), "name": name[:120], "entry": entry}
            if norm_url(page.url) != norm_url(url):
                self._add_transition({"from_state": sid, "to_state": None, "action": "click", "via": "click",
                                      "element": {**ref, "href": page.url}, "roles": [role.name],
                                      "resolved_by_template": False, "unresolved_reason": "navigated (queued as link)"})
                self._restore(page, recorder, url)
                continue
            try:
                new_elements, struct, _ = self._snapshot(page)
            except Exception:
                self._restore(page, recorder, url)
                continue
            if struct != base_struct:
                rsid = state_id(tmpl, struct)
                is_new = self._register_state(rsid, url, tmpl, page.title(), struct, new_elements, role.name, None,
                                              "reachable", depth, self.states[sid].get("seed"), kind="revealed",
                                              revealed_by={"from_state": sid, "element": ref})
                if is_new and self.cfg.baseline:
                    self.baseline[rsid] = base_rec.snapshot(page, url, role.name, with_timing=False)
                self._add_transition({"from_state": sid, "to_state": rsid, "action": "expand", "via": "click",
                                      "element": ref, "roles": [role.name], "resolved_by_template": False,
                                      "unresolved_reason": None})
                if is_new:
                    self._probe_forms(page, recorder, rsid, role, deadline,
                                      restore=lambda u=url, e=entry: self._restore(page, recorder, u, replay=e))
            self._restore(page, recorder, url)

    # ── forms ───────────────────────────────────────────────────────────
    def _probe_forms(self, page, recorder: NetworkRecorder, sid: str, role: RoleConfig, deadline: float,
                     restore: Callable[[], bool]) -> None:
        guard = self._guards.get(role.name)
        if guard is None:
            return
        state = self.states[sid]
        forms_now = F.tag_forms(page)
        if not forms_now:
            return
        full = self.policy.non_prod
        for form in forms_now:
            if not form.get("visible") and not any(f.get("visible") for f in form.get("fields") or []):
                continue  # a closed dialog / collapsed section: recorded once an expander reveals it
            fp = F.form_fingerprint(state["url_template"], form)
            if fp in self.forms:
                if fp not in state["forms"]:
                    state["forms"].append(fp)
                continue
            submit_text = (form.get("submit") or {}).get("text") or ""
            destructive = classify("click", accessible_name=submit_text, role="button").destructive
            reason = F.skip_reason(form, destructive, self.policy.destructive_allowed)
            if reason is None and not self.cfg.validation.enabled:
                reason = "validation_disabled"
            label = form.get("id") or form.get("aria_label") or submit_text or form.get("kind")
            record = self._form_record(fp, form, state, role.name)
            self.forms[fp] = record
            state["forms"].append(fp)
            if reason:
                record["skipped_probes"].append({"probe": "*", "reason": reason})
                self.skipped_forms.append({"form_id": fp, "state_id": sid, "form": str(label)[:120], "reason": reason})
                continue
            probes, budget_skipped = F.plan_probes(form, self.cfg)
            key_names = {f["key"]: F.field_name(f) for f in form.get("fields") or []}
            for p in probes:
                if time.monotonic() > deadline:
                    record["skipped_probes"].append({"probe": p["probe"], "field": key_names.get(p["field"]),
                                                     "reason": "max_minutes"})
                    continue
                record["probes"].append(F.run_probe(page, fp, state["url_template"], p, restore, recorder, guard,
                                                    write_allowed=full, key_names=key_names,
                                                    settle=lambda: self._settle(page)))
            for s in budget_skipped:
                record["skipped_probes"].append({**s, "field": key_names.get(s.get("field"))})
            for fld in record["fields"]:
                fld["observed_messages"] = F.observed_messages(fld["name"], record["probes"])
            restore()

    def _form_record(self, fp: str, form: Dict[str, Any], state: Dict[str, Any], role: str) -> Dict[str, Any]:
        from tools.test_creation.script_generator.build_dom_locator_map import _best_locator_entry
        by_name = {}
        for el in state["elements"]:
            a = el.get("attribute_locators") or {}
            for k in (a.get("name"), a.get("id")):
                if k and k not in by_name and not el.get("frame"):
                    by_name[k] = el
        fields = []
        for f in form.get("fields") or []:
            el = by_name.get(f.get("name")) or by_name.get(f.get("id"))
            subset = {k: f.get(k) for k in ("type", "required", "aria_required", "maxlength", "minlength", "min", "max",
                                            "step", "pattern", "accept", "multiple", "inputmode", "readonly", "disabled",
                                            "options")}
            fields.append({"name": F.field_name(f), "label": f.get("label") or "", "type": f.get("type") or "",
                           "locator": _best_locator_entry(el) if el else None,
                           "constraints": (el or {}).get("constraints") or subset, "observed_messages": {}})
        submit = form.get("submit") or {}
        return {"form_id": fp, "state_id": state["state_id"], "url": state["url"], "url_template": state["url_template"],
                "role": role, "dom_id": form.get("id") or None, "kind": form.get("kind") or "form", "method": form.get("method") or "get",
                "action": form.get("action"), "novalidate": bool(form.get("novalidate")),
                "submit": {"text": submit.get("text"), "type": submit.get("type"),
                           "destructive": classify("click", accessible_name=submit.get("text") or "", role="button").destructive},
                "fields": fields, "probes": [], "skipped_probes": []}

    # ── union pass ──────────────────────────────────────────────────────
    def _union_pass(self, sessions: Dict[str, Tuple[Any, Any, NetworkRecorder]], deadline: float) -> None:
        union: Dict[str, str] = {}
        for pages in self.role_pages.values():
            for tmpl, p in pages.items():
                if p.get("access") == "reachable" and tmpl not in union:
                    union[tmpl] = p["sample_url"]
        for role in self.roles:
            ctx, page, recorder = sessions.get(role.name, (None, None, None))
            if page is None or self.stopped_by.get(role.name, "").startswith("login_failed"):
                continue
            pages = self.role_pages.setdefault(role.name, {})
            for tmpl, url in sorted(union.items()):
                if tmpl in pages:
                    continue
                if time.monotonic() > deadline:
                    break
                if self._refuse(url):
                    continue
                visit = self._visit(page, recorder, url)
                if not visit["ok"]:
                    continue
                access = classify_visit(url, visit["final_url"], visit["status"])
                elements: List[Dict[str, Any]] = []
                if access == "reachable":
                    try:
                        elements, struct, _ = self._snapshot(page)
                        ftmpl = template_url(visit["final_url"])
                        self._register_state(state_id(ftmpl, struct), visit["final_url"], ftmpl, page.title(), struct,
                                             elements, role.name, visit["status"], access, 0, None)
                    except Exception:
                        elements = []
                pages[tmpl] = {"sample_url": url, "access": access, "via": "deep_link", "status": visit["status"],
                               "final_url": visit["final_url"], "actions": action_keys(elements)}
            recorder.drain_json()

    # ── entry point ─────────────────────────────────────────────────────
    def run(self) -> Dict[str, Any]:
        from playwright.sync_api import sync_playwright

        started = time.monotonic()
        total = self.cfg.max_minutes * 60
        hard_deadline = started + total
        per_role = (total * CRAWL_SHARE) / max(1, len(self.roles))
        self._recorders: List[NetworkRecorder] = []
        self._guards: Dict[str, WriteGuard] = {}
        self._trackers: Dict[int, InflightTracker] = {}
        sessions: Dict[str, Tuple[Any, Any, NetworkRecorder]] = {}
        with sync_playwright() as pw:
            browser = getattr(pw, self.browser_name).launch(headless=self.headless)
            try:
                self.browser_version = f"{self.browser_name} {browser.version}"
                for i, role in enumerate(self.roles):
                    role_deadline = min(hard_deadline, started + per_role * (i + 1))
                    ctx, page, recorder = self._crawl_role(browser, role, role_deadline)
                    sessions[role.name] = (ctx, page, recorder)
                    if page is not None and not self.locale:
                        try:
                            self.locale = page.evaluate("navigator.language")
                        except Exception:
                            pass
                if len(self.roles) > 1:
                    self._union_pass(sessions, hard_deadline)
            finally:
                for ctx, _, _ in sessions.values():
                    try:
                        if ctx is not None:
                            ctx.close()
                    except Exception:
                        pass
                browser.close()
        for r in self._recorders:
            self.network_records.extend(r.records)
        return self._documents(time.monotonic() - started)

    def _documents(self, duration: float) -> Dict[str, Any]:
        now = _now()
        roles_public = [r.public() for r in self.roles]
        states = sorted(self.states.values(), key=lambda s: (s["first_seen_depth"], s["url_template"], s["state_id"]))
        app_map = {
            "project": self.project, "generated_at": now, "config_hash": self.config_hash,
            "seeds": [s["url"] for s in self.seeds], "roles": roles_public,
            "bounds": {"max_pages": self.cfg.max_pages, "max_depth": self.cfg.max_depth,
                       "max_minutes": self.cfg.max_minutes, "samples_per_template": self.cfg.samples_per_template},
            "stopped_by": dict(self.stopped_by), "duration_s": round(duration, 1),
            "states": states, "transitions": self.transitions, "skipped": self.skipped,
            "limitations": list(LIMITATIONS),
        }
        form_model = {
            "project": self.project, "generated_at": now, "environment": self.policy.environment,
            "probe_mode": ("disabled" if not self.cfg.validation.enabled
                           else "full" if self.policy.non_prod else "client_only"),
            "browser": self.browser_version, "locale": self.locale,
            "forms": sorted(self.forms.values(), key=lambda f: (f["url_template"], f["form_id"])),
            "skipped_forms": self.skipped_forms,
        }
        api_inventory = {"project": self.project, "generated_at": now,
                         "endpoints": aggregate(self.network_records) if self.cfg.network else []}
        matrix = build_matrix([{"role": r.name, "pages": self.role_pages.get(r.name, {})} for r in self.roles])
        permission = {"project": self.project, "generated_at": now, **matrix}
        baseline = {"project": self.project, "generated_at": now, "browser": self.browser_version,
                    "states": self.baseline if self.cfg.baseline else {}}
        return {"app_map": app_map, "form_model": form_model, "api_inventory": api_inventory,
                "permission_matrix": permission, "baseline": baseline}
