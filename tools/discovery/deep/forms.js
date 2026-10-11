// forms.js — Phase 2 task 2.3 helpers, one evaluate per call.
//   mode "tag"    : find <form>s and virtual forms, mark fields (data-mta-field) and submit buttons
//                   (data-mta-submit), return descriptors
//   mode "state"  : native validity + validationMessage per marked field, aria-invalid, focus
//   mode "errors" : visible error texts with field attribution
([mode, arg]) => {
  const vis = el => { if (!el) return false; const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const FILLABLE = 'input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=reset]):not([type=image]),select,textarea,[contenteditable]:not([contenteditable="false"])';
  const SUBMITS = 'button:not([type=button]):not([type=reset]),input[type=submit],input[type=image]';
  const BUTTONS = 'button,[role=button],input[type=submit],input[type=button]';
  const txt = el => ((el.innerText || el.value || '').trim() || el.getAttribute('aria-label') || el.getAttribute('title') || '').replace(/\s+/g, ' ').slice(0, 120);
  const labelOf = el => {
    if (el.labels && el.labels[0]) { const c = el.labels[0].cloneNode(true);
      c.querySelectorAll('input,select,textarea,option,button').forEach(n => n.remove());
      return (c.textContent || '').replace(/\s+/g, ' ').trim(); }
    const lb = el.getAttribute('aria-labelledby');
    if (lb) { const n = document.getElementById(lb.split(/\s+/)[0]); if (n) return (n.innerText || '').trim(); }
    return (el.getAttribute('aria-label') || el.getAttribute('placeholder') || '').trim();
  };
  const fieldInfo = (el, key) => {
    const t = el.tagName;
    const type = t === 'INPUT' ? (el.getAttribute('type') || 'text').toLowerCase() : t === 'SELECT' ? 'select'
      : t === 'TEXTAREA' ? 'textarea' : 'contenteditable';
    const a = n => el.hasAttribute(n) ? el.getAttribute(n) : null;
    return {
      key, tag: t.toLowerCase(), type, name: el.getAttribute('name') || '', id: el.id || '', label: labelOf(el).slice(0, 120),
      required: el.hasAttribute('required'), aria_required: el.getAttribute('aria-required') === 'true',
      maxlength: a('maxlength') !== null && /^\d+$/.test(a('maxlength')) ? parseInt(a('maxlength'), 10) : null,
      minlength: a('minlength') !== null && /^\d+$/.test(a('minlength')) ? parseInt(a('minlength'), 10) : null,
      min: a('min'), max: a('max'), step: a('step'), pattern: a('pattern'), accept: a('accept'),
      multiple: el.hasAttribute('multiple'), inputmode: a('inputmode'),
      readonly: el.hasAttribute('readonly'), disabled: el.disabled === true || el.hasAttribute('disabled'),
      visible: vis(el),
      options: t === 'SELECT' ? [...el.options].map(o => ({ value: o.value, text: (o.text || '').trim(), disabled: !!o.disabled })) : null,
    };
  };

  if (mode === 'tag') {
    document.querySelectorAll('[data-mta-field]').forEach(n => n.removeAttribute('data-mta-field'));
    document.querySelectorAll('[data-mta-submit]').forEach(n => n.removeAttribute('data-mta-submit'));
    const forms = [];
    const real = [...document.querySelectorAll('form')];
    real.forEach((f, i) => {
      const fields = [...f.querySelectorAll(FILLABLE)].concat([...document.querySelectorAll(`[form="${CSS.escape(f.id || '__none__')}"]`)].filter(e => e.matches(FILLABLE)));
      const uniq = [...new Set(fields)];
      const descs = uniq.map((el, j) => { const key = `f${i}-${j}`; el.setAttribute('data-mta-field', key); return fieldInfo(el, key); });
      const submit = [...f.querySelectorAll(SUBMITS)].find(vis) || [...f.querySelectorAll(SUBMITS)][0] || null;
      if (submit) submit.setAttribute('data-mta-submit', `f${i}`);
      forms.push({ index: i, kind: 'form', id: f.id || '', name: f.getAttribute('name') || '', aria_label: f.getAttribute('aria-label') || '',
        method: (f.getAttribute('method') || 'get').toLowerCase(), action: f.getAttribute('action'), novalidate: !!f.noValidate,
        visible: vis(f), role: f.getAttribute('role') || '',
        submit: submit ? { key: `f${i}`, text: txt(submit), type: (submit.getAttribute('type') || 'submit').toLowerCase() } : null,
        fields: descs });
    });
    // virtual forms: visible fillable fields outside any <form>, grouped by the nearest ancestor holding a button
    const loose = [...document.querySelectorAll(FILLABLE)].filter(el => !el.closest('form') && !el.getAttribute('form') && vis(el));
    const groups = new Map();
    for (const el of loose) {
      let a = el.parentElement, depth = 0;
      while (a && depth < 6 && !([...a.querySelectorAll(BUTTONS)].some(vis))) { a = a.parentElement; depth++; }
      if (!a || depth >= 6) continue;
      if (!groups.has(a)) groups.set(a, []);
      groups.get(a).push(el);
    }
    let v = real.length;
    for (const [container, els] of groups) {
      const i = v++;
      const descs = els.map((el, j) => { const key = `f${i}-${j}`; el.setAttribute('data-mta-field', key); return fieldInfo(el, key); });
      const btn = [...container.querySelectorAll(BUTTONS)].find(vis);
      if (btn) btn.setAttribute('data-mta-submit', `f${i}`);
      forms.push({ index: i, kind: 'virtual', id: container.id || '', name: '', aria_label: container.getAttribute('aria-label') || '',
        method: '', action: null, novalidate: true, visible: true, role: container.getAttribute('role') || '',
        submit: btn ? { key: `f${i}`, text: txt(btn), type: (btn.getAttribute('type') || 'button').toLowerCase() } : null,
        fields: descs });
    }
    return forms;
  }

  const fields = [...document.querySelectorAll('[data-mta-field]')];
  if (mode === 'state') {
    const prefix = arg ? `f${arg}-` : null;
    const mine = fields.filter(el => !prefix || el.getAttribute('data-mta-field').startsWith(prefix));
    const messages = {};
    let anyInvalid = false;
    for (const el of mine) {
      const key = el.getAttribute('data-mta-field');
      if (el.validity && !el.validity.valid) { anyInvalid = true; messages[key] = el.validationMessage || 'invalid'; }
      else messages[key] = null;
    }
    const ariaInvalid = mine.filter(el => el.getAttribute('aria-invalid') === 'true').map(el => el.getAttribute('data-mta-field'));
    const ae = document.activeElement;
    const focused = ae && ae !== document.body ? (ae.getAttribute('data-mta-field') || (ae.tagName.toLowerCase() + (ae.id ? '#' + ae.id : ''))) : null;
    const form = mine[0] ? (mine[0].form || null) : null;
    return { messages, any_invalid: anyInvalid, novalidate: form ? !!form.noValidate : true, aria_invalid: ariaInvalid, focused };
  }

  if (mode === 'errors') {
    const CAND = '[role=alert],[aria-live]:not([aria-live=off]),[class*=error i],[class*=invalid i],[id*=error i],.invalid-feedback,[class*=help i]';
    const refs = new Map();
    for (const el of fields) {
      for (const at of ['aria-describedby', 'aria-errormessage']) {
        for (const id of (el.getAttribute(at) || '').split(/\s+/).filter(Boolean)) {
          const n = document.getElementById(id); if (n) refs.set(n, el.getAttribute('data-mta-field'));
        }
      }
    }
    let nodes = [...document.querySelectorAll(CAND)].concat([...refs.keys()]);
    nodes = [...new Set(nodes)].filter(n => vis(n) && !n.matches(FILLABLE) && !n.matches(BUTTONS));
    const set = new Set(nodes);
    const leaves = nodes.filter(n => ![...set].some(o => o !== n && n.contains(o)));
    const labels = fields.map(el => ({ key: el.getAttribute('data-mta-field'), label: labelOf(el).toLowerCase(),
      name: (el.getAttribute('name') || '').toLowerCase() }));
    const describe = n => n.tagName.toLowerCase() + (n.id ? '#' + n.id : '') + (n.classList[0] ? '.' + n.classList[0] : '');
    const out = [];
    const seenText = new Set();
    for (const n of leaves) {
      const items = [...n.querySelectorAll('li')].filter(vis);
      const texts = items.length ? items.map(li => (li.innerText || '').trim()) : [(n.innerText || '').trim()];
      const role = n.getAttribute('role') || (n.closest('[role=alert]') ? 'alert' : null);
      for (const raw of texts) {
        const text = raw.replace(/\s+/g, ' ');
        if (text.length < 2 || text.length > 300 || seenText.has(text)) continue;
        seenText.add(text);
        let field = null, attribution = null;
        let a = n;
        while (a && !field) { if (refs.has(a)) { field = refs.get(a); attribution = 'aria'; } a = a.parentElement; }
        if (!field) {
          let p = n.parentElement, depth = 0;
          while (p && depth < 3 && !field) {
            const inside = [...p.querySelectorAll('[data-mta-field]')];
            if (inside.length === 1) { field = inside[0].getAttribute('data-mta-field'); attribution = 'proximity'; }
            if (inside.length > 1) break;
            p = p.parentElement; depth++;
          }
        }
        if (!field) {
          const low = text.toLowerCase();
          const hits = new Set();
          for (const l of labels) {
            for (const cand of [l.label, l.name]) {
              if (cand && cand.length >= 3 && new RegExp('\\b' + cand.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\b').test(low)) hits.add(l.key);
            }
          }
          if (hits.size === 1) { field = [...hits][0]; attribution = 'text_mentions_label'; }
          else if (hits.size > 1) { attribution = 'mentions_multiple_fields'; }
        }
        out.push({ text, container: describe(n), role, field, attribution });
      }
    }
    return out;
  }
  return null;
}
