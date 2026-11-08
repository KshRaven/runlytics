'use strict';
/* Views for structured summaries: PR curves, embeddings, mesh, graphs, hyper-parameters. */

// Canvas view over one run/tag with an optional step slider (data comes from api/data).
class StepChart extends Chart {
  constructor(card, tag, run, kind) {
    super(card); this.tag = tag; this.run = run; this.kind = kind; this.d = null; this.follow = true; this.i = null;
    this.sl = el('input', 'ov'); this.sl.type = 'range'; this.sl.title = 'Step';
    this.sl.oninput = () => {
      const k = +this.sl.value, last = k === this.d.rows.length - 1;
      this.follow = last; this.i = this.d.rows[k][0]; this.fetch(last ? null : this.i);
    };
    this.body.append(this.sl);
  }
  async load() { await this.fetch(this.follow ? null : this.i); }
  async fetch(i) {
    try {
      const p = { run: this.run, tag: this.tag, kind: this.kind }; if (i != null) p.i = i;
      const d = await api('api/data', p); this.d = d; this.i = d.i;
      const k = Math.max(0, d.rows.findIndex(r => r[0] === d.i));
      this.sl.max = d.rows.length - 1; this.sl.value = k; this.sl.style.display = d.rows.length > 1 ? '' : 'none';
      $('.cn', this.card).textContent = `step ${d.rows[k][1]}`; this.msg('');
      this.prep(d.obj);
    } catch (e) { this.msg('Error: ' + e.message); }
    this.schedule();
  }
  prep() { }
  base() { const c = this.ctx, T = th(); c.clearRect(0, 0, this.w, this.h); c.fillStyle = T.card; c.fillRect(0, 0, this.w, this.h); return [c, T]; }
}

class PRChart extends StepChart {
  constructor(card, tag, run) { super(card, tag, run, 'pr_curves'); }
  draw() {
    const [c, T] = this.base(), o = this.d && this.d.obj; if (!o) return;
    const L = 44, R = 14, Tp = 10, B = 40, pw = this.w - L - R, ph = this.h - Tp - B; if (pw < 20 || ph < 20) return;
    const px = x => L + x * pw, py = y => Tp + (1 - y) * ph; this.geo = { px, py, L, pw };
    c.font = MONO; c.lineWidth = 1; c.strokeStyle = T.grid; c.fillStyle = T.dim;
    c.textAlign = 'right'; c.textBaseline = 'middle';
    for (let t = 0; t <= 1.001; t += .2) { const y = Math.round(py(t)) + .5; c.beginPath(); c.moveTo(L, y); c.lineTo(L + pw, y); c.stroke(); c.fillText(t.toFixed(1), L - 6, y); }
    c.textAlign = 'center'; c.textBaseline = 'top';
    for (let t = 0; t <= 1.001; t += .2) { const x = Math.round(px(t)) + .5; c.beginPath(); c.moveTo(x, Tp); c.lineTo(x, Tp + ph); c.stroke(); c.fillText(t.toFixed(1), x, Tp + ph + 5); }
    c.fillText('recall', L + pw / 2, Tp + ph + 20);
    c.save(); c.translate(11, Tp + ph / 2); c.rotate(-Math.PI / 2); c.fillText('precision', 0, 0); c.restore();
    const col = colorOf(this.run), n = o.recall.length;
    c.beginPath(); c.moveTo(px(o.recall[0]), py(0));
    for (let i = 0; i < n; i++) c.lineTo(px(o.recall[i]), py(o.precision[i]));
    c.lineTo(px(o.recall[n - 1]), py(0)); c.closePath(); c.globalAlpha = .12; c.fillStyle = col; c.fill(); c.globalAlpha = 1;
    c.strokeStyle = col; c.lineWidth = 2; c.beginPath();
    for (let i = 0; i < n; i++) { const X = px(o.recall[i]), Y = py(o.precision[i]); i ? c.lineTo(X, Y) : c.moveTo(X, Y); }
    c.stroke();
    const m = this.mouse;
    if (m && m.x >= L && m.x <= L + pw && m.y >= Tp && m.y <= Tp + ph) {
      let best = 0, bd = 1e18;
      for (let i = 0; i < n; i++) { const dx = px(o.recall[i]) - m.x, dy = py(o.precision[i]) - m.y, dd = dx * dx + dy * dy; if (dd < bd) { bd = dd; best = i; } }
      c.fillStyle = col; c.strokeStyle = T.card; c.lineWidth = 2; c.beginPath(); c.arc(px(o.recall[best]), py(o.precision[best]), 4.5, 0, 6.3); c.fill(); c.stroke();
      this.placeTip(`<div class="h">threshold ${(best / Math.max(1, n - 1)).toFixed(3)}</div><div class="r"><b>precision</b>${fmt(o.precision[best])}</div><div class="r"><b>recall</b>${fmt(o.recall[best])}</div>` +
        `<div class="r"><b>TP / FP</b>${fmt(o.tp[best])} / ${fmt(o.fp[best])}</div><div class="r"><b>TN / FN</b>${fmt(o.tn[best])} / ${fmt(o.fn[best])}</div>`);
    } else this.tip.style.display = 'none';
  }
}

// Shared 3D orbit view: drag to rotate, wheel to zoom, double-click to reset.
class OrbitChart extends StepChart {
  constructor(card, tag, run, kind) {
    super(card, tag, run, kind); this.yaw = 0; this.pitch = 0; this.zoom = 1; this.pts = null;
    this.cv.addEventListener('mousedown', e => {
      if (e.button !== 0) return; this.drag = { x: this.mouse.x, y: this.mouse.y, yaw: this.yaw, pitch: this.pitch };
      const up = () => { removeEventListener('mouseup', up); this.drag = null; }; addEventListener('mouseup', up);
    });
    this.cv.addEventListener('wheel', e => { e.preventDefault(); this.zoom = Math.min(8, Math.max(.2, this.zoom * (e.deltaY < 0 ? 1.1 : 1 / 1.1))); this.schedule(); }, { passive: false });
    this.cv.addEventListener('dblclick', () => { this.yaw = this.pitch = 0; this.zoom = 1; this.schedule(); });
  }
  onDrag() {
    const d = this.drag, m = this.mouse; this.yaw = d.yaw + (m.x - d.x) * .01;
    this.pitch = Math.max(-1.55, Math.min(1.55, d.pitch + (m.y - d.y) * .01)); this.schedule();
  }
  // Normalise raw points to a unit cube centred on the origin.
  fit(raw) {
    const lo = [1e30, 1e30, 1e30], hi = [-1e30, -1e30, -1e30];
    for (const p of raw) for (let k = 0; k < 3; k++) { if (p[k] < lo[k]) lo[k] = p[k]; if (p[k] > hi[k]) hi[k] = p[k]; }
    const s = Math.max(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]) / 2 || 1;
    return raw.map(p => [(p[0] - (lo[0] + hi[0]) / 2) / s, (p[1] - (lo[1] + hi[1]) / 2) / s, (p[2] - (lo[2] + hi[2]) / 2) / s]);
  }
  hover(i) { return ''; }
  draw() {
    const [c, T] = this.base(); if (!this.pts) return;
    const cy = Math.cos(this.yaw), sy = Math.sin(this.yaw), cp = Math.cos(this.pitch), sp = Math.sin(this.pitch);
    const S_ = Math.min(this.w, this.h - 24) * .42 * this.zoom, cx = this.w / 2, cz = (this.h - 16) / 2;
    const P = this.pts.map(p => { const x1 = p[0] * cy + p[2] * sy, z1 = -p[0] * sy + p[2] * cy; return [cx + x1 * S_, cz - (p[1] * cp - z1 * sp) * S_]; });
    if (this.faces) {
      c.strokeStyle = T.dim; c.globalAlpha = .28; c.lineWidth = 1; c.beginPath();
      for (const f of this.faces) { c.moveTo(P[f[0]][0], P[f[0]][1]); for (let k = 1; k < f.length; k++) c.lineTo(P[f[k]][0], P[f[k]][1]); c.closePath(); }
      c.stroke(); c.globalAlpha = 1;
    }
    const r = this.faces ? 1.6 : P.length > 2000 ? 2 : 3;
    for (let i = 0; i < P.length; i++) { c.fillStyle = this.cols[i]; c.fillRect(P[i][0] - r, P[i][1] - r, r * 2, r * 2); }
    const m = this.mouse; this.tip.style.display = 'none';
    if (m && !this.drag) {
      let best = -1, bd = 144;
      for (let i = 0; i < P.length; i++) { const dx = P[i][0] - m.x, dy = P[i][1] - m.y, dd = dx * dx + dy * dy; if (dd < bd) { bd = dd; best = i; } }
      if (best >= 0) {
        c.strokeStyle = T.text; c.lineWidth = 2; c.beginPath(); c.arc(P[best][0], P[best][1], 6, 0, 6.3); c.stroke();
        const h = this.hover(best); if (h) this.placeTip(h);
      }
    }
    this.drawLegend(c, T);
  }
  drawLegend() { }
}

class ProjectorChart extends OrbitChart {
  constructor(card, tag, run) { super(card, tag, run, 'projector'); this.col = 0; }
  prep(o) {
    if (!o) return; const [n, d] = o.shape, X = Float64Array.from(o.data), mean = new Float64Array(d);
    for (let i = 0; i < n; i++) for (let j = 0; j < d; j++) mean[j] += X[i * d + j] / n;
    for (let i = 0; i < n; i++) for (let j = 0; j < d; j++) X[i * d + j] -= mean[j];
    const comps = [], proj = Array.from({ length: n }, () => [0, 0, 0]);
    for (let k = 0; k < Math.min(3, d); k++) {          // power iteration with deflation
      let v = new Float64Array(d).map((_, j) => Math.sin(j * 12.9898 + k * 78.233) + 1.1);
      for (let it = 0; it < 40; it++) {
        const t = new Float64Array(n);
        for (let i = 0; i < n; i++) { let s = 0; for (let j = 0; j < d; j++) s += X[i * d + j] * v[j]; t[i] = s; }
        const w = new Float64Array(d);
        for (let i = 0; i < n; i++) for (let j = 0; j < d; j++) w[j] += X[i * d + j] * t[i];
        let nrm = 0; for (let j = 0; j < d; j++) nrm += w[j] * w[j]; nrm = Math.sqrt(nrm) || 1;
        for (let j = 0; j < d; j++) v[j] = w[j] / nrm;
      }
      for (let i = 0; i < n; i++) { let s = 0; for (let j = 0; j < d; j++) s += X[i * d + j] * v[j]; proj[i][k] = s; }
      for (let i = 0; i < n; i++) for (let j = 0; j < d; j++) X[i * d + j] -= proj[i][k] * v[j];
      comps.push(v);
    }
    this.pts = this.fit(proj); this.meta = o.metadata; this.header = o.header || [];
    const labels = this.meta ? this.meta.map(r => r[this.col]) : null, uniq = labels ? [...new Set(labels)] : [];
    this.legend = uniq.length && uniq.length <= 12 ? uniq : null;
    this.cols = labels ? labels.map(l => PAL[uniq.indexOf(l) % PAL.length]) : this.pts.map(() => colorOf(this.run));
  }
  hover(i) {
    if (!this.meta) return `<div class="h">point ${i}</div>`;
    return `<div class="h">point ${i}</div>` + this.meta[i].map((v, k) => `<div class="r"><b>${esc(this.header[k] || 'col' + k)}</b>${esc(v)}</div>`).join('');
  }
  drawLegend(c, T) {
    if (!this.legend) return; c.font = MONO; c.textAlign = 'left'; c.textBaseline = 'middle';
    this.legend.forEach((l, k) => { c.fillStyle = PAL[k % PAL.length]; c.fillRect(10, 12 + k * 15 - 4, 8, 8); c.fillStyle = T.text; c.fillText(String(l).slice(0, 24), 24, 12 + k * 15); });
  }
}

class MeshChart extends OrbitChart {
  constructor(card, tag, run) { super(card, tag, run, 'mesh'); }
  prep(o) {
    if (!o) return; this.pts = this.fit(o.v); this.faces = o.f && o.f.length && o.f.length < 60000 ? o.f : null;
    this.cols = o.c ? o.c.map(k => `rgb(${k[0]},${k[1]},${k[2]})`) : this.pts.map(() => colorOf(this.run));
  }
  hover(i) { const p = this.d.obj.v[i]; return `<div class="h">vertex ${i}</div><div class="r">${p.map(fmt).join(', ')}</div>`; }
}

// Model graph: layered left-to-right layout in SVG with pan / zoom and a node inspector.
class GraphView {
  constructor(card, tag, run) {
    this.card = card; this.run = run; this.body = $('.cbody', card); this.msgEl = $('.cmsg', card);
    this.box = el('div', 'graph'); this.body.append(this.box); this.k = 1; this.tx = 0; this.ty = 0;
  }
  msg(t) { this.msgEl.textContent = t || ''; }
  schedule() { } destroy() { }
  async load() {
    try {
      const d = await api('api/graph', { run: this.run }); this.nodes = d.nodes.slice(0, 3000);
      this.msg(d.nodes.length > 3000 ? `Showing first 3000 of ${d.nodes.length} nodes` : ''); this.build();
    } catch (e) { this.msg('Error: ' + e.message); }
  }
  build() {
    const nodes = this.nodes, by = new Map(nodes.map(n => [n.name, n])), layer = new Map(), busy = new Set();
    const depth = n => {
      if (layer.has(n.name)) return layer.get(n.name); if (busy.has(n.name)) return 0; busy.add(n.name);
      let d = 0; for (const i of n.inputs || []) { const p = by.get(i); if (p) d = Math.max(d, depth(p) + 1); }
      busy.delete(n.name); layer.set(n.name, d); return d;
    };
    const cols = []; nodes.forEach(n => { const d = depth(n); (cols[d] = cols[d] || []).push(n); });
    const W = 150, H = 32, GX = 70, GY = 14, pos = new Map(); let maxY = 0;
    cols.forEach((col, x) => col && col.forEach((n, y) => { pos.set(n.name, [x * (W + GX), y * (H + GY)]); maxY = Math.max(maxY, y * (H + GY) + H); }));
    const maxX = cols.length * (W + GX);
    let edges = '', boxes = ''; const ops = [...new Set(nodes.map(n => n.op))];
    for (const n of nodes) for (const i of n.inputs || []) {
      const a = pos.get(i), b = pos.get(n.name); if (!a) continue;
      const x1 = a[0] + W, y1 = a[1] + H / 2, x2 = b[0], y2 = b[1] + H / 2, mx = (x1 + x2) / 2;
      edges += `<path d="M${x1},${y1}C${mx},${y1} ${mx},${y2} ${x2},${y2}"/>`;
    }
    nodes.forEach((n, k) => {
      const p = pos.get(n.name), colr = PAL[ops.indexOf(n.op) % PAL.length], short = n.name.split('/').pop();
      boxes += `<g class="gn" data-k="${k}" transform="translate(${p[0]},${p[1]})"><rect width="${W}" height="${H}" rx="6" style="stroke:${colr}"/><text x="8" y="13">${esc(short.slice(0, 22))}</text><text x="8" y="25" class="op" style="fill:${colr}">${esc(String(n.op).slice(0, 24))}</text></g>`;
    });
    this.box.innerHTML = `<svg><g class="vp"><g class="ed">${edges}</g>${boxes}</g></svg><div class="ginfo"></div>`;
    this.svg = $('svg', this.box); this.vp = $('.vp', this.box); this.info = $('.ginfo', this.box);
    const fit = () => { const r = this.box.getBoundingClientRect(); this.k = Math.min(1, r.width / (maxX || 1), r.height / (maxY || 1)); this.tx = 10; this.ty = 10; this.apply(); };
    fit(); this.svg.addEventListener('dblclick', fit);
    this.svg.addEventListener('wheel', e => {
      e.preventDefault(); const r = this.svg.getBoundingClientRect(), f = e.deltaY < 0 ? 1.15 : 1 / 1.15, mx = e.clientX - r.left, my = e.clientY - r.top;
      this.tx = mx - (mx - this.tx) * f; this.ty = my - (my - this.ty) * f; this.k *= f; this.apply();
    }, { passive: false });
    this.svg.addEventListener('mousedown', e => {
      const s = { x: e.clientX, y: e.clientY, tx: this.tx, ty: this.ty };
      const mv = ev => { this.tx = s.tx + ev.clientX - s.x; this.ty = s.ty + ev.clientY - s.y; this.apply(); };
      const up = () => { removeEventListener('mousemove', mv); removeEventListener('mouseup', up); };
      addEventListener('mousemove', mv); addEventListener('mouseup', up);
    });
    this.svg.addEventListener('click', e => {
      const g = e.target.closest('.gn'); if (!g) { this.info.style.display = 'none'; return; }
      const n = nodes[+g.dataset.k]; this.info.style.display = 'block';
      this.info.innerHTML = `<b>${esc(n.name)}</b><br>op: ${esc(n.op)}${n.attrs ? `<br>${esc(n.attrs)}` : ''}<br>inputs: ${esc((n.inputs || []).join(', ') || '—')}`;
    });
  }
  apply() { this.vp.setAttribute('transform', `translate(${this.tx},${this.ty}) scale(${this.k})`); }
}

// Hyper-parameter table: one row per run, sortable columns, metric cells shaded by value.
class HParamsView {
  constructor(card, tag, runs) {
    this.card = card; this.runs = runs; this.body = $('.cbody', card); this.msgEl = $('.cmsg', card);
    this.box = el('div', 'hp'); this.body.append(this.box); this.sort = null; this.dir = 1;
  }
  msg(t) { this.msgEl.textContent = t || ''; }
  schedule() { } destroy() { }
  async load() {
    try { this.d = await api('api/hparams', { run: this.runs }); this.msg(this.d.rows.length ? '' : 'No data'); this.render(); }
    catch (e) { this.msg('Error: ' + e.message); }
  }
  render() {
    const d = this.d, cols = ['run', ...d.hparams, ...d.metrics], val = (r, c) => c === 'run' ? r.run : c in r.hparams ? r.hparams[c] : r.metrics[c];
    const rng = {}; for (const m of d.metrics) { const v = d.rows.map(r => r.metrics[m]).filter(x => x != null); rng[m] = [Math.min(...v), Math.max(...v)]; }
    const rows = [...d.rows]; if (this.sort) rows.sort((a, b) => { const x = val(a, this.sort), y = val(b, this.sort); return (x > y ? 1 : x < y ? -1 : 0) * this.dir; });
    let h = '<table><thead><tr>' + cols.map(c => `<th data-c="${esc(c)}" class="${d.metrics.includes(c) ? 'm' : ''}">${esc(c)}${this.sort === c ? (this.dir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('') + '</tr></thead><tbody>';
    for (const r of rows) {
      h += '<tr>' + cols.map(c => {
        const v = val(r, c);
        if (c === 'run') return `<td><i class="dot" style="background:${colorOf(r.run)}"></i>${esc(r.run)}</td>`;
        if (d.metrics.includes(c) && v != null) { const [a, b] = rng[c], p = b > a ? (v - a) / (b - a) * 100 : 100; return `<td class="m" style="background:linear-gradient(90deg,color-mix(in srgb,var(--accent) 35%,transparent) ${p}%,transparent ${p}%)">${fmt(v)}</td>`; }
        return `<td>${v == null ? '—' : esc(typeof v === 'number' ? fmt(v) : v)}</td>`;
      }).join('') + '</tr>';
    }
    this.box.innerHTML = h + '</tbody></table>';
    this.box.querySelectorAll('th').forEach(t => t.onclick = () => { const c = t.dataset.c; this.dir = this.sort === c ? -this.dir : 1; this.sort = c; this.render(); });
  }
}
