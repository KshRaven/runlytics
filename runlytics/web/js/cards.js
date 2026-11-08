'use strict';
/* Cards and content area. */

const io = new IntersectionObserver(es => {
  for (const e of es) {
    const ct = S.ctrls.get(e.target); if (!ct) continue;
    ct.visible = e.isIntersecting;
    if (ct.visible) ct.activate();
  }
}, { root: $('#main'), rootMargin: '300px' });

// Card kinds: how each tab maps to a card type, which cards are single-run, and how a view is constructed.
const CANVAS = new Set(['line', 'hist', 'pr', 'projector', 'mesh', 'custom']);
const SINGLE = new Set(['hist', 'image', 'audio', 'text', 'graph', 'pr', 'projector', 'mesh']);
let CUSTOM = {};   // custom-scalar chart key -> resolved scalar tags
// Custom-scalar layout -> {"category/chart": runs}; Multiline entries are anchored regexes, Margin entries literal tags.
function customSrc() {
  const out = {}, sc = S.tags.scalars || {}; CUSTOM = {};
  for (const [cat, charts] of Object.entries(S.tags.layout || {})) for (const [title, spec] of Object.entries(charts)) {
    const [kind, items] = spec; let tags = [];
    if (kind === 'Margin') tags = (items[0] || []).filter(t => sc[t]);
    else for (const pat of items) { let re; try { re = new RegExp('^(?:' + pat + ')$'); } catch (e) { continue; } tags.push(...Object.keys(sc).filter(t => re.test(t) && !tags.includes(t))); }
    if (!tags.length) continue;
    const key = cat + '/' + title; CUSTOM[key] = tags; out[key] = [...new Set(tags.flatMap(t => sc[t]))];
  }
  return out;
}
const TAB_SPEC = {
  scalars: { kind: 'line', multi: true, src: () => S.tags.scalars },
  histograms: { kind: 'hist', src: () => S.tags.histograms },
  images: { kind: 'image', src: () => S.tags.other.images || {} },
  audio: { kind: 'audio', src: () => S.tags.other.audio || {} },
  text: { kind: 'text', src: () => S.tags.other.text || {} },
  graphs: { kind: 'graph', src: () => S.tags.other.graphs || {} },
  projector: { kind: 'projector', src: () => S.tags.other.projector || {} },
  pr_curves: { kind: 'pr', src: () => S.tags.other.pr_curves || {} },
  hparams: { kind: 'hparams', multi: true, src: () => S.tags.other.hparams || {} },
  custom_scalars: { kind: 'custom', multi: true, src: customSrc },
  mesh: { kind: 'mesh', src: () => S.tags.other.mesh || {} },
  timeseries: { mixed: ['scalars', 'histograms', 'images'], src: () => Object.assign({}, S.tags.scalars, S.tags.histograms, (S.tags.other || {}).images) }
};
const VIEWS = {
  line: (c, t, rs) => new LineChart(c, t, rs),
  hist: (c, t, rs) => new HistChart(c, t, rs[0]),
  image: (c, t, rs) => new ImageView(c, t, rs[0]),
  audio: (c, t, rs) => new AudioView(c, t, rs[0]),
  text: (c, t, rs) => new TextView(c, t, rs[0]),
  graph: (c, t, rs) => new GraphView(c, t, rs[0]),
  projector: (c, t, rs) => new ProjectorChart(c, t, rs[0]),
  pr: (c, t, rs) => new PRChart(c, t, rs[0]),
  mesh: (c, t, rs) => new MeshChart(c, t, rs[0]),
  hparams: (c, t, rs) => new HParamsView(c, t, rs),
  custom: (c, t, rs) => new LineChart(c, t, rs, CUSTOM[t])
};

const gridCols = () => `repeat(auto-fill,minmax(min(100%,${SET.cardW}px),1fr))`;
const pkey = (kind, tag) => kind + '|' + tag;
function makeCard(kind, tag, runs) {
  const card = el('div', 'card' + (CANVAS.has(kind) ? '' : ' mc'));
  const run = SINGLE.has(kind) ? runs[0] : null, hk = HINT_KIND[kind], custom = hintFor(hk, tag).custom, pk = pkey(kind, tag);
  card.innerHTML = `<div class="chead"><span class="ct" title="${esc(tag)}">${run ? `<i style="background:${colorOf(run)}"></i>` : ''}${esc(tag)}${run ? ` <span style="color:var(--dim);font-weight:400">· ${esc(run)}</span>` : ''}</span><span class="cn"></span>${custom ? '<button class="ci has" title="About this chart">i</button>' : ''}<div class="cb"></div></div><div class="cbody"><div class="cmsg">Loading…</div></div>`;
  const ct = { card, kind, tag, runs, chart: null, visible: false, dirty: true };
  const cb = $('.cb', card), ci = $('.ci', card);
  if (ci) ci.onclick = e => { e.stopPropagation(); toggleHint(card, hk, tag); };
  const mk = (h, title, fn, cls) => { const b = el('button', cls || 'ib', h); b.title = title; b.onclick = fn; return b; };
  // expand: grows to the full row (like a normal dashboard); long-press opens a pop-up instead
  const ex = mk(icon('max'), 'Expand to full row (hold for pop-up)', null);
  let hold = 0, long = false;
  ex.onpointerdown = () => { long = false; hold = setTimeout(() => { long = true; toggleXL(card); }, 550); };
  ex.onpointerup = ex.onpointerleave = () => clearTimeout(hold);
  ex.onclick = e => { e.stopPropagation(); if (long) { long = false; return; } if (card.classList.contains('xl')) return toggleXL(card); const on = card.classList.toggle('wide'); ex.classList.toggle('on', on); };
  // 3-dot menu
  const more = mk(icon('more'), 'More', null);
  const menu = el('div', 'menu'); card.append(menu);
  const item = (label, fn, cls) => { const b = el('button', cls || '', label); b.onclick = e => { e.stopPropagation(); closeMenus(); fn(); }; menu.append(b); return b; };
  if (kind === 'line' || kind === 'custom') {
    item('Log Y axis', () => { const ch = ct.chart; if (!ch) return; ch.log = !ch.isLog(); ch.schedule(); });
    item('Download CSV', () => ct.chart && ct.chart.csv());
  }
  if (CANVAS.has(kind)) item('Download PNG', () => ct.chart && ct.chart.png(tag.replace(/[^\w.-]+/g, '_')));
  const pinned = SET.pinned.includes(pk);
  const pin = mk(icon('pin'), pinned ? 'Unpin' : 'Pin (a copy is kept in Pinned)', () => { const i = SET.pinned.indexOf(pk); i < 0 ? SET.pinned.push(pk) : SET.pinned.splice(i, 1); renderContent(); });
  if (pinned) pin.classList.add('on');
  const rs = (kind === 'line' || kind === 'custom') ? mk(icon('reset'), 'Reset zoom (double-click chart)', () => ct.chart && ct.chart.reset()) : null;
  more.onclick = e => { e.stopPropagation(); const o = menu.classList.contains('on'); closeMenus(); if (!o) menu.classList.add('on'); };
  if (rs) cb.append(rs); cb.append(pin, ex, more);
  if (CANVAS.has(kind)) {   // drag the bottom edge to make the chart taller
    const rz = el('div', 'crz'), body = $('.cbody', card); card.append(rz);
    rz.onpointerdown = e => { e.preventDefault(); rz.setPointerCapture(e.pointerId); const y0 = e.clientY, h0 = body.getBoundingClientRect().height;
      rz.onpointermove = ev => { body.style.height = Math.max(190, Math.min(2000, h0 + ev.clientY - y0)) + 'px'; };
      rz.onpointerup = () => { rz.onpointermove = rz.onpointerup = null; }; };
    rz.ondblclick = () => { body.style.height = ''; };
  }
  ct.activate = () => {
    if (!ct.chart) ct.chart = VIEWS[kind](card, tag, runs);
    if (ct.dirty) { ct.dirty = false; ct.chart.load(); }
  };
  S.ctrls.set(card, ct); io.observe(card);
  return card;
}
function closeMenus() { document.querySelectorAll('.menu.on').forEach(m => m.classList.remove('on')); }
document.addEventListener('click', closeMenus);
function toggleXL(card) { const on = card.classList.toggle('xl'); $('#veil').classList.toggle('on', on); }
$('#veil').onclick = () => { document.querySelectorAll('.card.xl').forEach(c => toggleXL(c)); };
addEventListener('keydown', e => {
  if (e.key === 'Escape') { $('#veil').click(); closeMenus(); }
  else if (e.key === '/' && !/INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)) { e.preventDefault(); $('#tagFilter').focus(); }
});

function clearContent() { io.disconnect(); S.ctrls.forEach(c => c.chart && c.chart.destroy()); S.ctrls.clear(); $('#veil').classList.remove('on'); }
function renderContent() {
  clearContent(); S.pinsChanged && S.pinsChanged();
  const root = $('#content'); root.replaceChildren();
  if (!S.runs.length) { root.innerHTML = '<div class="empty"><div><b>No event files found</b></div></div>'; return; }
  if (!S.sel.size) { root.innerHTML = '<div class="empty"><div><b>No runs selected</b></div></div>'; return; }
  const spec = TAB_SPEC[S.tab], f = mkFilter($('#tagFilter').value, FO.tag), items = [];
  for (const sp of (spec ? (spec.mixed ? spec.mixed.map(k => TAB_SPEC[k]) : [spec]) : []))
    for (const [t, rs] of Object.entries(sp.src())) { if (sp.multi) items.push([t, rs, sp.kind]); else rs.forEach(run => items.push([t, [run], sp.kind])); }
  const sel = items.filter(([t]) => f(t));
  if (!sel.length) { root.innerHTML = `<div class="empty"><div><b>Nothing to show</b></div></div>`; return; }
  S.pinsChanged && S.pinsChanged();
  const pins = new Set(SET.pinned), groups = new Map(), pinned = [];
  for (const it of sel) {
    if (pins.has(pkey(it[2], it[0]))) pinned.push(it);   // pinning copies: the chart also stays in its own group
    const g = it[0].split('/')[0]; if (!groups.has(g)) groups.set(g, []); groups.get(g).push(it);
  }
  const cols = gridCols(), byName = (a, b) => a[0].localeCompare(b[0], undefined, { numeric: true });
  const section = (g, arr, cls) => {
    arr.sort(byName);
    const key = (cls ? '\u0000' : '') + g, open = key in S.gstate ? S.gstate[key] : !!cls;   // groups start collapsed; only the Pinned section starts open
    const sec = el('section', 'group' + (open ? '' : ' col'));
    const head = el('div', 'ghead' + (cls ? ' ' + cls : ''), `${icon('chev')}<span>${esc(g)}</span><span class="gc">${arr.length}</span>`);
    const grid = el('div', 'grid'); grid.style.gridTemplateColumns = cols;
    const fill = () => { if (grid.dataset.f) return; grid.dataset.f = 1; for (const [tag, runs, kind] of arr) grid.append(makeCard(kind, tag, runs)); };   // cards are only built once a group is open
    head.onclick = () => { sec.classList.toggle('col'); const c = sec.classList.contains('col'); S.gstate[key] = !c; if (!c) fill(); };
    if (!sec.classList.contains('col')) fill();
    sec.append(head, grid); root.append(sec);
  };
  if (pinned.length) section('Pinned', pinned, 'pin');
  for (const g of [...groups.keys()].sort()) section(g, groups.get(g));
}
function redrawAll(prep) { S.ctrls.forEach(c => { if (c.chart) { prep && c.chart.prep && c.chart.prep(); c.chart.schedule(); } }); }
function reloadAll() { S.ctrls.forEach(c => { c.dirty = true; if (c.visible) c.activate(); }); }

