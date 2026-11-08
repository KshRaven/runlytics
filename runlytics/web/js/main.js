'use strict';
/* Tabs, runs, settings, live updates, boot. */

const TABS = [['scalars', 'Scalars'], ['timeseries', 'Time Series'], ['histograms', 'Histograms'], ['images', 'Images'], ['graphs', 'Graphs'], ['text', 'Text'], ['audio', 'Audio'],
  ['projector', 'Embeddings'], ['pr_curves', 'PR Curves'], ['hparams', 'HParams'], ['custom_scalars', 'Custom Scalars'], ['mesh', 'Mesh']];
function renderTabs() {
  const box = $('#tabs'); box.replaceChildren();
  for (const [k, label] of TABS) {
    const spec = TAB_SPEC[k], live = !!spec, cnt = spec ? Object.keys(spec.src()).length : 0;
    const b = el('button', S.tab === k ? 'on' : '', esc(label) + (cnt ? `<span class="n">${cnt}</span>` : ''));
    if (!live) { b.disabled = true; b.title = 'Coming soon'; }
    b.onclick = () => { if (S.tab === k) return; S.tab = k; history.pushState(null, '', k); renderTabs(); renderContent(); };
    box.append(b);
  }
}
async function loadTags() {
  const runs = [...S.sel];
  S.tags = runs.length ? await api('api/tags', { run: runs }) : { scalars: {}, histograms: {}, other: {}, layout: {} };
  S.sig = JSON.stringify([S.tags.scalars, S.tags.histograms, S.tags.other, S.tags.layout]); renderTabs();
}
const ROW = 28;
S.want = new Set(store.get('want', [])); S.sort = Object.assign({ by: 'name', dir: 1 }, store.get('sort', {}));
// restore search boxes and their options (options are only persisted together with a non-empty query)
(function () {
  const ui = store.get('ui', {});
  for (const k of ['run', 'tag']) {
    const inp = $(k === 'run' ? '#runFilter' : '#tagFilter'), o = ui[k] || {};
    inp.value = o.q || ''; if (o.q) Object.assign(FO[k], { case: !!o.case, word: !!o.word, regex: !!o.regex });
    document.querySelectorAll(`.fopts[data-for="${k}"] button`).forEach(b => b.classList.toggle('on', !!FO[k][b.dataset.o]));
  }
  $('#runSort').value = S.sort.by;
})();
const sig = set => [...set].sort().join('\n');
function applyFilter() {
  const f = mkFilter($('#runFilter').value, FO.run), { by, dir } = S.sort;
  const cmp = by === 'name' ? (a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }) : (a, b) => (a[by] - b[by]) || a.name.localeCompare(b.name);
  S.shown = S.runs.filter(r => f(r.name)).sort((a, b) => dir * cmp(a, b));
  const vis = new Set(S.shown.map(r => r.name)), prev = sig(S.sel);
  S.sel = new Set([...S.want].filter(n => vis.has(n)));   // runs hidden by the filter are unloaded until they match again
  return sig(S.sel) !== prev;
}
function renderRuns() {
  const changed = applyFilter();
  $('#runCount').textContent = `${S.sel.size} / ${S.runs.length}`;
  $('#runInner').style.height = S.shown.length * ROW + 'px'; paintRuns();
  return changed;
}
function paintRuns() {
  const box = $('#runList'), inner = $('#runInner'), a = Math.max(0, Math.floor(box.scrollTop / ROW) - 6), b = Math.min(S.shown.length, Math.ceil((box.scrollTop + box.clientHeight) / ROW) + 6), now = Date.now() / 1000, fr = document.createDocumentFragment();
  for (let i = a; i < b; i++) {
    const r = S.shown[i], on = S.sel.has(r.name), l = el('div', 'run' + (on ? ' on' : '') + (now - r.mtime < 60 ? ' live' : ''));
    l.style.top = i * ROW + 'px'; l.title = r.name + ' · ' + r.files + ' file(s)'; l.dataset.run = r.name;
    l.innerHTML = `<span class="cbx${on ? ' c' : ''}"></span><i class="sw" title="Change colour" style="background:${colorOf(r.name)}"></i><span class="nm">${esc(r.name)}</span><span class="sz">${fmtSize(r.size)}</span>`;
    fr.append(l);
  }
  inner.replaceChildren(fr);
}
let selTimer = 0;
function selectionChanged() {
  persistView(); $('#runCount').textContent = `${S.sel.size} / ${S.runs.length}`;
  clearTimeout(selTimer);
  selTimer = setTimeout(async () => { try { await loadTags(); } catch (e) { } renderContent(); api('api/keep', { run: [...S.sel] }).catch(() => { }); }, 300);
}
function persistView() { }
$('#runList').addEventListener('scroll', () => requestAnimationFrame(paintRuns));
function pickColor(name) {
  const i = el('input'); i.type = 'color'; i.value = toHex(colorOf(name)); i.style.cssText = 'position:fixed;left:-99px;opacity:0';
  document.body.append(i); i.oninput = () => { S.colors.set(name, i.value); paintRuns(); redrawAll(true); };
  i.onchange = () => i.remove(); i.click();
}
$('#runInner').addEventListener('click', e => {
  const r = e.target.closest('.run'); if (!r) return; const n = r.dataset.run;
  if (e.target.classList.contains('sw')) return pickColor(n);
  if (S.want.has(n)) { S.want.delete(n); S.sel.delete(n); } else { S.want.add(n); S.sel.add(n); }
  paintRuns(); selectionChanged();
});
const refilter = () => { if (renderRuns()) selectionChanged(); };
let rft = 0; $('#runFilter').oninput = () => { clearTimeout(rft); rft = setTimeout(refilter, 200); };
$('#rAll').onclick = () => { S.shown.forEach(r => { S.want.add(r.name); S.sel.add(r.name); }); paintRuns(); selectionChanged(); };
$('#rNone').onclick = () => { S.shown.forEach(r => { S.want.delete(r.name); S.sel.delete(r.name); }); paintRuns(); selectionChanged(); };
$('#rInv').onclick = () => { S.shown.forEach(r => { if (S.want.has(r.name)) { S.want.delete(r.name); S.sel.delete(r.name); } else { S.want.add(r.name); S.sel.add(r.name); } }); paintRuns(); selectionChanged(); };
$('#runSort').onchange = e => { S.sort.by = e.target.value; S.sort.dir = S.sort.by === 'name' ? 1 : -1; syncSort(); refilter(); };
$('#sortDir').onclick = () => { S.sort.dir *= -1; syncSort(); refilter(); };
function syncSort() { $('#sortDir').textContent = S.sort.by === 'name' ? (S.sort.dir > 0 ? 'A→Z' : 'Z→A') : S.sort.by === 'size' ? (S.sort.dir > 0 ? 'Small first' : 'Large first') : (S.sort.dir > 0 ? 'Oldest first' : 'Newest first'); }
document.querySelectorAll('.fopts').forEach(box => box.addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return; const o = FO[box.dataset.for]; o[b.dataset.o] = !o[b.dataset.o]; b.classList.toggle('on', o[b.dataset.o]);
  box.dataset.for === 'run' ? refilter() : renderContent();
}));
let tf = 0; $('#tagFilter').oninput = () => { clearTimeout(tf); tf = setTimeout(renderContent, 180); };
$('#collapseAll').onclick = () => { document.querySelectorAll('.group:not(.col) .ghead').forEach(h => h.click()); };
$('#expandAll').onclick = () => { document.querySelectorAll('.group.col .ghead').forEach(h => h.click()); };



function bindSettings() {
  const bind = (id, key, kind, after) => {
    const e = $('#' + id); if (kind === 'chk') e.checked = SET[key]; else e.value = SET[key];
    e.addEventListener(kind === 'chk' ? 'change' : 'input', () => {
      SET[key] = kind === 'chk' ? e.checked : kind === 'num' ? +e.value : e.value; saveSet(); after && after();
    });
  };
  // smoothing: slider + typed value, redraw coalesced to one frame
  const sl = $('#smooth'), nu = $('#smoothN'); let sraf = 0;
  const setSmooth = v => { v = Math.min(0.99, Math.max(0, +v || 0)); SET.smooth = v; sl.value = nu.value = v; if (!sraf) sraf = requestAnimationFrame(() => { sraf = 0; redrawAll(true); }); };
  sl.value = nu.value = SET.smooth; sl.oninput = () => setSmooth(sl.value); nu.onchange = () => setSmooth(nu.value);
  bind('xaxis', 'xaxis', 'str', () => { S.ctrls.forEach(c => c.chart && c.chart.view && (c.chart.view.x = null)); redrawAll(true); });
  bind('ylog', 'ylog', 'chk', () => redrawAll()); bind('clip', 'clip', 'chk', () => redrawAll()); bind('raw', 'raw', 'chk', () => redrawAll());
  // chart width decides the column count (works on phones too)
  bind('cardW', 'cardW', 'num', () => { $('#cardWV').textContent = SET.cardW; document.querySelectorAll('.grid').forEach(g => g.style.gridTemplateColumns = gridCols()); });
  $('#cardWV').textContent = SET.cardW;
  bind('histMode', 'histMode', 'str', () => redrawAll());
  bind('tipOn', 'tooltipOn', 'chk'); bind('tipSort', 'tooltipSort', 'str');
  const unpin = () => { SET.pinned = []; renderContent(); };
  $('#unpinTb').onclick = unpin;
  bind('maxPoints', 'maxPoints', 'num', reloadAll);
  // auto refresh: off by default, custom interval, minimum 5s
  const ao = $('#arOn'), as = $('#arSec'); as.value = SET.arSec;
  const setAuto = () => { SET.arSec = Math.max(5, Math.round(+as.value) || 30); as.value = SET.arSec; SET.refresh = ao.checked ? SET.arSec : 0; startPoll(); };
  ao.checked = SET.refresh > 0; ao.onchange = setAuto; as.onchange = setAuto;
  const eff = () => SET.theme === 'auto' ? (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark') : SET.theme;
  const applyTheme = () => { document.documentElement.dataset.theme = SET.theme; $('#themeBtn').title = 'Theme: ' + eff(); TH = null; redrawAll(); };
  $('#themeBtn').onclick = () => { SET.theme = eff() === 'dark' ? 'light' : 'dark'; applyTheme(); };   // always flips what you currently see
  applyTheme();
  matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => { TH = null; redrawAll(); });
}



let pollT = 0, busy = false;
function setStatus(ok) { const s = $('#status'); s.className = ok ? 'ok' : 'bad'; $('#stxt').textContent = ok ? 'updated ' + new Date().toLocaleTimeString() : 'disconnected'; }
async function poll(force) {
  if (busy || (!force && !(SET.refresh > 0)) || (document.hidden && !force)) return; busy = true;
  try {
    const d = await api('api/runs', force ? { refresh: 1 } : {}), old = new Map(S.runs.map(r => [r.name, r.rev])), changed = new Set();
    let listChanged = d.runs.length !== S.runs.length;
    for (const r of d.runs) { if (!old.has(r.name)) listChanged = true; else if (old.get(r.name) !== r.rev && S.sel.has(r.name)) changed.add(r.name); }
    S.runs = d.runs; if (listChanged || changed.size || force) renderRuns();
    setStatus(true);
    if (changed.size || force) {
      const t = await api('api/tags', { run: [...S.sel] }), sig = JSON.stringify([t.scalars, t.histograms, t.other, t.layout]);
      S.tags = t;
      if (sig !== S.sig) { S.sig = sig; renderTabs(); renderContent(); }
      else S.ctrls.forEach(c => { if (force || c.runs.some(r => changed.has(r))) { c.dirty = true; if (c.visible) c.activate(); } });
    }
  } catch (e) { setStatus(false); }
  busy = false;
}
function startPoll() { clearInterval(pollT); if (SET.refresh > 0) pollT = setInterval(poll, SET.refresh * 1000); }
document.addEventListener('visibilitychange', () => { if (!document.hidden && SET.refresh > 0) poll(); });
$('#reload').onclick = () => poll(true);


// boot

(async function () {
  try {
    S.cfg = await api('api/config'); document.title = S.cfg.title; api('api/keep', {}).catch(() => { });   // fresh page: release anything a previous tab left loaded
    if (!store.get('settings', {}).maxPoints) SET.maxPoints = S.cfg.samples.scalars;
    $('#maxPoints').value = SET.maxPoints;
    S.hist = S.cfg.samples.histograms;
    bindSettings();
    S.runs = (await api('api/runs')).runs;
    S.runs.forEach(r => colorOf(r.name)); { const nm = new Set(S.runs.map(r => r.name)); S.want = new Set([...S.want].filter(n => nm.has(n))); }
    syncSort();
    renderRuns(); renderTabs(); setStatus(true);
    if (S.sel.size) await loadTags(); renderContent(); startPoll();
  } catch (e) { setStatus(false); $('#content').innerHTML = `<div class="empty"><div><b>Cannot reach server</b>${esc(e.message)}</div></div>`; }
})();


// docks (left: runs, right: settings): expandable, resizable, remembered
function dock(side) {
  const L = side === 'left', box = $(L ? '#side' : '#settings'), rz = $(L ? '#rzL' : '#rzR'), rail = L ? $('#leftRail') : null, kO = L ? 'leftOpen' : 'rightOpen', kW = L ? 'leftW' : 'rightW', v = L ? '--lw' : '--rw';
  const apply = () => { const o = SET[kO]; box.classList.toggle('hide', !o); rz.classList.toggle('hide', !o); rail && rail.classList.toggle('hide', o); document.documentElement.style.setProperty(v, SET[kW] + 'px'); setTimeout(() => redrawAll(), 30); };
  const open = o => { SET[kO] = o; saveSet(); apply(); };
  $(L ? '#leftX' : '#rightX').onclick = () => open(false); if (rail) rail.onclick = () => open(true);
  rz.onpointerdown = e => {
    e.preventDefault(); rz.setPointerCapture(e.pointerId); rz.classList.add('drag');
    rz.onpointermove = ev => { const r = box.getBoundingClientRect(); SET[kW] = Math.round(Math.min(640, Math.max(180, L ? ev.clientX - r.left : r.right - ev.clientX))); document.documentElement.style.setProperty(v, SET[kW] + 'px'); };
    rz.onpointerup = () => { rz.onpointermove = rz.onpointerup = null; rz.classList.remove('drag'); saveSet(); redrawAll(); };
  };
  apply(); return open;
}
const openLeft = dock('left'), openRight = dock('right');
$('#gearI').innerHTML = ICON.gear;
$('#setBtn').onclick = () => openRight(!SET.rightOpen);
S.pinsChanged = () => { $('#unpinTb').style.display = SET.pinned.length ? '' : 'none'; };

// header tabs: wheel scroll + edge arrows
(function () {
  const w = $('#tabsWrap'), t = $('#tabs'), upd = () => { w.classList.toggle('l', t.scrollLeft > 4); w.classList.toggle('r', t.scrollLeft + t.clientWidth < t.scrollWidth - 4); };
  t.addEventListener('wheel', e => { if (t.scrollWidth > t.clientWidth) { e.preventDefault(); t.scrollBy({ left: e.deltaY + e.deltaX, behavior: 'auto' }); } }, { passive: false });
  t.addEventListener('scroll', upd); addEventListener('resize', upd); new MutationObserver(upd).observe(t, { childList: true, subtree: true });
  $('#tabL').onclick = () => t.scrollBy({ left: -240 }); $('#tabR').onclick = () => t.scrollBy({ left: 240 });
  setTimeout(upd, 50);
})();

addEventListener('popstate', () => { S.tab = tabFromUrl(); renderTabs(); renderContent(); });

// persist everything across refreshes (cheap: only writes when something changed)
(function () {
  let last = '';
  const snap = () => {
    const ui = {};
    for (const [k, id] of [['run', '#runFilter'], ['tag', '#tagFilter']]) { const q = $(id).value; ui[k] = q ? Object.assign({ q }, FO[k]) : { q: '' }; }
    store.set('settings', SET); store.set('gstate', S.gstate); store.set('want', [...S.want]); store.set('sort', S.sort); store.set('ui', ui);
    const s = JSON.stringify(_mem); if (s !== last) { last = s; store.flush(); }
  };
  setInterval(snap, 700); addEventListener('pagehide', snap); addEventListener('beforeunload', snap);
  document.addEventListener('visibilitychange', () => document.hidden && snap());
})();

// hide floating tooltips when the page scrolls under a stationary mouse
$('#main').addEventListener('scroll', () => document.querySelectorAll('.tip').forEach(t => t.style.display = 'none'), { passive: true });
