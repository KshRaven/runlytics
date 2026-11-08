'use strict';
/* DOM-based views (images, audio, text). They share the chart interface: load(), schedule(), destroy(), msg(). */

// Small block-level markdown: headings, lists, tables, fenced code, paragraphs.
function mdBlock(src) {
  const lines = String(src).split('\n'), out = [];
  let i = 0;
  while (i < lines.length) {
    const ln = lines[i];
    if (/^```/.test(ln)) {
      const buf = []; i++;
      while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
      i++; out.push(`<pre>${esc(buf.join('\n'))}</pre>`); continue;
    }
    let m = /^(#{1,6})\s+(.*)$/.exec(ln);
    if (m) { out.push(`<h${m[1].length + 2}>${mdLite(m[2])}</h${m[1].length + 2}>`); i++; continue; }
    if (/^\s*\|.*\|\s*$/.test(ln) && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1] || '')) {
      const cells = l => l.trim().replace(/^\||\|$/g, '').split('|').map(c => mdLite(c.trim()));
      let h = '<table><thead><tr>' + cells(ln).map(c => `<th>${c}</th>`).join('') + '</tr></thead><tbody>';
      i += 2;
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) h += '<tr>' + cells(lines[i++]).map(c => `<td>${c}</td>`).join('') + '</tr>';
      out.push(h + '</tbody></table>'); continue;
    }
    if (/^\s*([-*]|\d+\.)\s+/.test(ln)) {
      const ord = /^\s*\d+\./.test(ln); let h = ord ? '<ol>' : '<ul>';
      while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) h += `<li>${mdLite(lines[i++].replace(/^\s*([-*]|\d+\.)\s+/, ''))}</li>`;
      out.push(h + (ord ? '</ol>' : '</ul>')); continue;
    }
    if (!ln.trim()) { i++; continue; }
    const buf = [];
    while (i < lines.length && lines[i].trim() && !/^(```|#{1,6}\s|\s*([-*]|\d+\.)\s)/.test(lines[i])) buf.push(lines[i++]);
    out.push(`<p>${mdLite(buf.join('\n'))}</p>`);
  }
  return out.join('');
}

class MediaView {
  constructor(card, tag, run, kind) {
    this.card = card; this.tag = tag; this.run = run; this.kind = kind;
    this.rows = []; this.idx = -1; this.follow = true; this.gen = 0;
    this.body = $('.cbody', card); this.msgEl = $('.cmsg', card);
    this.box = el('div', 'media'); this.body.append(this.box);
  }
  msg(t) { this.msgEl.textContent = t || ''; }
  schedule() { }
  destroy() { }
  async load() {
    try {
      const d = await api('api/media', { run: this.run, tag: this.tag, kind: this.kind });
      this.rows = d.rows; this.gen = d.gen; this.msg(this.rows.length ? '' : 'No data');
      if (this.follow || this.idx >= this.rows.length) this.idx = this.rows.length - 1;
      this.build();
    } catch (e) { this.msg('Error: ' + e.message); }
  }
  url(row) { return 'api/blob?' + new URLSearchParams({ run: this.run, tag: this.tag, kind: this.kind, i: row.i, g: this.gen }); }
  extras() { return []; }
  build() {
    this.box.replaceChildren(); if (!this.rows.length) return;
    this.view = el('div', 'mview'); this.info = el('div', 'minfo');
    const sl = el('input'); sl.type = 'range'; sl.min = 0; sl.max = this.rows.length - 1; sl.value = this.idx;
    sl.title = 'Step'; sl.oninput = () => { this.idx = +sl.value; this.follow = this.idx === this.rows.length - 1; this.show(); };
    this.box.append(this.view, this.info, sl, ...this.extras()); this.show();
  }
  stamp(r) { return `step ${r.step} · ${new Date(r.wall * 1000).toLocaleString()}`; }
  show() { }
}

class ImageView extends MediaView {
  constructor(card, tag, run) { super(card, tag, run, 'images'); this.bright = 1; this.contrast = 1; }
  extras() {
    const mk = (label, key) => {
      const l = el('label', 'mrow', `<span>${label}</span>`), r = el('input'); r.type = 'range'; r.min = 0.2; r.max = 3; r.step = 0.05; r.value = this[key];
      r.oninput = () => { this[key] = +r.value; this.filter(); }; l.append(r); return l;
    };
    return [mk('Brightness', 'bright'), mk('Contrast', 'contrast')];
  }
  filter() { const i = $('img', this.view); if (i) i.style.filter = `brightness(${this.bright}) contrast(${this.contrast})`; }
  show() {
    const r = this.rows[this.idx]; this.info.textContent = `${this.stamp(r)} · ${r.w}×${r.h}`;
    let img = $('img', this.view); if (!img) { img = el('img'); img.alt = this.tag; this.view.append(img); }
    img.src = this.url(r); this.filter();
  }
}

class AudioView extends MediaView {
  constructor(card, tag, run) { super(card, tag, run, 'audio'); }
  show() {
    const r = this.rows[this.idx]; this.info.textContent = `${this.stamp(r)} · ${r.rate} Hz · ${r.ch} ch · ${(r.frames / r.rate).toFixed(2)} s`;
    const a = el('audio'); a.controls = true; a.preload = 'none'; a.src = this.url(r); this.view.replaceChildren(a);
  }
}

class TextView extends MediaView {
  constructor(card, tag, run) { super(card, tag, run, 'text'); }
  show() { const r = this.rows[this.idx]; this.info.textContent = this.stamp(r); this.view.innerHTML = mdBlock(r.text); }
}
