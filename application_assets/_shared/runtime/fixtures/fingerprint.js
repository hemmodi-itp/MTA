// fingerprint.js — the identity of one element (Phase 6.3), evaluated in the page.
// ONE source for both sides: tools/healing/identity.py (healing, capture) reads this file, and
// ActionEngine.ts (the failure-time identity probe) reads it too. Plain JS: no imports, no TS syntax.
// Fingerprint = tag, role (explicit or implicit), accessible name, associated label, container (closest
// form/nav/main/... by its accessible name, not its id), position among same-tag peers in that container, and
// attrs (id / test id / name / type — tie-break only; they are what a locator change renames).
function mtaFingerprint(el) {
  const tag = el.tagName.toLowerCase();
  const type = (el.getAttribute('type') || '').toLowerCase();
  const implicit = () => {
    if (tag === 'button') return 'button';
    if (tag === 'a' && el.hasAttribute('href')) return 'link';
    if (tag === 'select') return el.multiple ? 'listbox' : 'combobox';
    if (tag === 'textarea') return 'textbox';
    if (tag === 'input') {
      if (['submit', 'button', 'reset', 'image'].includes(type)) return 'button';
      if (type === 'checkbox' || type === 'radio') return type;
      if (type === 'number') return 'spinbutton';
      if (type === 'hidden') return '';
      return 'textbox';
    }
    if (/^h[1-6]$/.test(tag)) return 'heading';
    return {img: 'img', li: 'listitem', ul: 'list', ol: 'list', nav: 'navigation', form: 'form', table: 'table',
            main: 'main', dialog: 'dialog', p: 'paragraph'}[tag] || '';
  };
  const role = (el.getAttribute('role') || implicit()).toLowerCase();
  const text = (n) => (n && n.textContent || '').replace(/\s+/g, ' ').trim();
  const doc = el.ownerDocument;
  let label = '';
  if (el.id) {
    const l = doc.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    if (l) label = text(l);
  }
  if (!label && el.closest('label')) label = text(el.closest('label'));
  const byIds = (attr) => (el.getAttribute(attr) || '').split(/\s+/).filter(Boolean)
      .map((id) => text(doc.getElementById(id))).join(' ').trim();
  let name = el.getAttribute('aria-label') || byIds('aria-labelledby') || '';
  if (!name && ['button', 'link', 'heading', 'listitem', 'paragraph', 'tab', 'menuitem', 'option'].includes(role)) name = text(el);
  if (!name) name = label || el.getAttribute('placeholder') || el.getAttribute('title') || el.getAttribute('alt') ||
      (tag === 'input' && ['submit', 'button'].includes(type) ? el.value : '') || '';
  // container = the landmark path down to the element ("main>form|Add product"): wrappers such as div, fieldset
  // or section are not landmarks, so wrapping an element does not move it; position counts peers in that container.
  const LANDMARKS = 'form, nav, main, header, footer, aside, dialog, [role=dialog], [role=search], table';
  const box = el.parentElement ? el.parentElement.closest(LANDMARKS) : null;
  const named = (b) => {
    const legend = b.querySelector(':scope > legend');
    const heading = b.querySelector('h1, h2, h3');
    const cname = b.getAttribute('aria-label') || (legend ? text(legend) : '') ||
        (b.tagName === 'FORM' && heading ? text(heading) : '');
    return cname.slice(0, 60);
  };
  const path = [];
  for (let b = box; b; b = b.parentElement ? b.parentElement.closest(LANDMARKS) : null) path.unshift(b.tagName.toLowerCase());
  const container = box ? `${path.join('>')}|${named(box)}` : '';
  const scope = box || doc.body;
  const peers = [...scope.querySelectorAll(tag)].filter((p) =>
      (p.parentElement ? p.parentElement.closest(LANDMARKS) : null) === box);
  return {
    tag, role, name: name.slice(0, 120), label: label.slice(0, 120), container,
    position: [peers.indexOf(el), peers.length],
    attrs: {id: el.id || '', testid: el.getAttribute('data-testid') || el.getAttribute('data-test') || '',
            name: el.getAttribute('name') || '', type},
  };
}
