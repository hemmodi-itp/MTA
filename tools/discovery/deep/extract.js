// extract.js — Phase 2 batched element extraction: ONE evaluate per frame.
//
// Returns {records, stats}. Each record holds the raw facts the legacy scanner gathered
// with ~19 Playwright round trips per element (12 attributes, innerText, associated
// label, visible, enabled, tag name, CSS path, XPath), plus the deep fields: constraints,
// container candidates, ARIA state hints, capture reason, shadow host chain.
//
// Legacy parity rules (tests/unit/test_deep_extract_parity.py):
//   * classic selectors are walked first, selector-major, in the legacy order, and
//     deduplicated by CSS-path string exactly as PlaywrightScanner.scan_page did;
//   * label / CSS path / XPath use the legacy JS verbatim;
//   * visible / enabled mirror Playwright's isElementVisible / getAriaDisabled.
(cfg) => {
  const ATTRS = cfg.attributes;
  const MAX_TEXT_EXTRA = 150;

  // ── Playwright parity: visibility ────────────────────────────────────────
  const styleVisible = (el, style) => {
    if (!style) return true;
    if (Element.prototype.checkVisibility) {
      if (!el.checkVisibility()) return false;
    } else {
      const ds = el.closest('details,summary');
      if (ds !== el && ds && ds.nodeName === 'DETAILS' && !ds.open) return false;
    }
    return style.visibility === 'visible';
  };
  const textNodeVisible = node => {
    const range = node.ownerDocument.createRange();
    range.selectNode(node);
    const rect = range.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const isVisible = el => {
    let style;
    try { style = getComputedStyle(el); } catch (e) { return true; }
    if (!style) return true;
    if (style.display === 'contents') {
      for (let c = el.firstChild; c; c = c.nextSibling) {
        if (c.nodeType === 1 && isVisible(c)) return true;
        if (c.nodeType === 3 && textNodeVisible(c)) return true;
      }
      return false;
    }
    if (!styleVisible(el, style)) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };

  // ── implicit ARIA role (subset Playwright uses; enough for enabled + containers) ──
  const named = el => !!((el.getAttribute('aria-label') || '').trim() || el.getAttribute('aria-labelledby') || el.getAttribute('title'));
  const roleOf = el => {
    const explicit = (el.getAttribute('role') || '').trim().split(/\s+/)[0];
    if (explicit) return explicit.toLowerCase();
    const t = el.tagName;
    if (t === 'BUTTON') return 'button';
    if (t === 'A' || t === 'AREA') return el.hasAttribute('href') ? 'link' : null;
    if (t === 'INPUT') {
      const ty = (el.getAttribute('type') || 'text').toLowerCase();
      if (['button', 'submit', 'reset', 'image'].includes(ty)) return 'button';
      if (ty === 'checkbox') return 'checkbox';
      if (ty === 'radio') return 'radio';
      if (ty === 'range') return 'slider';
      if (ty === 'number') return 'spinbutton';
      if (ty === 'search') return el.hasAttribute('list') ? 'combobox' : 'searchbox';
      if (['email', 'tel', 'text', 'url', ''].includes(ty)) return el.hasAttribute('list') ? 'combobox' : 'textbox';
      if (ty === 'password') return null;
      return null;
    }
    if (t === 'SELECT') return (el.multiple || el.size > 1) ? 'listbox' : 'combobox';
    if (t === 'TEXTAREA') return 'textbox';
    if (t === 'OPTION') return 'option';
    if (t === 'DIALOG') return 'dialog';
    if (t === 'FIELDSET' || t === 'DETAILS' || t === 'OPTGROUP') return 'group';
    if (t === 'NAV') return 'navigation';
    if (t === 'MAIN') return 'main';
    if (t === 'ASIDE') return 'complementary';
    if (t === 'ARTICLE') return 'article';
    if (t === 'FORM') return named(el) ? 'form' : null;
    if (t === 'SECTION') return named(el) ? 'region' : null;
    if (t === 'HEADER') return el.parentElement && el.parentElement.closest('article,aside,main,nav,section') ? null : 'banner';
    if (t === 'FOOTER') return el.parentElement && el.parentElement.closest('article,aside,main,nav,section') ? null : 'contentinfo';
    if (t === 'LI') return 'listitem';
    if (t === 'UL' || t === 'OL' || t === 'MENU') return 'list';
    if (t === 'TR') return 'row';
    if (t === 'TABLE') return 'table';
    return null;
  };

  // ── Playwright parity: enabled = !getAriaDisabled ───────────────────────
  const ARIA_DISABLED_ROLES = new Set(['application', 'button', 'composite', 'gridcell', 'group', 'input', 'link', 'menuitem',
    'scrollbar', 'separator', 'tab', 'checkbox', 'columnheader', 'combobox', 'grid', 'listbox', 'menu', 'menubar',
    'menuitemcheckbox', 'menuitemradio', 'option', 'radio', 'radiogroup', 'row', 'rowheader', 'searchbox', 'select',
    'slider', 'spinbutton', 'switch', 'tablist', 'textbox', 'toolbar', 'tree', 'treegrid', 'treeitem']);
  const parentOrHost = el => el.parentElement || (el.parentNode && el.parentNode.host) || null;
  const nativelyDisabled = el => {
    if (!['BUTTON', 'INPUT', 'SELECT', 'TEXTAREA', 'OPTION', 'OPTGROUP'].includes(el.tagName)) return false;
    if (el.hasAttribute('disabled')) return true;
    if (el.tagName === 'OPTION' && el.closest('OPTGROUP[DISABLED]')) return true;
    const fs = el.closest('FIELDSET[DISABLED]');
    if (!fs) return false;
    const legend = fs.querySelector(':scope > LEGEND');
    return !legend || !legend.contains(el);
  };
  const explicitAriaDisabled = (el, isAncestor) => {
    if (!el) return false;
    if (isAncestor || ARIA_DISABLED_ROLES.has(roleOf(el) || '')) {
      const a = (el.getAttribute('aria-disabled') || '').toLowerCase();
      if (a === 'true') return true;
      if (a === 'false') return false;
      return explicitAriaDisabled(parentOrHost(el), true);
    }
    return false;
  };
  const isEnabled = el => !(nativelyDisabled(el) || explicitAriaDisabled(el, false));

  // ── legacy label / CSS path / XPath (verbatim logic) ────────────────────
  const legacyLabel = el => {
    try {
      const root = el.getRootNode();
      if (el.id) {
        const label = root.querySelector(`label[for="${el.id}"]`);
        if (label) return label.innerText.trim();
      }
      const parentLabel = el.closest('label');
      if (parentLabel) return parentLabel.innerText.trim();
      return '';
    } catch (e) { return ''; }
  };
  const legacyCss = element => {
    if (element.id) return '#' + element.id;
    let path = '';
    while (element && element.nodeType === Node.ELEMENT_NODE) {
      let name = element.nodeName.toLowerCase();
      let index = 1;
      let sibling = element.previousElementSibling;
      while (sibling) {
        if (sibling.nodeName === element.nodeName) index += 1;
        sibling = sibling.previousElementSibling;
      }
      path = name + (index > 1 ? ':' + 'nth-of-type(' + index + ')' : '') + (path ? '>' + path : '');
      if (element.id) break;
      element = element.parentElement;
    }
    return path;
  };
  const legacyXpath = element => {
    if (element.id) return `//*[@id="${element.id}"]`;
    const getPath = el => {
      if (!el || el.nodeType !== Node.ELEMENT_NODE) return '';
      let index = 1;
      let sibling = el.previousElementSibling;
      while (sibling) {
        if (sibling.nodeName === el.nodeName) index++;
        sibling = sibling.previousElementSibling;
      }
      return getPath(el.parentElement) + '/' + el.nodeName.toLowerCase() + '[' + index + ']';
    };
    return getPath(element);
  };

  // ── roots: document + open shadow roots (recursively) ───────────────────
  const roots = [];
  const collectRoots = (root, hosts) => {
    roots.push({ root, hosts });
    if (!cfg.shadow) return;
    for (const el of root.querySelectorAll('*')) {
      if (el.shadowRoot) collectRoots(el.shadowRoot, hosts.concat([el]));
    }
  };
  collectRoots(document, []);

  const cssFor = (el, hosts) => {
    const inner = legacyCss(el);
    if (!hosts.length) return inner;
    return hosts.map(h => legacyCss(h)).join(' ') + ' ' + inner;
  };

  // ── constraints (2.2) ───────────────────────────────────────────────────
  const FORM_ROLES = new Set(['textbox', 'searchbox', 'spinbutton', 'slider', 'combobox', 'checkbox', 'radio', 'switch', 'listbox']);
  const isNative = el => ['INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName);
  const isEditable = el => el.hasAttribute('contenteditable') && el.getAttribute('contenteditable') !== 'false';
  const isControl = el => isNative(el) || isEditable(el) || FORM_ROLES.has((el.getAttribute('role') || '').trim().toLowerCase());
  const attrOrNull = (el, a) => el.hasAttribute(a) ? el.getAttribute(a) : null;
  const intOrNull = v => (v !== null && /^\s*\d+\s*$/.test(v)) ? parseInt(v, 10) : null;
  const textById = (root, ids) => (ids || '').split(/\s+/).filter(Boolean).map(id => {
    const n = (root.getElementById ? root.getElementById(id) : null) || document.getElementById(id);
    return { id, text: n ? ((n.innerText || n.textContent || '').trim()).slice(0, 300) : null };
  });
  const constraintsOf = el => {
    const t = el.tagName;
    const native = isNative(el);
    const roleAttr = (el.getAttribute('role') || '').trim().toLowerCase();
    const type = t === 'INPUT' ? (el.getAttribute('type') || 'text').toLowerCase()
      : t === 'SELECT' ? 'select' : t === 'TEXTAREA' ? 'textarea' : isEditable(el) ? 'contenteditable' : (roleAttr || null);
    const root = el.getRootNode();
    const c = {
      type, source: native ? 'html' : 'aria',
      inputmode: el.getAttribute('inputmode'), autocomplete: el.getAttribute('autocomplete'),
      required: native ? el.hasAttribute('required') : false,
      aria_required: el.getAttribute('aria-required') === 'true',
      maxlength: intOrNull(attrOrNull(el, 'maxlength')), minlength: intOrNull(attrOrNull(el, 'minlength')),
      pattern: attrOrNull(el, 'pattern'),
      min: native ? attrOrNull(el, 'min') : attrOrNull(el, 'aria-valuemin'),
      max: native ? attrOrNull(el, 'max') : attrOrNull(el, 'aria-valuemax'),
      step: attrOrNull(el, 'step'),
      accept: attrOrNull(el, 'accept'), multiple: el.hasAttribute('multiple'),
      readonly: el.hasAttribute('readonly') || el.getAttribute('aria-readonly') === 'true',
      disabled: el.hasAttribute('disabled') || el.getAttribute('aria-disabled') === 'true',
      aria_invalid: el.getAttribute('aria-invalid'),
      default_value: null, default_checked: null, options: null, options_truncated: false,
      radio_group: null, error_container: null, form: null,
    };
    c.effective_required = c.required || c.aria_required;
    if (t === 'INPUT' && (type === 'checkbox' || type === 'radio')) {
      c.default_checked = !!el.defaultChecked;
      c.default_value = el.getAttribute('value');
    } else if (t === 'INPUT' || t === 'TEXTAREA') {
      c.default_value = type === 'file' || type === 'password' ? null : (el.defaultValue || null);
    }
    const optionList = t === 'SELECT' ? [...el.options] : (t === 'INPUT' && el.list ? [...el.list.options] : null);
    if (optionList) {
      c.options = optionList.slice(0, 200).map(o => ({ value: o.value, text: (o.text || '').trim(), disabled: !!o.disabled,
        selected: !!o.defaultSelected }));
      c.options_truncated = optionList.length > 200;
      if (t === 'SELECT') {
        const d = optionList.find(o => o.defaultSelected) || optionList[0];
        c.default_value = d ? d.value : null;
      }
    }
    if (t === 'INPUT' && type === 'radio' && el.name) {
      const scope = el.form || root;
      let members = [];
      try { members = [...scope.querySelectorAll(`input[type=radio][name="${CSS.escape(el.name)}"]`)]; } catch (e) { members = [el]; }
      c.radio_group = { name: el.name, members: members.slice(0, 50).map(m => ({ value: m.getAttribute('value'),
        label: legacyLabel(m), checked: !!m.defaultChecked })) };
    }
    const describedby = el.getAttribute('aria-describedby');
    const errormessage = el.getAttribute('aria-errormessage');
    if (describedby || errormessage) {
      c.error_container = { describedby: describedby ? textById(root, describedby) : [],
        errormessage: errormessage ? textById(root, errormessage)[0] || null : null };
    }
    const form = el.form || el.closest('form');
    if (form) {
      c.form = { id: form.getAttribute('id'), name: form.getAttribute('name'), novalidate: !!form.noValidate,
        method: (form.getAttribute('method') || 'get').toLowerCase(), action: form.getAttribute('action') };
    }
    return c;
  };

  // ── containers (2.1 scoped locators) ────────────────────────────────────
  const CONTAINER_ROLES = new Set(['dialog', 'alertdialog', 'form', 'region', 'navigation', 'main', 'complementary',
    'banner', 'contentinfo', 'search', 'group', 'article', 'tabpanel', 'menu', 'toolbar', 'row']);
  const accName = (a, role) => {
    const root = a.getRootNode();
    const lb = a.getAttribute('aria-labelledby');
    if (lb) {
      const t = textById(root, lb).map(x => x.text || '').filter(Boolean).join(' ');
      if (t) return t;
    }
    const al = (a.getAttribute('aria-label') || '').trim();
    if (al) return al;
    if (a.tagName === 'FIELDSET') {
      const lg = a.querySelector(':scope > legend');
      if (lg) return (lg.innerText || lg.textContent || '').replace(/\s+/g, ' ').trim();
    }
    if (role === 'row') return (a.innerText || a.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 200);
    const title = (a.getAttribute('title') || '').trim();
    return title || '';
  };
  const containersOf = el => {
    const out = [];
    let a = parentOrHost(el);
    while (a && a.nodeType === 1 && out.length < 4) {
      const role = roleOf(a);
      if (role && CONTAINER_ROLES.has(role)) {
        out.push({ role, name: accName(a, role) || null, kind: a.tagName.toLowerCase() });
      }
      a = parentOrHost(a);
    }
    return out;
  };

  // ── selection ───────────────────────────────────────────────────────────
  const records = [];
  const seen = new Set();
  const seenCss = new Set();
  let index = cfg.start_index || 0;
  const INTERACTIVE = 'input,button,select,textarea,a,[role=combobox],[role=button],[role=link],[role=tab],[role=menuitem],'
    + '[role=menuitemcheckbox],[role=menuitemradio],[role=checkbox],[role=radio],[role=switch],[role=slider],'
    + '[role=spinbutton],[role=option],[role=treeitem],[role=searchbox],[role=textbox],[contenteditable],[onclick],summary';

  const take = (el, tag, reason, hosts) => {
    if (seen.has(el)) return;
    const css = cssFor(el, hosts);
    if (!css || seenCss.has(css)) { seen.add(el); return; }
    seen.add(el);
    seenCss.add(css);
    const values = {};
    for (const a of ATTRS) values[a] = el.getAttribute(a);
    let text = '';
    if (el instanceof HTMLElement) { try { text = el.innerText || ''; } catch (e) { text = ''; } }
    if (tag === null && text.length > MAX_TEXT_EXTRA) text = text.slice(0, MAX_TEXT_EXTRA);
    let visible = false, enabled = false;
    try { visible = isVisible(el); enabled = isEnabled(el); } catch (e) { visible = false; enabled = false; }
    el.__mtaIdx = index;
    records.push({
      index, tag, reason, values, text, label: legacyLabel(el), visible, enabled,
      tag_name: el.tagName.toLowerCase(), css, xpath: hosts.length ? null : legacyXpath(el),
      in_shadow: hosts.length > 0,
      href: ((el.tagName === 'A' || el.tagName === 'AREA') && el.hasAttribute('href')) ? el.href : null,
      aria_role: roleOf(el),
      constraints: isControl(el) ? constraintsOf(el) : null,
      containers: containersOf(el),
      state: { expanded: el.getAttribute('aria-expanded'), haspopup: el.getAttribute('aria-haspopup'),
        controls: el.getAttribute('aria-controls'), toggle: el.getAttribute('data-bs-toggle') || el.getAttribute('data-toggle'),
        type: (el.getAttribute('type') || '').toLowerCase(), open: el.tagName === 'DETAILS' ? !!el.open : null },
    });
    index += 1;
  };

  // 1. classic selectors, selector-major (legacy order), document first, then shadow roots
  for (const [selector, tag] of cfg.classic) {
    for (const { root, hosts } of roots) {
      for (const el of root.querySelectorAll(selector)) take(el, tag, 'classic', hosts);
    }
  }
  // 2. the wider set
  for (const [selector, reason] of cfg.extra) {
    for (const { root, hosts } of roots) {
      let list = [];
      try { list = root.querySelectorAll(selector); } catch (e) { list = []; }
      for (const el of list) take(el, null, reason, hosts);
    }
  }
  // 3. cursor:pointer elements with no interactive ancestor or descendant (outermost only)
  let pointerCount = 0;
  const NON_CONTENT = new Set(['HTML', 'HEAD', 'BODY', 'SCRIPT', 'STYLE', 'META', 'LINK', 'TITLE', 'NOSCRIPT', 'TEMPLATE']);
  if (cfg.cursor_pointer) {
    outer:
    for (const { root, hosts } of roots) {
      for (const el of root.querySelectorAll('*')) {
        if (pointerCount >= cfg.max_pointer) break outer;
        if (seen.has(el) || !(el instanceof HTMLElement) || NON_CONTENT.has(el.tagName)) continue;
        let style;
        try { style = getComputedStyle(el); } catch (e) { continue; }
        if (style.cursor !== 'pointer') continue;
        const parent = el.parentElement;
        if (parent) { try { if (getComputedStyle(parent).cursor === 'pointer') continue; } catch (e) { /* ignore */ } }
        if (el.closest(INTERACTIVE) || el.querySelector(INTERACTIVE)) continue;
        take(el, null, 'cursor_pointer', hosts);
        pointerCount += 1;
      }
    }
  }
  return { records, stats: { roots: roots.length, shadow_roots: roots.length - 1, pointer: pointerCount,
                              pointer_capped: pointerCount >= cfg.max_pointer && cfg.cursor_pointer } };
}
