/* MDMP harness — front end.
   Vanilla JS, no build step, no dependencies. Served straight off disk. */

'use strict';

const S = {
  user: null, flow: null, doctrine: null,
  view: 'plans', planId: null, plan: null, answers: {}, state: null,
  meta: {}, role: null, canPlan: false, canApprove: false,
  stepKey: null, options: {}, busy: {}, pulseSince: 0, pulseTimer: null,
  sections: [], tab: 'plan', provider: '', online: [],
};

const $ = (sel, root) => (root || document).querySelector(sel);
const el = (tag, attrs, ...kids) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') n.className = v;
    else if (k === 'html') n.innerHTML = v;
    else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
    else if (k === 'text') n.textContent = v;
    else n.setAttribute(k, v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    n.appendChild(typeof kid === 'string' ? document.createTextNode(kid) : kid);
  }
  return n;
};

/* ------------------------------------------------------------------ net */

async function api(path, opts) {
  const res = await fetch(path, Object.assign({
    headers: { 'Content-Type': 'application/json' },
  }, opts || {}));
  const ctype = res.headers.get('Content-Type') || '';
  if (!ctype.includes('json')) {
    const text = await res.text();
    if (!res.ok) throw new Error(text.slice(0, 200));
    return text;
  }
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
  return data;
}
const post = (p, body) => api(p, { method: 'POST', body: JSON.stringify(body || {}) });

let toastTimer = null;
function toast(msg) {
  let t = $('.toast');
  if (!t) { t = el('div', { class: 'toast' }); document.body.appendChild(t); }
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 2600);
}

/* --------------------------------------------------------------- render */

function render() {
  const app = $('#app');
  app.textContent = '';
  if (!S.user) return app.appendChild(S.needsSetup ? viewSetup() : viewLogin());
  app.appendChild(topBar());
  const wrap = el('div', { class: 'wrap' });
  if (S.view === 'plans') wrap.appendChild(viewPlans());
  else if (S.view === 'plan') wrap.appendChild(viewPlan());
  else if (S.view === 'settings') wrap.appendChild(viewSettings());
  app.appendChild(wrap);
}

function topBar() {
  const bits = [
    el('span', { class: 'brand', text: 'MDMP Harness',
      onclick: () => { S.view = 'plans'; stopPulse(); loadPlans(); } }),
  ];
  if (S.plan && S.view === 'plan') {
    bits.push(el('span', { class: 'planname', text: S.plan.name }));
    bits.push(el('span', { class: 'chip', text: S.plan.phase === 'planning'
      ? 'Planning' : (S.plan.phase === 'production' ? 'Staff production' : 'Published') }));
  }
  bits.push(el('span', { class: 'spacer' }));
  if (S.online.length > 1) {
    bits.push(el('span', { class: 'chip live',
      text: S.online.length + ' online' }));
  }
  if (S.provider) bits.push(el('span', { class: 'chip', text: S.provider }));
  bits.push(el('span', { class: 'chip', text: S.user.display_name + ' · ' + S.user.role }));
  if (S.user.role === 'admin') {
    bits.push(el('button', { class: 'ghost', text: 'Settings',
      onclick: () => { S.view = 'settings'; stopPulse(); render(); } }));
  }
  bits.push(el('button', { class: 'ghost', text: 'Sign out', onclick: logout }));
  return el('div', { class: 'top' }, bits);
}

/* ---------------------------------------------------------------- login */

function viewLogin() {
  const u = el('input', { type: 'text', id: 'u', placeholder: 'username' });
  const p = el('input', { type: 'password', id: 'p', placeholder: 'password' });
  const err = el('div', { class: 'err' });
  const go = async () => {
    err.textContent = '';
    try {
      const r = await post('/api/login', { username: u.value, password: p.value });
      S.user = r.user; await boot();
    } catch (e) { err.textContent = e.message; }
  };
  p.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
  return el('div', { class: 'center' },
    el('div', { class: 'card' },
      el('h2', { text: 'MDMP Harness' }),
      el('p', { class: 'muted small', text: 'Sign in to plan.' }),
      el('label', { class: 'lab', text: 'Username' }), u,
      el('label', { class: 'lab', text: 'Password' }), p,
      el('div', { style: 'margin-top:1rem' },
        el('button', { class: 'primary wide', text: 'Sign in', onclick: go })),
      err));
}

function viewSetup() {
  const f = {};
  const mk = (k, label, type) => {
    f[k] = el('input', { type: type || 'text' });
    return [el('label', { class: 'lab', text: label }), f[k]];
  };
  const err = el('div', { class: 'err' });
  const go = async () => {
    err.textContent = '';
    try {
      const r = await post('/api/setup', {
        username: f.u.value, password: f.p.value, display_name: f.d.value,
      });
      S.user = r.user; S.needsSetup = false; await boot();
    } catch (e) { err.textContent = e.message; }
  };
  return el('div', { class: 'center' },
    el('div', { class: 'card' },
      el('h2', { text: 'First run' }),
      el('p', { class: 'muted small', text:
        'This server has no accounts yet. Create the administrator account — '
        + 'everyone else can be added from Settings afterwards.' }),
      mk('u', 'Username'), mk('d', 'Display name'),
      mk('p', 'Password (6+ characters)', 'password'),
      el('div', { style: 'margin-top:1rem' },
        el('button', { class: 'primary wide', text: 'Create account', onclick: go })),
      err));
}

async function logout() {
  await post('/api/logout');
  S.user = null; stopPulse(); render();
}

/* ---------------------------------------------------------------- plans */

function viewPlans() {
  const name = el('input', { type: 'text', placeholder: 'e.g. OPERATION IRON ANVIL' });
  const create = async () => {
    if (!name.value.trim()) return toast('Give the plan a name');
    const r = await post('/api/plans', { name: name.value.trim() });
    openPlan(r.id);
  };
  const list = (S.plans || []).map((p) => {
    const pct = p.progress ? Math.round(100 * p.progress.complete / p.progress.total) : 0;
    return el('div', { class: 'brow', style: 'cursor:pointer',
      onclick: () => openPlan(p.id) },
      el('div', {},
        el('div', { class: 'btitle', text: p.name }),
        el('div', { class: 'tiny muted', text:
          'started by ' + p.owner + ' · updated ' + when(p.updated_at) })),
      el('div', {},
        el('div', { class: 'tiny muted', text:
          p.progress.complete + ' of ' + p.progress.total + ' steps' }),
        el('div', { class: 'progress' }, el('i', { style: 'width:' + pct + '%' }))),
      el('div', { class: 'st ' + (p.phase === 'planning' ? 'in_progress' : 'approved'),
        text: p.phase === 'planning' ? 'Planning' : (p.phase === 'production' ? 'Staff production' : 'Published') }),
      el('div', { class: 'tiny muted', text: '#' + p.id }));
  });
  return el('div', {},
    el('div', { class: 'card' },
      el('h2', { text: 'Plans' }),
      el('p', { class: 'muted small', text:
        'Each plan runs the seven steps of MDMP and ends in a five-paragraph '
        + 'operation order. Anyone signed in to this server can open one.' }),
      el('div', { class: 'row', style: 'margin-top:.8rem' },
        el('div', { style: 'flex:1;min-width:220px' }, name),
        el('button', { class: 'primary', text: 'Start a new plan', onclick: create }))),
    el('div', { class: 'card' },
      el('h3', { text: 'Open plans' }),
      list.length ? el('div', { class: 'board' }, list)
        : el('p', { class: 'muted small', text: 'Nothing yet.' })));
}

async function loadPlans() {
  const r = await api('/api/plans');
  S.plans = r.plans; S.view = 'plans'; render();
}

async function openPlan(id) {
  S.planId = id;
  const r = await api('/api/plans/' + id);
  S.plan = r.plan; S.answers = r.answers; S.state = r.state; S.meta = r.meta;
  S.role = r.role; S.canPlan = r.can_plan; S.canApprove = r.can_approve;
  S.provider = r.provider; S.completeness = r.completeness;
  S.stepKey = S.stepKey && S.flow.steps.some((s) => s.key === S.stepKey)
    ? S.stepKey : r.state.current;
  S.view = 'plan';
  S.tab = S.plan.phase === 'planning' ? 'plan' : 'produce';
  S.options = {};
  render();
  startPulse();
}

async function refreshPlan() {
  const r = await api('/api/plans/' + S.planId);
  S.plan = r.plan; S.answers = r.answers; S.state = r.state; S.meta = r.meta;
  S.completeness = r.completeness;
}

/* --------------------------------------------------------------- pulse */

function startPulse() {
  stopPulse();
  S.pulseTimer = setInterval(async () => {
    if (S.view !== 'plan' || !S.planId) return;
    try {
      const r = await api('/api/plans/' + S.planId + '/pulse?since=' + S.pulseSince);
      S.online = r.online || [];
      if (r.activity && r.activity.length) {
        S.pulseSince = r.last_id;
        S.activity = (r.activity || []).concat(S.activity || []).slice(0, 40);
        if (S.tab === 'produce') { await loadSections(); }
        renderSideRight();
        renderTopOnly();
      }
    } catch (e) { /* offline is fine */ }
  }, 6000);
}
function stopPulse() { if (S.pulseTimer) clearInterval(S.pulseTimer); S.pulseTimer = null; }
function renderTopOnly() {
  const old = $('.top');
  if (old) old.replaceWith(topBar());
}

/* ----------------------------------------------------------- plan view */

function viewPlan() {
  const tabs = el('div', { class: 'tabs' },
    tabBtn('plan', 'Plan  ·  7 steps'),
    tabBtn('produce', 'Staff production'),
    tabBtn('opord', 'OPORD'),
    tabBtn('brief', 'Briefing products'));
  let main;
  if (S.tab === 'plan') main = paneSteps();
  else if (S.tab === 'produce') main = paneProduce();
  else if (S.tab === 'opord') main = paneOpord();
  else main = paneBrief();

  return el('div', {},
    tabs,
    el('div', { class: 'layout' },
      el('div', { class: 'side-left' }, railCard()),
      el('div', { id: 'main' }, main),
      el('div', { class: 'side-right', id: 'sideright' }, sideRight())));
}

function tabBtn(key, label) {
  return el('button', { class: 'tab' + (S.tab === key ? ' on' : ''), text: label,
    onclick: async () => {
      S.tab = key;
      if (key === 'produce' || key === 'opord') await loadSections();
      render();
    } });
}

function railCard() {
  const steps = S.state.steps.map((st) => {
    const def = S.flow.steps.find((x) => x.key === st.key);
    const mark = st.status === 'complete' ? '✓' : (st.status === 'stale' ? '!' : st.num);
    const done = Object.values(st.fields).filter((v) => v === 'answered').length;
    return el('button', {
      class: 'step' + (S.stepKey === st.key && S.tab === 'plan' ? ' active' : ''),
      onclick: () => { S.stepKey = st.key; S.tab = 'plan'; render(); window.scrollTo(0, 0); } },
      el('span', { class: 'dot ' + st.status, text: String(mark) }),
      el('span', {},
        def.title,
        el('span', { class: 'sub', text: done + '/' + Object.keys(st.fields).length
          + ' fields' + (st.status === 'stale' ? ' · needs review' : '') })));
  });
  const doneSteps = S.state.steps.filter((s) => s.status === 'complete').length;
  return el('div', { class: 'card rail' },
    el('div', { class: 'railhead', text: 'Military decision-making process' }),
    steps,
    el('div', { style: 'padding:.6rem .5rem 0' },
      el('div', { class: 'progress' },
        el('i', { style: 'width:' + Math.round(100 * doneSteps / S.state.steps.length) + '%' })),
      el('div', { class: 'tiny muted', style: 'margin-top:.35rem',
        text: doneSteps + ' of ' + S.state.steps.length + ' steps complete' })),
    S.canPlan && S.plan.phase === 'planning' ? el('div', { style: 'padding:.7rem .5rem 0' },
      el('button', { class: 'primary wide', text: 'Move to staff production',
        onclick: toProduction })) : null);
}

async function toProduction() {
  const incomplete = S.state.steps.filter((s) => s.status !== 'complete');
  if (incomplete.length && !confirm(
    incomplete.length + ' step(s) are not complete. The OPORD will have gaps '
    + 'for the staff to fill. Continue?')) return;
  await post('/api/plans/' + S.planId + '/phase', { phase: 'production' });
  await refreshPlan();
  S.tab = 'produce';
  await loadSections();
  render();
  toast('OPORD drafted from your decisions — assign the paragraphs');
}

/* ------------------------------------------------------------ step pane */

function paneSteps() {
  const def = S.flow.steps.find((s) => s.key === S.stepKey);
  const st = S.state.steps.find((s) => s.key === S.stepKey);
  const idx = S.flow.steps.findIndex((s) => s.key === S.stepKey);

  const head = el('div', { class: 'stephead' },
    el('h1', { text: 'Step ' + def.num + ' — ' + def.title }),
    el('div', { class: 'plain', text: def.plain }),
    el('div', { class: 'small muted', style: 'margin-top:.4rem',
      text: 'Purpose: ' + def.purpose }),
    el('div', { class: 'outputs pill-row' },
      def.outputs.map((o) => el('span', { class: 'pill', text: o }))));

  const fields = def.fields.map((f) => fieldCard(f, st.fields[f.key]));

  const nav = el('div', { class: 'row', style: 'margin-top:1rem;justify-content:space-between' },
    idx > 0 ? el('button', { text: '← Step ' + S.flow.steps[idx - 1].num + ': '
      + S.flow.steps[idx - 1].title,
      onclick: () => { S.stepKey = S.flow.steps[idx - 1].key; render(); window.scrollTo(0, 0); } })
      : el('span'),
    idx < S.flow.steps.length - 1 ? el('button', { class: 'primary',
      text: 'Step ' + S.flow.steps[idx + 1].num + ': ' + S.flow.steps[idx + 1].title + ' →',
      onclick: () => { S.stepKey = S.flow.steps[idx + 1].key; render(); window.scrollTo(0, 0); } })
      : el('button', { class: 'primary', text: 'Move to staff production →',
        onclick: toProduction }));

  const warnord = def.warnord ? el('div', { class: 'card' },
    el('h3', { text: 'Warning order #' + def.warnord }),
    el('p', { class: 'small muted', text:
      'Issued at the end of this step so subordinates can start their own '
      + 'planning and movement while you finish yours.' }),
    el('button', { text: 'Generate WARNORD #' + def.warnord,
      onclick: () => window.open('/api/plans/' + S.planId + '/warnord/' + def.warnord, '_blank') }))
    : null;

  return el('div', {}, el('div', { class: 'card' }, head, fields), warnord, nav);
}

/* ------------------------------------------------------------ one field */

function fieldCard(f, status) {
  const value = S.answers[f.key];
  const has = !isEmpty(value);
  const box = el('div', { class: 'field', id: 'f-' + f.key });

  const head = el('div', { class: 'flabel' },
    el('h3', { text: f.label }),
    el('span', { class: 'badge ' + status, text: status === 'answered' ? 'answered'
      : (status === 'stale' ? 'needs review' : 'not answered') }),
    f.required ? el('span', { class: 'badge req', text: 'required' })
      : el('span', { class: 'badge opt', text: 'optional' }),
    f.opord && f.opord.length ? el('span', { class: 'tiny muted',
      text: '→ feeds ' + f.opord.length + ' OPORD paragraph'
        + (f.opord.length > 1 ? 's' : '') }) : null);
  box.appendChild(head);
  if (f.plain) box.appendChild(el('div', { class: 'plain', text: f.plain }));
  if (f.doctrine) box.appendChild(el('div', { class: 'doct', text: f.doctrine }));

  if (status === 'stale') {
    box.appendChild(el('div', { class: 'warn', style: 'margin-bottom:.6rem', text:
      'Something this answer was based on changed. Review it — or regenerate '
      + 'options to see what the change implies.' }));
  }

  if (has) box.appendChild(answerView(f, status));

  const acts = el('div', { class: 'row', style: 'margin-top:.6rem' });
  if (S.canPlan) {
    acts.appendChild(el('button', { class: has ? '' : 'primary',
      text: has ? 'Show options again' : 'Generate options',
      id: 'gen-' + f.key,
      onclick: () => loadOptions(f, false) }));
    acts.appendChild(el('button', { class: 'ghost', text: 'More options',
      onclick: () => loadOptions(f, true) }));
    acts.appendChild(el('button', { class: 'ghost', text: 'Write my own',
      onclick: () => openWriter(f) }));
    if (has) {
      acts.appendChild(el('button', { class: 'ghost', text: 'Clear',
        onclick: () => saveAnswer(f, f.kind === 'text' || f.kind === 'choice' ? '' : [], 'written') }));
    }
  }
  box.appendChild(acts);
  box.appendChild(el('div', { class: 'opts', id: 'opts-' + f.key }));
  if (S.options[f.key]) renderOptions(f, box);
  return box;
}

function answerView(f, status) {
  const v = S.answers[f.key];
  const meta = S.meta[f.key] || {};
  const wrap = el('div', { class: 'answer' + (status === 'stale' ? ' stale' : '') });
  if (f.kind === 'table') {
    wrap.appendChild(tableEditor(f, v));
  } else if (Array.isArray(v)) {
    wrap.appendChild(el('div', { class: 'items' }, v.map((item, i) =>
      el('div', { class: 'item' },
        el('span', { class: 'num', text: (i + 1) + '.' }),
        el('span', { class: 'txt', text: String(item) }),
        S.canPlan ? el('button', { class: 'ghost x', text: '×', title: 'remove',
          onclick: () => {
            const next = v.slice(); next.splice(i, 1);
            saveAnswer(f, next, 'edited');
          } }) : null))));
    if (S.canPlan) wrap.appendChild(addOwnRow(f, v));
  } else {
    wrap.appendChild(el('div', { text: String(v) }));
  }
  wrap.appendChild(el('div', { class: 'ameta', text:
    (meta.source === 'written' ? 'written by hand' :
      meta.source === 'edited' ? 'edited' : 'chosen from options')
    + (meta.at ? ' · ' + when(meta.at) : '') }));
  return wrap;
}

function addOwnRow(f, current) {
  const inp = el('input', { type: 'text', placeholder: 'add your own…' });
  const add = () => {
    const t = inp.value.trim();
    if (!t) return;
    saveAnswer(f, (current || []).concat([t]), 'edited');
  };
  inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') add(); });
  return el('div', { class: 'row', style: 'margin-top:.5rem' },
    el('div', { style: 'flex:1;min-width:200px' }, inp),
    el('button', { text: 'Add', onclick: add }));
}

function tableEditor(f, rows) {
  rows = (rows || []).map((r) => Array.isArray(r) ? r.slice() : [String(r)]);
  const table = el('table', { class: 'grid' });
  table.appendChild(el('tr', {}, f.columns.map((c) => el('th', { text: c }))));
  rows.forEach((row, ri) => {
    const cells = f.columns.map((_c, ci) => el('td', {
      contenteditable: S.canPlan ? 'true' : null,
      text: row[ci] === undefined ? '' : String(row[ci]),
      oninput: (e) => { rows[ri][ci] = e.target.textContent; },
      onblur: () => saveAnswer(f, rows, 'edited', true),
    }));
    if (S.canPlan) {
      cells.push(el('td', { style: 'width:1%' },
        el('button', { class: 'ghost', text: '×', title: 'delete row',
          onclick: () => { const n = rows.slice(); n.splice(ri, 1); saveAnswer(f, n, 'edited'); } })));
    }
    table.appendChild(el('tr', {}, cells));
  });
  const wrap = el('div', {}, el('div', { class: 'tablewrap' }, table));
  if (S.canPlan) {
    wrap.appendChild(el('button', { class: 'ghost', text: '+ blank row',
      onclick: () => saveAnswer(f, rows.concat([f.columns.map(() => '')]), 'edited') }));
  }
  return wrap;
}

/* --------------------------------------------------------------- options */

async function loadOptions(f, refresh) {
  const btn = document.getElementById('gen-' + f.key);
  const host = document.getElementById('opts-' + f.key);
  if (!host) return;
  host.textContent = '';
  host.appendChild(el('div', { class: 'small muted' },
    el('span', { class: 'spin' }), ' generating options…'));
  if (btn) btn.disabled = true;
  try {
    const r = await post('/api/plans/' + S.planId + '/options',
      { field: f.key, n: 5, refresh: !!refresh });
    S.options[f.key] = r;
    const box = document.getElementById('f-' + f.key);
    renderOptions(f, box);
  } catch (e) {
    host.textContent = '';
    host.appendChild(el('div', { class: 'err', text: e.message }));
  } finally { if (btn) btn.disabled = false; }
}

function renderOptions(f, box) {
  const host = document.getElementById('opts-' + f.key);
  if (!host) return;
  const data = S.options[f.key];
  host.textContent = '';
  if (!data) return;

  if (data.notes && data.notes.length) {
    host.appendChild(el('div', { class: 'note', text: data.notes.join(' · ') }));
  }
  host.appendChild(el('div', { class: 'tiny muted', text:
    (data.options.length + ' options · ' + (data.provider || 'offline')
      + (data.cached ? ' · cached' : '')) }));

  const multi = (f.kind === 'items' || f.kind === 'multi' || f.kind === 'table');
  const current = S.answers[f.key];

  data.options.forEach((o) => {
    const val = o.value;
    const isBlank = (typeof val === 'string' && !val.trim());
    const picked = multi ? containsValue(current, val) : sameValue(current, val);
    const card = el('div', { class: 'opt' + (picked ? ' picked' : '') });
    card.appendChild(el('div', { class: 'olabel', text: o.label || 'Option' }));
    const shown = Array.isArray(val) ? val.join('  |  ') : String(val);
    // When the label is the whole answer (short choices), don't print it twice.
    if (!isBlank && shown.trim() !== (o.label || '').trim()) {
      card.appendChild(el('div', { class: 'oval', text: shown }));
    }
    if (o.rationale) card.appendChild(el('div', { class: 'orat', text: o.rationale }));
    if (o.flags && o.flags.length) {
      card.appendChild(el('div', { class: 'oflags' },
        o.flags.map((fl) => el('span', { class: 'oflag', text: fl }))));
    }
    if (o.cites && o.cites.length) {
      card.appendChild(el('div', { class: 'ocite', text:
        'doctrine: ' + o.cites.map((c) => c.title).join(', ') }));
    }
    const acts = el('div', { class: 'oacts' });
    if (isBlank) {
      acts.appendChild(el('button', { class: 'primary', text: 'Write my own',
        onclick: () => openWriter(f) }));
    } else if (multi) {
      acts.appendChild(el('button', { class: picked ? '' : 'primary',
        text: picked ? 'Remove' : 'Add to list',
        onclick: () => {
          const cur = Array.isArray(current) ? current.slice() : [];
          const at = cur.findIndex((x) => sameValue(x, val));
          if (at >= 0) cur.splice(at, 1); else cur.push(val);
          saveAnswer(f, cur, 'selected', false, o.id);
        } }));
      acts.appendChild(el('button', { class: 'ghost', text: 'Add & edit',
        onclick: () => openWriter(f, val, true) }));
    } else {
      acts.appendChild(el('button', { class: 'primary', text: 'Use this',
        onclick: () => saveAnswer(f, val, 'selected', false, o.id) }));
      acts.appendChild(el('button', { class: 'ghost', text: 'Use & edit',
        onclick: () => openWriter(f, val) }));
    }
    card.appendChild(acts);
    host.appendChild(card);
  });

  host.appendChild(el('div', { class: 'row', style: 'margin-top:.3rem' },
    el('button', { class: 'ghost', text: 'None of these — write my own',
      onclick: () => openWriter(f) }),
    el('button', { class: 'ghost', text: 'Different options',
      onclick: () => loadOptions(f, true) }),
    el('button', { class: 'ghost', text: 'Hide options',
      onclick: () => { delete S.options[f.key]; render(); } })));
}

function openWriter(f, seed, appendToList) {
  const host = document.getElementById('opts-' + f.key);
  if (!host) return;
  host.textContent = '';
  const ta = el('textarea', { placeholder: f.placeholder || 'Type your own…' });
  ta.value = seed === undefined ? currentAsText(f) : (Array.isArray(seed) ? seed.join(' | ') : String(seed));
  const hint = f.kind === 'items'
    ? 'One entry per line.'
    : (f.kind === 'table' ? ('One row per line, cells separated by |  —  columns: '
      + f.columns.join(' | ')) : '');
  host.appendChild(el('div', { class: 'card', style: 'margin:0' },
    el('h3', { text: 'Write your own' }),
    hint ? el('div', { class: 'tiny muted', style: 'margin-bottom:.35rem', text: hint }) : null,
    ta,
    el('div', { class: 'row', style: 'margin-top:.5rem' },
      el('button', { class: 'primary', text: 'Save', onclick: () => {
        const v = parseWritten(f, ta.value, appendToList);
        saveAnswer(f, v, 'written');
      } }),
      el('button', { class: 'ghost', text: 'Cancel',
        onclick: () => { delete S.options[f.key]; render(); } }))));
  ta.focus();
}

function currentAsText(f) {
  const v = S.answers[f.key];
  if (isEmpty(v)) return '';
  if (f.kind === 'table') return (v || []).map((r) => r.join(' | ')).join('\n');
  if (Array.isArray(v)) return v.join('\n');
  return String(v);
}

function parseWritten(f, text, appendToList) {
  if (f.kind === 'table') {
    const rows = text.split('\n').map((l) => l.trim()).filter(Boolean)
      .map((l) => {
        const cells = l.split('|').map((c) => c.trim());
        while (cells.length < f.columns.length) cells.push('');
        return cells.slice(0, f.columns.length);
      });
    return appendToList ? (S.answers[f.key] || []).concat(rows) : rows;
  }
  if (f.kind === 'items' || f.kind === 'multi') {
    const items = text.split('\n').map((l) => l.trim()).filter(Boolean);
    return appendToList ? (S.answers[f.key] || []).concat(items) : items;
  }
  return text.trim();
}

async function saveAnswer(f, value, source, quiet, optionId) {
  try {
    const r = await post('/api/plans/' + S.planId + '/answer',
      { field: f.key, value: value, source: source, option_id: optionId });
    S.answers[f.key] = value;
    S.state = r.state;
    S.meta[f.key] = { source: source, at: Math.floor(Date.now() / 1000) };
    if (r.stale && r.stale.length) {
      toast(r.stale.length + ' later answer(s) now need review: '
        + r.stale.slice(0, 2).map((s) => s.label).join(', ')
        + (r.stale.length > 2 ? '…' : ''));
    } else if (!quiet) { toast('Saved'); }
    if (!quiet) { delete S.options[f.key]; render(); }
  } catch (e) { toast(e.message); }
}

/* ------------------------------------------------------- staff production */

async function loadSections() {
  const r = await api('/api/plans/' + S.planId + '/sections');
  S.sections = r.sections; S.completeness = r.completeness;
}

function paneProduce() {
  if (S.plan.phase === 'planning') {
    return el('div', { class: 'card' },
      el('h2', { text: 'Staff production' }),
      el('p', { class: 'muted', text:
        'This phase opens once the planning steps are done. Every paragraph of '
        + 'the order will already be drafted from the decisions you made — the '
        + 'staff refines and owns them rather than typing them from scratch.' }),
      S.canPlan ? el('button', { class: 'primary', text:
        'Draft the OPORD and open production now', onclick: toProduction }) : null);
  }
  const c = S.completeness || {};
  const paras = S.sections.filter((s) => s.kind === 'paragraph');
  const annexes = S.sections.filter((s) => s.kind === 'annex');
  const mine = S.sections.filter((s) => s.owner_id === S.user.id);

  const rowFor = (s) => el('div', { class: 'brow' },
    el('div', { style: 'cursor:pointer', onclick: () => openSection(s) },
      el('div', { class: 'btitle', text: s.title }),
      el('div', { class: 'tiny muted', text: (s.body || '').trim()
        ? (s.body.replace(/\s+/g, ' ').slice(0, 110) + '…') : 'empty' })),
    el('div', { class: 'tiny muted', text: s.owner_name
      ? ('owner: ' + s.owner_name) : ('suggest: ' + s.owner_hint_name) }),
    el('div', { class: 'st ' + s.status, text: s.status.replace(/_/g, ' ') }),
    el('div', { class: 'row tight' },
      !s.owner_id ? el('button', { class: 'ghost', text: 'Claim',
        onclick: async () => { await post('/api/plans/' + S.planId + '/sections/'
          + s.key + '/claim'); await loadSections(); render(); toast('Yours'); } })
        : el('button', { class: 'ghost', text: 'Open', onclick: () => openSection(s) })));

  return el('div', {},
    el('div', { class: 'card' },
      el('h2', { text: 'Staff production' }),
      el('p', { class: 'small muted', text:
        'Every paragraph below was drafted from the plan. Claim the ones you own, '
        + 'refine them, and mark them ready. Other people on the network see your '
        + 'changes within a few seconds.' }),
      el('div', { class: 'row', style: 'margin-top:.5rem' },
        el('span', { class: 'pill', text: (c.filled || 0) + ' of ' + (c.paragraphs || 0) + ' paragraphs drafted' }),
        el('span', { class: 'pill', text: (c.approved || 0) + ' approved' }),
        el('span', { class: 'pill', text: (c.annexes_started || 0) + ' of ' + (c.annexes || 0) + ' annexes started' }))),
    mine.length ? el('div', { class: 'card' },
      el('h3', { text: 'Assigned to you' }),
      el('div', { class: 'board' }, mine.map(rowFor))) : null,
    el('div', { class: 'card' },
      el('h3', { text: 'Order paragraphs' }),
      el('div', { class: 'board' }, paras.map(rowFor))),
    el('div', { class: 'card' },
      el('h3', { text: 'Annexes' }),
      el('p', { class: 'small muted', text:
        'Annexes are optional. Start only the ones this operation needs.' }),
      el('div', { class: 'board' }, annexes.map(rowFor))));
}

function openSection(s) {
  const ta = el('textarea', { style: 'min-height:18rem' });
  ta.value = s.body || '';
  const statusSel = el('select', {},
    ['not_started', 'drafted', 'in_progress', 'ready_for_review', 'approved']
      .map((v) => el('option', { value: v, selected: v === s.status ? 'selected' : null,
        text: v.replace(/_/g, ' ') })));
  const save = async () => {
    const body = { body: ta.value, status: statusSel.value };
    try {
      await post('/api/plans/' + S.planId + '/sections/' + s.key, body);
      await loadSections(); render(); toast('Saved');
    } catch (e) { toast(e.message); }
  };
  const main = document.getElementById('main');
  main.textContent = '';
  main.appendChild(el('div', { class: 'card' },
    el('div', { class: 'row', style: 'justify-content:space-between' },
      el('h2', { text: s.title }),
      el('button', { class: 'ghost', text: '← back to production',
        onclick: () => render() })),
    s.guidance ? el('div', { class: 'doct', text: s.guidance }) : null,
    el('div', { class: 'tiny muted', text: s.owner_name
      ? ('Owner: ' + s.owner_name) : ('Suggested owner: ' + s.owner_hint_name) }),
    el('label', { class: 'lab', text: 'Paragraph text' }), ta,
    el('div', { class: 'row', style: 'margin-top:.6rem' },
      el('span', { class: 'small muted', text: 'Status' }), statusSel,
      el('button', { class: 'primary', text: 'Save', onclick: save }),
      !s.owner_id ? el('button', { text: 'Claim this paragraph', onclick: async () => {
        await post('/api/plans/' + S.planId + '/sections/' + s.key + '/claim');
        await loadSections(); render();
      } }) : null),
    !S.canApprove ? el('div', { class: 'tiny muted', style: 'margin-top:.5rem',
      text: 'Only the commander or an admin can set a paragraph to approved.' }) : null));
  window.scrollTo(0, 0);
}

/* --------------------------------------------------------------- OPORD */

function paneOpord() {
  const doc = el('div', { class: 'doc' });
  api('/api/plans/' + S.planId + '/opord').then((r) => {
    doc.textContent = '';
    r.document.forEach((n) => {
      const tag = n.level === 0 ? 'h2' : 'h3';
      doc.appendChild(el(tag, { text: (n.num ? n.num + ' ' : '') + n.title }));
      doc.appendChild(el('div', { class: 'p' + (n.body.trim() ? '' : ' todo'),
        text: n.body.trim() || '(to be completed)' }));
    });
    doc.appendChild(el('h2', { text: 'Annexes' }));
    r.annexes.forEach((a) => {
      doc.appendChild(el('div', { class: 'p' + (a.body.trim() ? '' : ' todo'),
        text: 'Annex ' + a.letter + ' — ' + a.title + ' (' + a.owner + ')'
          + (a.body.trim() ? '' : ' — not started') }));
    });
  });
  const ex = (fmt, label) => el('button', { text: label,
    onclick: () => window.open('/api/plans/' + S.planId + '/export?format=' + fmt, '_blank') });
  return el('div', {},
    el('div', { class: 'card' },
      el('div', { class: 'row', style: 'justify-content:space-between' },
        el('h2', { text: 'Operation order' }),
        el('div', { class: 'row tight' },
          ex('html', 'Print / HTML'), ex('docx', 'Word'), ex('md', 'Markdown'),
          ex('txt', 'Plain text'), ex('json', 'Plan data')))),
    doc);
}

function paneBrief() {
  const w = (n) => el('button', { text: 'WARNORD #' + n,
    onclick: () => window.open('/api/plans/' + S.planId + '/warnord/' + n, '_blank') });
  return el('div', { class: 'card' },
    el('h2', { text: 'Briefing products' }),
    el('p', { class: 'small muted', text:
      'Warning orders are built from whatever the plan knows so far — issue '
      + 'them early and update as you go, rather than waiting for certainty.' }),
    el('div', { class: 'row', style: 'margin-top:.6rem' }, w(1), w(2), w(3)),
    el('h3', { style: 'margin-top:1.3rem', text: 'What goes in each' }),
    Object.entries(S.doctrine.warnord).map(([num, items]) =>
      el('div', { style: 'margin-bottom:.7rem' },
        el('div', { class: 'small', style: 'font-weight:600',
          text: 'WARNORD #' + num }),
        el('div', { class: 'pill-row' },
          items.map((i) => el('span', { class: 'pill', text: i }))))));
}

/* ----------------------------------------------------------- right rail */

function sideRight() {
  const bits = [];
  const key = ['mission_statement', 'intent_purpose', 'intent_end_state',
    'approved_coa'];
  const known = key.filter((k) => !isEmpty(S.answers[k]));
  if (known.length) {
    bits.push(el('div', { class: 'card' },
      el('h3', { text: 'Plan at a glance' }),
      known.map((k) => {
        const f = fieldDef(k);
        return el('div', { style: 'margin-bottom:.6rem' },
          el('div', { class: 'tiny muted', text: f ? f.label : k }),
          el('div', { class: 'small', text: String(S.answers[k]).slice(0, 260) }));
      })));
  }
  const acts = (S.activity || []).slice(0, 12);
  bits.push(el('div', { class: 'card' },
    el('h3', { text: 'Activity' }),
    S.online.length ? el('div', { class: 'pill-row', style: 'margin-bottom:.5rem' },
      S.online.map((o) => el('span', { class: 'pill',
        text: o.display_name + ' · ' + (o.staff_section || '').toUpperCase() }))) : null,
    acts.length ? acts.map((a) => el('div', { class: 'tiny muted',
      style: 'margin-bottom:.3rem',
      text: (a.display_name || 'someone') + ' ' + a.kind.replace(/\./g, ' ')
        + (a.detail ? ' — ' + a.detail : '') + ' · ' + when(a.ts) }))
      : el('div', { class: 'tiny muted', text: 'Nothing yet.' })));
  return bits;
}
function renderSideRight() {
  const host = document.getElementById('sideright');
  if (!host) return;
  host.textContent = '';
  sideRight().forEach((b) => host.appendChild(b));
}

/* ------------------------------------------------------------- settings */

function viewSettings() {
  const box = el('div', {});
  box.appendChild(el('div', { class: 'card' },
    el('h2', { text: 'Settings' }),
    el('p', { class: 'small muted', text:
      'The tool works with no model at all — option generation falls back to '
      + 'doctrinal templates. A local model makes the drafts fit your scenario '
      + 'more closely.' })));

  const provBox = el('div', { class: 'card' }, el('h3', { text: 'Model provider' }),
    el('div', { class: 'small muted' }, 'loading…'));
  box.appendChild(provBox);
  api('/api/providers').then((r) => {
    provBox.textContent = '';
    provBox.appendChild(el('h3', { text: 'Model provider' }));
    provBox.appendChild(el('div', { class: 'small', style: 'margin-bottom:.6rem',
      text: 'Currently: ' + r.describe }));
    const sel = el('select', {}, r.detected.map((d) => el('option', {
      value: d.name, selected: d.name === r.current.provider ? 'selected' : null,
      text: d.describe + (d.available ? '  ✓ reachable' : '  — not detected') })));
    const model = el('input', { type: 'text', value: r.current.model || '',
      placeholder: 'model name (e.g. qwen2.5:7b-instruct, claude-opus-5)' });
    const base = el('input', { type: 'text', value: r.current.base_url || '',
      placeholder: 'base URL (e.g. http://localhost:11434)' });
    const key = el('input', { type: 'password',
      placeholder: r.current.has_key ? '•••••• (set)' : 'API key (Claude only)' });
    const out = el('div', {});
    provBox.appendChild(el('label', { class: 'lab', text: 'Provider' }));
    provBox.appendChild(sel);
    provBox.appendChild(el('label', { class: 'lab', text: 'Model' }));
    provBox.appendChild(model);
    provBox.appendChild(el('label', { class: 'lab', text: 'Base URL' }));
    provBox.appendChild(base);
    provBox.appendChild(el('label', { class: 'lab', text: 'API key' }));
    provBox.appendChild(key);
    provBox.appendChild(el('div', { class: 'row', style: 'margin-top:.7rem' },
      el('button', { class: 'primary', text: 'Save', onclick: async () => {
        const res = await post('/api/providers', { provider: sel.value,
          model: model.value, base_url: base.value, api_key: key.value });
        out.textContent = '';
        out.appendChild(el('div', { class: res.available ? 'ok' : 'err',
          text: res.describe + (res.available ? ' — reachable'
            : ' — NOT reachable; option generation will use doctrinal templates') }));
        S.provider = res.describe;
      } })));
    provBox.appendChild(out);
    r.detected.forEach((d) => {
      if (d.models && d.models.length) {
        provBox.appendChild(el('div', { class: 'tiny muted', style: 'margin-top:.4rem',
          text: 'Ollama models available: ' + d.models.join(', ') }));
      }
    });
  });

  const docBox = el('div', { class: 'card' }, el('h3', { text: 'Doctrine library' }),
    el('div', { class: 'small muted' }, 'loading…'));
  box.appendChild(docBox);
  const loadDoc = () => api('/api/doctrine/stats').then((r) => {
    docBox.textContent = '';
    docBox.appendChild(el('h3', { text: 'Doctrine library' }));
    docBox.appendChild(el('p', { class: 'small muted', text:
      'Drop publications into ' + (r.corpus_dir || 'corpus/') + ' and re-index. '
      + 'PDF, DOCX, PPTX, TXT, and Markdown are read. Retrieved passages are '
      + 'shown next to the options they informed.' }));
    docBox.appendChild(el('div', { class: 'small', text:
      r.documents.length + ' document(s), ' + r.chunks + ' passage(s) indexed' }));
    docBox.appendChild(el('div', { class: 'pill-row' },
      r.documents.map((d) => el('span', { class: 'pill',
        text: d.title + ' (' + d.n_chunks + ')' }))));
    docBox.appendChild(el('div', { class: 'row', style: 'margin-top:.7rem' },
      el('button', { text: 'Index new documents', onclick: async () => {
        toast('Indexing…');
        await post('/api/doctrine/ingest', {}); loadDoc(); toast('Done');
      } }),
      el('button', { class: 'ghost', text: 'Rebuild from scratch', onclick: async () => {
        toast('Rebuilding…');
        await post('/api/doctrine/ingest', { force: true }); loadDoc(); toast('Done');
      } })));
  });
  loadDoc();

  const userBox = el('div', { class: 'card' }, el('h3', { text: 'Accounts' }),
    el('div', { class: 'small muted' }, 'loading…'));
  box.appendChild(userBox);
  const loadUsers = () => api('/api/users').then((r) => {
    userBox.textContent = '';
    userBox.appendChild(el('h3', { text: 'Accounts' }));
    userBox.appendChild(el('p', { class: 'small muted', text:
      'Everyone who needs to work on an order needs an account on this machine. '
      + 'They reach it at the address printed in the server window.' }));
    const table = el('table', { class: 'grid' },
      el('tr', {}, ['Name', 'Username', 'Role', 'Section', ''].map((h) => el('th', { text: h }))));
    r.users.forEach((u) => table.appendChild(el('tr', {},
      el('td', { text: u.display_name }), el('td', { text: u.username }),
      el('td', { text: u.role }), el('td', { text: (u.staff_section || '').toUpperCase() }),
      el('td', {}, u.active ? el('button', { class: 'ghost', text: 'Deactivate',
        onclick: async () => {
          if (!confirm('Deactivate ' + u.display_name + '?')) return;
          await post('/api/users/' + u.id + '/deactivate'); loadUsers();
        } }) : el('span', { class: 'tiny muted', text: 'inactive' })))));
    userBox.appendChild(el('div', { class: 'tablewrap' }, table));

    const nu = { u: el('input', { type: 'text', placeholder: 'username' }),
      d: el('input', { type: 'text', placeholder: 'display name' }),
      p: el('input', { type: 'password', placeholder: 'password' }),
      r: el('select', {}, r.roles.map((x) => el('option', { value: x, text: x }))),
      s: el('select', {}, r.sections.map((x) => el('option', { value: x.key,
        text: x.name }))) };
    const err = el('div', { class: 'err' });
    userBox.appendChild(el('h3', { style: 'margin-top:1rem', text: 'Add an account' }));
    userBox.appendChild(el('div', { class: 'row' },
      el('div', { style: 'flex:1;min-width:140px' }, nu.u),
      el('div', { style: 'flex:1;min-width:140px' }, nu.d),
      el('div', { style: 'flex:1;min-width:140px' }, nu.p),
      el('div', { style: 'min-width:130px' }, nu.r),
      el('div', { style: 'min-width:170px' }, nu.s),
      el('button', { class: 'primary', text: 'Add', onclick: async () => {
        err.textContent = '';
        try {
          await post('/api/users', { username: nu.u.value, display_name: nu.d.value,
            password: nu.p.value, role: nu.r.value, staff_section: nu.s.value });
          nu.u.value = nu.d.value = nu.p.value = ''; loadUsers();
        } catch (e) { err.textContent = e.message; }
      } })));
    userBox.appendChild(err);
    userBox.appendChild(el('div', { class: 'tiny muted', style: 'margin-top:.5rem',
      text: 'Roles — admin: everything. commander: approves paragraphs and owns '
        + 'the intent. planner: runs the seven steps. staff: writes assigned '
        + 'paragraphs. observer: read only.' }));
  });
  loadUsers();

  box.appendChild(el('button', { text: '← back to plans',
    onclick: () => { S.view = 'plans'; loadPlans(); } }));
  return box;
}

/* ----------------------------------------------------------------- util */

function fieldDef(key) {
  for (const s of S.flow.steps) for (const f of s.fields) if (f.key === key) return f;
  return null;
}
function isEmpty(v) {
  return v === null || v === undefined || (typeof v === 'string' && !v.trim())
    || (Array.isArray(v) && v.length === 0);
}
function sameValue(a, b) {
  if (Array.isArray(a) && Array.isArray(b)) return a.join('') === b.join('');
  return String(a) === String(b);
}
function containsValue(list, v) {
  if (!Array.isArray(list)) return false;
  return list.some((x) => sameValue(x, v));
}
function when(ts) {
  if (!ts) return '';
  const d = new Date(ts * 1000);
  const secs = (Date.now() / 1000) - ts;
  if (secs < 60) return 'just now';
  if (secs < 3600) return Math.floor(secs / 60) + 'm ago';
  if (secs < 86400) return Math.floor(secs / 3600) + 'h ago';
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/* ----------------------------------------------------------------- boot */

async function boot() {
  const b = await api('/api/bootstrap');
  S.needsSetup = b.needs_setup;
  S.user = b.user;
  if (!S.user) return render();
  const f = await api('/api/flow');
  S.flow = f.flow; S.doctrine = f.doctrine;
  await loadPlans();
}

boot().catch((e) => {
  document.getElementById('app').textContent = 'Could not reach the server: ' + e.message;
});
