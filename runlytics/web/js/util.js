'use strict';
/* Runlytics UI: no dependencies. Canvas charts, lazy cards, virtualized run list. */
const $ = (s, r = document) => r.querySelector(s);
const el = (t, c, h) => { const e = document.createElement(t); if (c) e.className = c; if (h != null) e.innerHTML = h; return e; };
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const ICON = {
  max: '<path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>',
  reset: '<path d="M1 4v6h6"/><path d="M3.5 15a9 9 0 1 0 2.1-9.4L1 10"/>',
  png: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/>',
  csv: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18"/>',
  chev: '<path d="M6 9l6 6 6-6"/>',
  more: '<circle cx="12" cy="5" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="12" cy="19" r="1.6"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  pin: '<path d="M12 17v5M9 3h6l-1 7 3 3v2H7v-2l3-3z"/>',
  rt: '<path d="M9 6l6 6-6 6"/>', lt: '<path d="M15 6l-6 6 6 6"/>'
};
const icon = n => `<svg viewBox="0 0 24 24">${ICON[n]}</svg>`;


// state

// State survives page refreshes (localStorage) but is discarded when the server was restarted (new boot id = new dashboard instance).
const _KEY = 'runlytics:state', _BOOT = String(window.__BOOT__ || '');
let _mem = {};
try { const r = JSON.parse(localStorage.getItem(_KEY) || 'null'); if (r && r.boot === _BOOT && r.d) _mem = r.d; } catch (e) { }
const store = { get(k, d) { return k in _mem ? _mem[k] : d; }, set(k, v) { _mem[k] = v; },
  flush() { try { localStorage.setItem(_KEY, JSON.stringify({ boot: _BOOT, d: _mem })); } catch (e) { } } };
const TAB_KEYS = ['scalars', 'timeseries', 'histograms', 'images', 'graphs', 'text', 'audio', 'projector', 'pr_curves', 'hparams', 'custom_scalars', 'mesh'];
const tabFromUrl = () => { const seg = location.pathname.split('/').filter(Boolean).pop(); return TAB_KEYS.includes(seg) ? seg : 'scalars'; };
const SET = Object.assign({ smooth: 0.6, xaxis: 'step', ylog: false, clip: false, raw: true, cardW: 360, arSec: 30, histMode: 'offset',
  maxPoints: 1500, refresh: 0, theme: 'auto', leftW: 280, rightW: 280, leftOpen: true, rightOpen: false, pinned: [], ignoreSmoothY: false, tooltipSort: 'default', tooltipOn: true, yLinkHint: 1, hscale: 1 }, store.get('settings', {}));
const S = { runs: [], sel: new Set(), shown: [], tags: { scalars: {}, histograms: {}, other: {}, layout: {} }, tab: tabFromUrl(),
  gstate: store.get('gstate', {}), cfg: {}, sig: '', ctrls: new Map(), colors: new Map(), hist: 50 };
const saveSet = () => store.set('settings', SET);


// utils

let _act = 0; const _q = [];
function _pump() { while (_act < 4 && _q.length) { const j = _q.shift(); _act++; j().finally(() => { _act--; _pump(); }); } }
function api(path, params) {
  const u = new URL(path, location.href);
  for (const [k, v] of Object.entries(params || {})) (Array.isArray(v) ? v : [v]).forEach(x => { if (x != null) u.searchParams.append(k, x); });
  return new Promise((ok, no) => {
    _q.push(() => fetch(u).then(r => { if (!r.ok) throw new Error(path + ' ' + r.status); return r.json(); }).then(ok, no));
    _pump();
  });
}
const PAL = ['#ff5d3a', '#35d0c2', '#7c9cff', '#ffc233', '#c77dff', '#5ee06c', '#ff7eb6', '#4dc3ff', '#ff9f43', '#a0e548'];
function colorOf(run) {
  let c = S.colors.get(run);
  if (!c) { const i = S.colors.size; c = i < PAL.length ? PAL[i] : `hsl(${(i * 137.508) % 360},68%,58%)`; S.colors.set(run, c); }
  return c;
}
function niceTicks(lo, hi, n) {
  if (!isFinite(lo) || !isFinite(hi)) return [];
  const span = hi - lo || 1, raw = span / Math.max(n, 1), mag = Math.pow(10, Math.floor(Math.log10(raw))), f = raw / mag;
  const step = (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * mag, out = [];
  if (!(step > 0) || !isFinite(step)) return [lo];
  const k0 = Math.ceil(lo / step), k1 = Math.floor(hi / step + 1e-9);
  for (let k = k0, c = 0; k <= k1 && c < 200; k++, c++) out.push(+(k * step).toPrecision(12));   // bounded: never loops forever on extreme values
  return out;
}
function logTicks(lo, hi) {
  if (!(lo > 0) || !isFinite(hi) || hi <= 0) return [1, 10];
  const a = Math.floor(Math.log10(lo)), b = Math.ceil(Math.log10(hi)), out = [];
  if (b - a > 60) return [lo, hi];
  for (let k = a; k <= b; k++) for (const m of (b - a <= 3 ? [1, 2, 5] : [1])) { const v = m * Math.pow(10, k); if (v >= lo * .999 && v <= hi * 1.001) out.push(v); }
  return out.length > 1 ? out : [lo, hi];
}
function fmt(v) {
  if (v == null || !isFinite(v) || v === 0) return String(v);
  const a = Math.abs(v);
  if (a >= 1e6 || a < 1e-3) return v.toExponential(2).replace(/\.?0+e/, 'e').replace('e+', 'e');
  return String(parseFloat(v.toPrecision(4)));
}
function fmtStep(v) {
  const a = Math.abs(v);
  if (a >= 1e6) return parseFloat((v / 1e6).toFixed(2)) + 'M';
  if (a >= 1e4) return parseFloat((v / 1e3).toFixed(1)) + 'k';
  return String(parseFloat(v.toFixed(2)));
}
function fmtDur(s) {
  s = Math.max(0, s);
  if (s < 60) return parseFloat(s.toFixed(s < 10 ? 1 : 0)) + 's';
  if (s < 3600) return Math.floor(s / 60) + 'm' + (Math.round(s % 60) ? Math.round(s % 60) + 's' : '');
  return Math.floor(s / 3600) + 'h' + String(Math.round((s % 3600) / 60)).padStart(2, '0') + 'm';
}
const p2 = n => String(n).padStart(2, '0');
function fmtWall(w, span) {
  const d = new Date(w * 1000);
  return span > 86400 ? `${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())}` : `${p2(d.getHours())}:${p2(d.getMinutes())}:${p2(d.getSeconds())}`;
}
function fmtX(v, span) { return SET.xaxis === 'wall' ? fmtWall(v, span) : SET.xaxis === 'relative' ? fmtDur(v) : fmtStep(v); }
function fmtSize(b) { return b < 1024 ? b + 'B' : b < 1 << 20 ? (b / 1024).toFixed(0) + 'K' : b < 1 << 30 ? (b / (1 << 20)).toFixed(1) + 'M' : (b / (1 << 30)).toFixed(2) + 'G'; }
function smooth(v, w) {
  if (!w) return v;
  // EMA computed on the offset from the first finite value: a constant series stays exactly constant (no float drift)
  const out = new Array(v.length); let last = 0, n = 0, base = null;
  for (let i = 0; i < v.length; i++) {
    const x = v[i];
    if (x == null || !isFinite(x)) { out[i] = x; continue; }
    if (base === null) base = x;
    last = last * w + (1 - w) * (x - base); n++;
    out[i] = base + last / (1 - Math.pow(w, n));
  }
  return out;
}
function nearest(xs, x) {
  if (xs.length < 2) return 0;
  let lo = 0, hi = xs.length - 1;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (xs[m] < x) lo = m; else hi = m; }
  return Math.abs(xs[lo] - x) <= Math.abs(xs[hi] - x) ? lo : hi;
}
function download(name, blob) { const a = el('a'); a.href = URL.createObjectURL(blob); a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000); }
function rx(v) { try { return new RegExp(v, 'i'); } catch (e) { return new RegExp(v.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i'); } }
let TH = null;
function th() {
  if (!TH) { const cs = getComputedStyle(document.documentElement), g = n => cs.getPropertyValue(n).trim(); TH = { card: g('--card'), line: g('--line'), grid: g('--grid'), text: g('--text'), dim: g('--dim'), accent: g('--accent') }; }
  return TH;
}
const MONO = '11px ui-monospace,Menlo,Consolas,monospace';


// minimal markdown: **bold**, *italic*, `code`, line breaks (input is escaped first)
function mdLite(t) {
  return esc(t).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<i>$2</i>').replace(/\n/g, '<br>');
}

// text filter with VS Code style options: match case, whole word, regex
function mkFilter(text, o) {
  if (!text) return () => true;
  const esc_ = t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); let re;
  try { re = new RegExp(o.word ? '\\b(?:' + (o.regex ? text : esc_(text)) + ')\\b' : (o.regex ? text : esc_(text)), o.case ? '' : 'i'); }
  catch (e) { re = new RegExp(esc_(text), o.case ? '' : 'i'); }
  return s => re.test(s);
}
const FO = { run: { case: false, word: false, regex: false }, tag: { case: false, word: false, regex: false } };
function toHex(c) { const g = document.createElement('canvas').getContext('2d'); g.fillStyle = '#000'; g.fillStyle = c; return g.fillStyle; }

// colour ramp: pale at the low end of a range, fully saturated at the high end (used by histograms: -inf -> +inf)
function mixHex(a, b, t) {
  const p = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16)), x = p(toHex(a)), y = p(toHex(b));
  return '#' + x.map((v, i) => Math.round(v + (y[i] - v) * t).toString(16).padStart(2, '0')).join('');
}
