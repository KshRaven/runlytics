"""One run's parsed data: incremental, tail-following ingestion of its event files."""
from __future__ import annotations

import threading
import time
from bisect import bisect_left

from ..charting.histogram import tensor_to_histo
from ..core import DT_STRING, CorruptRecord, decode_event, decode_tensor, parse_records
from .series import Series

__all__ = ["RunData"]


def _json_handler(kind: str):
    """Keep only entries whose payload is really ours (a JSON string tensor); others are skipped, never fatal.
    Precision/recall curves written as a plain ``[6, N]`` float tensor by other tools are accepted too."""
    def handler(self, tag, ev, payload, path, off, meta):
        t = decode_tensor(payload)
        if t is None or not len(t.values):
            return
        if t.dtype == DT_STRING:
            first = bytes(t.values[0][:1])
            if first in (b"{", b"["):
                self._append(kind, tag, (ev.step, ev.wall, path, off))
        elif kind == "pr_curves" and len(t.shape) == 2 and t.shape[0] == 6:
            self._append(kind, tag, (ev.step, ev.wall, path, off, "raw"))
    return handler

CHUNK = 32 << 20


class RunData:
    def __init__(self, name: str, purge: bool = True):
        self.name, self.purge = name, purge
        self.lock = threading.RLock()
        self._clear()
        self.last_check = 0.0

    def _clear(self):
        self.scalars: dict[str, Series] = {}
        self.hists: dict[str, list] = {}
        self.items: dict[str, dict[str, list]] = {}   # other kinds: kind -> tag -> [entries]
        self.plugin: dict[str, str] = {}               # tag -> plugin name
        self.desc: dict[str, str] = {}                 # tag -> description (chart hint)
        self.offsets: dict[str, int] = {}
        self.graph = None
        self.gen, self.loaded_bytes, self.bad, self.skipped = 0, 0, set(), 0

    # ---- ingest ----------------------------------------------------------------------------
    def refresh(self, files) -> bool:
        with self.lock:
            if any(size < self.offsets.get(p, 0) for p, size, _ in files):
                self._clear()
            changed = False
            for p, size, _ in files:
                off = self.offsets.get(p, 0)
                if size <= off or p in self.bad:
                    continue
                try:
                    new = self._read(p, off, size)
                except OSError:
                    continue
                except CorruptRecord:
                    self.bad.add(p)
                    continue
                if new != off:
                    self.offsets[p] = new
                    self.loaded_bytes += new - off
                    changed = True
            if changed:
                self.gen += 1
            self.last_check = time.time()
            return changed

    def _read(self, path: str, off: int, size: int) -> int:
        limit = CHUNK
        with open(path, "rb") as f:
            while off < size:
                f.seek(off)
                buf = f.read(min(size - off, limit))
                spans, used = parse_records(buf)
                mv = memoryview(buf)
                for a, b in spans:
                    self._ingest(mv[a:b], path, off + a - 12)
                off += used
                if used == 0:
                    if len(buf) >= limit:
                        limit *= 2  # record bigger than chunk
                        continue
                    break  # partial tail record: wait for more bytes
        return off

    def _ingest(self, data, path: str, frame_off: int) -> None:
        try:
            self._ingest_event(data, path, frame_off)
        except Exception:   # one unreadable or foreign record must never take the run (or the UI) down
            self.skipped += 1

    def _ingest_event(self, data, path: str, frame_off: int) -> None:
        ev = decode_event(data)
        if ev.graph is not None:
            self.graph = (path, frame_off)
        if ev.session == 1 and self.purge:
            self._purge_all(ev.step)
        for v in ev.values:
            meta = v.meta
            if meta:
                if meta.plugin:
                    self.plugin[v.tag] = meta.plugin
                if meta.description:
                    self.desc[v.tag] = meta.description
            kind, payload = v.kind, v.payload
            if kind == "tensor":
                kind, payload = self._tensor_kind(v.tag, payload)
            elif kind is None:
                kind, payload = self.plugin.get(v.tag), meta
            if not kind:
                continue
            handler = getattr(self, "_on_" + kind, None)
            if handler is not None:
                handler(v.tag, ev, payload, path, frame_off, meta)

    def _tensor_kind(self, tag: str, payload):
        pl = self.plugin.get(tag) or "tensors"
        if pl == "scalars":
            t = decode_tensor(payload)
            return ("scalars", float(t.values[0])) if t is not None and len(t.values) else (None, None)
        if pl == "histograms":
            h = tensor_to_histo(decode_tensor(payload))
            return ("histograms", h) if h else (None, None)
        return pl, payload

    def _purge_all(self, step: int) -> None:
        for ser in self.scalars.values():
            k = bisect_left(ser.s, step) if ser.sorted else len(ser.s)
            del ser.s[k:], ser.w[k:], ser.v[k:]
        for tag, lst in self.hists.items():
            self.hists[tag] = [h for h in lst if h[0] < step]
        for tags in self.items.values():
            for tag, lst in tags.items():
                tags[tag] = [e for e in lst if e[0] < step]

    def _append(self, kind: str, tag: str, entry: tuple) -> None:
        """Append ``entry`` (step first) to an item list, replacing any entries at or after its step."""
        self._extend(kind, tag, [entry])

    def _extend(self, kind: str, tag: str, entries: list) -> None:
        lst = self.items.setdefault(kind, {}).setdefault(tag, [])
        if self.purge:
            while lst and lst[-1][0] >= entries[0][0]:
                lst.pop()
        lst.extend(entries)

    # ---- handlers: one per summary kind, looked up as ``_on_<kind>`` ------------------------
    def _on_scalars(self, tag, ev, payload, *_):
        ser = self.scalars.get(tag)
        if ser is None:
            ser = self.scalars[tag] = Series()
        if ser.s and ev.step < ser.s[-1]:
            if self.purge:
                k = bisect_left(ser.s, ev.step)
                del ser.s[k:], ser.w[k:], ser.v[k:]
            else:
                ser.sorted = False
        ser.s.append(ev.step)
        ser.w.append(ev.wall)
        ser.v.append(payload)

    def _on_histograms(self, tag, ev, payload, *_):
        lst = self.hists.setdefault(tag, [])
        if self.purge:
            while lst and lst[-1][0] >= ev.step:
                lst.pop()
        lst.append((ev.step, ev.wall, payload))

    # Media entries keep only file offsets (``(step, wall, path, frame_offset, ...)``): bytes are read on demand.
    def _on_images(self, tag, ev, payload, path, off, meta):
        if isinstance(payload, tuple):  # classic image summary: (height, width, channels)
            self._append("images", tag, (ev.step, ev.wall, path, off, payload[0], payload[1], -1))
            return
        t = decode_tensor(payload)      # tensor form: [width, height, encoded_0, encoded_1, ...]
        if t is not None and len(t.values) >= 3:
            w, h = int(t.values[0]), int(t.values[1])
            self._extend("images", tag, [(ev.step, ev.wall, path, off, h, w, i) for i in range(len(t.values) - 2)])

    def _on_audio(self, tag, ev, payload, path, off, meta):
        if isinstance(payload, tuple):  # (sample_rate, channels, frames)
            self._append("audio", tag, (ev.step, ev.wall, path, off, payload[0], payload[1], payload[2]))

    def _on_text(self, tag, ev, payload, path, off, meta):
        t = decode_tensor(payload)
        if t is not None and t.values:
            text = "\n".join(bytes(b).decode("utf-8", "replace") for b in t.values)
            self._append("text", tag, (ev.step, ev.wall, text[:200_000]))

    # Structured kinds (JSON string tensors) keep only file offsets too: ``(step, wall, path, frame_offset)``.
    _on_pr_curves = _json_handler("pr_curves")
    _on_hparams = _json_handler("hparams")
    _on_custom_scalars = _json_handler("custom_scalars")
    _on_projector = _json_handler("projector")
    _on_mesh = _json_handler("mesh")
