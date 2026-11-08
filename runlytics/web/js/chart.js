'use strict';
/* Chart base class: canvas, resize, tooltip, PNG export. */

class Chart {
  constructor(card) {
    this.card = card; this.body = $('.cbody', card);
    this.cv = el('canvas'); this.msgEl = $('.cmsg', card);
    this.tip = el('div', 'tip'); this.body.append(this.cv); document.body.append(this.tip);   // tooltip lives on <body>: never clipped by the card, floats above everything
    this.ctx = this.cv.getContext('2d'); this.w = 0; this.h = 0; this.mouse = null;
    this.ro = new ResizeObserver(() => this.resize()); this.ro.observe(this.body);
    this.cv.addEventListener('mousemove', e => { const r = this.cv.getBoundingClientRect(); this.mouse = { x: e.clientX - r.left, y: e.clientY - r.top }; if (!this.drag) this.schedule(); else this.onDrag(); });
    this.cv.addEventListener('mouseleave', () => { this.mouse = null; this.tip.style.display = 'none'; this.schedule(); });
  }
  msg(t) { this.msgEl.textContent = t || ''; }
  resize() {
    const r = this.body.getBoundingClientRect(), d = window.devicePixelRatio || 1;
    this.w = Math.max(10, r.width); this.h = Math.max(10, r.height);
    this.cv.width = Math.round(this.w * d); this.cv.height = Math.round(this.h * d);
    this.cv.style.width = this.w + 'px'; this.cv.style.height = this.h + 'px';
    this.ctx.setTransform(d, 0, 0, d, 0, 0); this.schedule();
  }
  schedule() { if (this._raf) return; this._raf = requestAnimationFrame(() => { this._raf = 0; if (this.w) this.draw(); }); }
  placeTip(html) {
    const t = this.tip; t.innerHTML = html; t.style.display = 'block';
    const r = this.cv.getBoundingClientRect(), m = this.mouse, tw = t.offsetWidth, th_ = t.offsetHeight, vw = innerWidth, vh = innerHeight;
    const cx = r.left + m.x, cy = r.top + m.y;
    let x = cx + 16 + tw > vw - 4 ? cx - tw - 16 : cx + 16, y = cy - th_ / 2;
    t.style.left = Math.max(4, Math.min(vw - tw - 4, x)) + 'px';
    t.style.top = Math.max(4, Math.min(vh - th_ - 4, y)) + 'px';
  }
  destroy() { this.tip.remove(); this.ro.disconnect(); if (this._raf) cancelAnimationFrame(this._raf); }
  png(name) { this.cv.toBlob(b => b && download(name + '.png', b)); }
}

