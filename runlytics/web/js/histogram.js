'use strict';
/* Histogram chart. */

class HistChart extends Chart {
  constructor(card, tag, run) { super(card); this.tag = tag; this.run = run; this.d = null; }
  get color() { return colorOf(this.run); }
  async load() {
    try {
      this.d = await api('api/histograms', { run: this.run, tag: this.tag, bins: 40, max_steps: S.hist });
      this.msg(this.d.steps.length ? '' : 'No data');
    } catch (e) { this.d = null; this.msg('Error: ' + e.message); }
    this.schedule();
  }
  layout(offset) {
    const c = this.ctx; c.font = MONO; const d = this.d, maxc = Math.max(1e-9, ...d.counts.map(r => Math.max(...r)));
    const L = offset ? 14 : 48, R = offset ? 54 : 14, T = 10, B = 24, pw = this.w - L - R, ph = this.h - T - B;
    return { maxc, L, R, T, B, pw, ph, bw: (d.max - d.min) / d.bins, px: x => L + (x - d.min) / (d.max - d.min) * pw };
  }
  draw() {
    const c = this.ctx, T = th(), W = this.w, H = this.h, d = this.d;
    c.clearRect(0, 0, W, H); c.fillStyle = T.card; c.fillRect(0, 0, W, H);
    if (!d || !d.steps.length) return;
    const off = SET.histMode === 'offset', g = this.layout(off), N = d.steps.length;
    if (g.pw < 20 || g.ph < 20) return;
    c.font = MONO; c.lineWidth = 1; c.textBaseline = 'top'; c.textAlign = 'center';
    niceTicks(d.min, d.max, Math.max(2, Math.floor(g.pw / 80))).forEach(t => {
      const x = Math.round(g.px(t)) + .5; c.strokeStyle = T.grid; c.beginPath(); c.moveTo(x, g.T); c.lineTo(x, H - g.B); c.stroke();
      c.fillStyle = T.dim; c.fillText(fmt(t), Math.min(W - 20, Math.max(g.L + 8, x)), H - g.B + 6);
    });
    const centers = j => g.px(d.min + (j + .5) * g.bw);
    // colour ramps with the step: the first (oldest) histogram is pale, the newest is fully saturated
    const shade = i => mixHex(this.color, T.card, .8 * (1 - (N > 1 ? i / (N - 1) : 1)));
    // offset mode: oldest histogram at the top, newest at the bottom (as in Tensorboard); each baseline is `sp` below the previous
    const hh = N > 1 ? Math.min(g.ph * .6, Math.max(20, g.ph * .35)) : g.ph, sp = N > 1 ? (g.ph - hh) / (N - 1) : 0;
    const base = i => g.T + hh + i * sp;
    this.sp = sp; this.hh = hh; this.g = g;
    const hov = this.hover = this.mouse ? this.pick(off, g, N) : null;
    if (off) {
      c.textAlign = 'left'; c.textBaseline = 'middle';
      for (let i = 0; i < N; i++) {
        const y0 = base(i), row = d.counts[i]; c.beginPath(); c.moveTo(g.L, y0);
        for (let j = 0; j < d.bins; j++) c.lineTo(centers(j), y0 - row[j] / g.maxc * hh);
        c.lineTo(g.L + g.pw, y0); c.lineTo(g.L + g.pw, y0); c.closePath();
        c.fillStyle = T.card; c.fill(); c.globalAlpha = .55; c.fillStyle = shade(i); c.fill(); c.globalAlpha = 1;
        c.strokeStyle = shade(i); c.lineWidth = hov && hov.i === i ? 2.2 : 1.2; c.stroke();
      }
      const every = Math.max(1, Math.ceil(N / 8)); c.fillStyle = T.dim;
      for (let i = 0; i < N; i += every) c.fillText(fmtStep(d.steps[i]), g.L + g.pw + 8, base(i));
    } else {
      c.textAlign = 'right'; c.textBaseline = 'middle';
      niceTicks(0, g.maxc, Math.max(2, Math.floor(g.ph / 45))).forEach(t => {
        const y = Math.round(g.T + g.ph - t / g.maxc * g.ph) + .5; c.strokeStyle = T.grid; c.beginPath(); c.moveTo(g.L, y); c.lineTo(W - g.R, y); c.stroke(); c.fillStyle = T.dim; c.fillText(fmt(t), g.L - 6, y);
      });
      for (let i = 0; i < N; i++) {
        c.strokeStyle = shade(i); c.globalAlpha = hov ? (hov.i === i ? 1 : .25) : 1; c.lineWidth = hov && hov.i === i ? 2.4 : 1.3; c.beginPath();
        for (let j = 0; j < d.bins; j++) { const x = centers(j), y = g.T + g.ph - d.counts[i][j] / g.maxc * g.ph; j ? c.lineTo(x, y) : c.moveTo(x, y); }
        c.stroke();
      }
      c.globalAlpha = 1;
    }
    if (hov) {
      const lo = d.min + hov.j * g.bw, wall = new Date(d.walls[hov.i] * 1000).toLocaleString();
      this.placeTip(`<div class="h">step ${d.steps[hov.i]} · ${wall}</div><div class="r"><b>[${fmt(lo)}, ${fmt(lo + g.bw)})</b>count ${fmt(d.counts[hov.i][hov.j])}</div>`);
    } else this.tip.style.display = 'none';
  }
  pick(off, g, N) {
    const m = this.mouse, d = this.d;
    if (m.x < g.L || m.x > g.L + g.pw || m.y < g.T || m.y > this.h - g.B) return null;
    const j = Math.min(d.bins - 1, Math.max(0, Math.floor((m.x - g.L) / g.pw * d.bins)));
    let i;
    if (off) i = this.sp ? Math.min(N - 1, Math.max(0, Math.ceil((m.y - g.T - this.hh) / this.sp))) : 0;
    else {
      const yv = (g.T + g.ph - m.y) / g.ph * g.maxc; let best = 1e300; i = 0;
      for (let k = 0; k < N; k++) { const df = Math.abs(d.counts[k][j] - yv); if (df < best) { best = df; i = k; } }
    }
    return { i, j };
  }
}

