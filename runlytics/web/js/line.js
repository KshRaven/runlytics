'use strict';
/* Line chart (scalars). */

class LineChart extends Chart {
  constructor(card, tag, runs, tags) {
    super(card); this.tag = tag; this.runs = runs; this.tags = tags || null; this.series = []; this.view = null; this.log = null; this.nan = 0;
    this.cv.addEventListener('mousedown', e => {
      if (e.button !== 0 || !this.geo) return;
      this.drag = { x: this.mouse.x, y: this.mouse.y };
      const up = () => { window.removeEventListener('mouseup', up); this.endDrag(); };
      window.addEventListener('mouseup', up);
    });
    this.cv.addEventListener('dblclick', () => this.reset());
  }
  isLog() { return this.log === null ? SET.ylog : this.log; }
  async load(range) {
    try {
      const tags = this.tags || [this.tag], multi = !!this.tags && tags.length > 1; this.series = [];
      for (const tag of tags) {
        const p = { tag, run: this.runs, max_points: SET.maxPoints };
        if (range) { p.min_step = Math.floor(range[0]); p.max_step = Math.ceil(range[1]); }
        const d = await api('api/scalars', p);
        for (const r of this.runs) if (d[r]) this.series.push(Object.assign({ run: multi ? `${r} · ${tag}` : r, ck: multi ? r + '\0' + tag : r, color: colorOf(multi ? r + '\0' + tag : r) }, d[r]));
      }
      this.nan = this.series.reduce((a, s) => a + s.nan, 0);
      $('.cn', this.card).textContent = this.nan ? `⚠ ${this.nan} NaN/inf` : '';
      this.msg(this.series.length ? '' : 'No data'); this.prep();
    } catch (e) { this.msg('Error: ' + e.message); }
    this.schedule();
  }
  prep() {
    for (const s of this.series) {
      s.x = SET.xaxis === 'step' ? s.s : SET.xaxis === 'wall' ? s.w : s.w.map(t => t - s.t0);
      s.y = smooth(s.v, SET.smooth); s.color = colorOf(s.ck);
    }
    this.schedule();
  }
  reset() { const z = this.view && this.view.x; this.view = null; if (z) this.load(); else this.schedule(); }
  geom() {
    const log = this.isLog(), v = this.view; let x0 = Infinity, x1 = -Infinity;
    for (const s of this.series) for (let i = 0; i < s.x.length; i++) { const x = s.x[i]; if (x < x0) x0 = x; if (x > x1) x1 = x; }
    if (!isFinite(x0)) return null;
    if (v && v.x) { x0 = v.x[0]; x1 = v.x[1]; }
    if (x1 <= x0) { x0 -= 1; x1 += 1; }
    let y0, y1;
    if (v && v.y) { y0 = v.y[0]; y1 = v.y[1]; }
    else {
      const ys = []; y0 = Infinity; y1 = -Infinity;
      for (const s of this.series) for (let i = 0; i < s.y.length; i++) {
        const x = s.x[i], y = s.y[i];
        if (x < x0 || x > x1 || y == null || !isFinite(y) || (log && y <= 0)) continue;
        if (SET.clip) ys.push(y); else { if (y < y0) y0 = y; if (y > y1) y1 = y; }
      }
      if (SET.clip && ys.length) { ys.sort((a, b) => a - b); const q = p => ys[Math.min(ys.length - 1, Math.floor(p * (ys.length - 1)))]; y0 = q(.05); y1 = q(.95); const pad = (y1 - y0) * .3; if (!log) { y0 -= pad; y1 += pad; } }
      if (!isFinite(y0)) { y0 = log ? 1 : 0; y1 = log ? 10 : 1; }
      if (log) { if (y1 <= y0) { y0 /= 2; y1 *= 2; } else { y0 /= 1.1; y1 *= 1.1; } }
      else {
        // a (numerically) constant series gets a fixed band around its value instead of zooming into float noise
        const m = Math.max(Math.abs(y0), Math.abs(y1));
        if (y1 - y0 <= m * 1e-6) { const c = (y0 + y1) / 2, pad = m * .1 || 1; y0 = c - pad; y1 = c + pad; }
        else { const pad = (y1 - y0) * .06; y0 -= pad; y1 += pad; }
      }
    }
    const ty = log ? Math.log10 : (a => a), tI = log ? (a => Math.pow(10, a)) : (a => a);
    const c = this.ctx; c.font = MONO;
    const yt = log ? logTicks(y0, y1) : niceTicks(y0, y1, Math.max(2, Math.floor(this.h / 48)));
    const L = Math.min(90, Math.max(...yt.map(t => c.measureText(fmt(t)).width), 20) + 14), R = 14, T = 10, B = 24;
    const PX = 8;   // first and last points are inset so they never sit on the frame
    const pw = this.w - L - R, ph = this.h - T - B;
    if (pw < 20 || ph < 20) return null;
    const ty0 = ty(y0), ty1 = ty(y1);
    return { x0, x1, y0, y1, log, yt, xt: niceTicks(x0, x1, Math.max(2, Math.floor(pw / 90))), L, R, T, B, pw, ph, tI,
      px: x => L + PX + (x - x0) / (x1 - x0) * (pw - 2 * PX), py: y => T + (1 - (ty(y) - ty0) / (ty1 - ty0)) * ph,
      ix: p => x0 + (p - L - PX) / (pw - 2 * PX) * (x1 - x0), iy: p => tI(ty0 + (1 - (p - T) / ph) * (ty1 - ty0)) };
  }
  trace(arr, s, g) {
    const c = this.ctx; c.beginPath(); let pen = false;
    for (let i = 0; i < arr.length; i++) {
      const y = arr[i];
      if (y == null || !isFinite(y) || (g.log && y <= 0)) { pen = false; continue; }
      const X = g.px(s.x[i]), Y = g.py(y);
      if (pen) c.lineTo(X, Y); else c.moveTo(X, Y);
      pen = true;
    }
    c.stroke();
  }
  draw() {
    const c = this.ctx, T = th(), W = this.w, H = this.h;
    c.clearRect(0, 0, W, H); c.fillStyle = T.card; c.fillRect(0, 0, W, H);
    const g = this.geo = this.geom(); if (!g) return;
    c.font = MONO; c.lineWidth = 1; c.strokeStyle = T.grid; c.fillStyle = T.dim; c.textAlign = 'right'; c.textBaseline = 'middle';
    for (const t of g.yt) { const y = Math.round(g.py(t)) + .5; c.beginPath(); c.moveTo(g.L, y); c.lineTo(W - g.R, y); c.stroke(); c.fillText(fmt(t), g.L - 6, y); }
    c.textAlign = 'center'; c.textBaseline = 'top';
    const span = g.x1 - g.x0;
    g.xt.forEach(t => { const x = Math.round(g.px(t)) + .5; c.beginPath(); c.moveTo(x, g.T); c.lineTo(x, H - g.B); c.stroke(); c.fillText(fmtX(t, span), Math.min(W - 24, Math.max(g.L + 10, x)), H - g.B + 6); });
    c.save(); c.beginPath(); c.rect(g.L, g.T, g.pw, g.ph); c.clip(); c.lineJoin = 'round';
    for (const s of this.series) {
      c.strokeStyle = s.color;
      if (SET.smooth > 0 && SET.raw) { c.globalAlpha = .22; c.lineWidth = 1.2; this.trace(s.v, s, g); }
      c.globalAlpha = 1; c.lineWidth = 1.8; this.trace(s.y, s, g);
      if (s.x.length * 8 < g.pw) { c.fillStyle = s.color; for (let i = 0; i < s.x.length; i++) { const y = s.y[i]; if (y == null || !isFinite(y) || (g.log && y <= 0)) continue; c.beginPath(); c.arc(g.px(s.x[i]), g.py(y), 2.2, 0, 6.3); c.fill(); } }
    }
    c.restore();
    if (this.drag && this.mouse) {
      const a = this.drag, m = this.mouse; c.fillStyle = 'rgba(255,93,58,.12)'; c.strokeStyle = T.accent; c.setLineDash([4, 3]);
      c.fillRect(a.x, a.y, m.x - a.x, m.y - a.y); c.strokeRect(a.x, a.y, m.x - a.x, m.y - a.y); c.setLineDash([]); this.tip.style.display = 'none'; return;
    }
    const m = this.mouse;
    if (SET.tooltipOn && m && m.x >= g.L && m.x <= W - g.R && m.y >= g.T && m.y <= H - g.B) {
      const hx = g.ix(m.x); let rows = '', ax = null;
      c.strokeStyle = T.dim; c.setLineDash([3, 3]); c.beginPath(); c.moveTo(m.x, g.T); c.lineTo(m.x, H - g.B); c.stroke(); c.setLineDash([]);
      const list = []; let order = this.series;
      for (const s of order) {
        if (!s.x.length) continue;
        const i = nearest(s.x, hx), y = s.y[i], X = g.px(s.x[i]);
        if (ax == null || Math.abs(X - m.x) < Math.abs(ax - m.x)) ax = X;
        if (isFinite(y) && !(g.log && y <= 0)) { c.fillStyle = s.color; c.strokeStyle = T.card; c.lineWidth = 2; c.beginPath(); c.arc(X, g.py(y), 4, 0, 6.3); c.fill(); c.stroke(); }
        const tm = SET.xaxis === 'step' ? '' : ` <span>#${s.s[i]}</span>`;
        list.push([y, s.run, `<div class="r"><i style="background:${s.color}"></i><b>${esc(s.run)}</b>${fmt(y)}${SET.smooth > 0 ? ` <span>(${fmt(s.v[i])})</span>` : ''}${tm}</div>`]);
      }
      const ts = SET.tooltipSort; if (ts === 'asc') list.sort((a, b) => a[0] - b[0]); else if (ts === 'desc') list.sort((a, b) => b[0] - a[0]); else if (ts === 'name') list.sort((a, b) => a[1].localeCompare(b[1]));
      rows = list.map(r => r[2]).join('');
      this.placeTip(`<div class="h">${fmtX(hx, span)}${SET.xaxis === 'step' ? '' : ''}</div>${rows}`);
    } else this.tip.style.display = 'none';
  }
  onDrag() { this.schedule(); }
  endDrag() {
    const a = this.drag, m = this.mouse, g = this.geo; this.drag = null;
    if (!a || !m || !g) return this.schedule();
    const dx = Math.abs(m.x - a.x), dy = Math.abs(m.y - a.y), v = this.view || {};
    if (dx > 6) { const p = [g.ix(Math.min(a.x, m.x)), g.ix(Math.max(a.x, m.x))]; v.x = p; }
    if (dy > 6) { const p = [g.iy(Math.max(a.y, m.y)), g.iy(Math.min(a.y, m.y))]; v.y = p; }
    if (dx > 6 || dy > 6) { this.view = v; if (dx > 6 && SET.xaxis === 'step') this.load(v.x); }
    this.schedule();
  }
  csv() {
    let o = 'run,step,wall_time,value,smoothed\n';
    for (const s of this.series) for (let i = 0; i < s.s.length; i++) o += `"${s.run.replace(/"/g, '""')}",${s.s[i]},${s.w[i]},${s.v[i]},${s.y[i]}\n`;
    download(this.tag.replace(/[^\w.-]+/g, '_') + '.csv', new Blob([o], { type: 'text/csv' }));
  }
}

