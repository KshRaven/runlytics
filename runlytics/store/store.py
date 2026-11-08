"""Lazy, incremental, memory-bounded event store.

* ``scan()`` lists/stats event-file names only (cached per directory); nothing is parsed.
* A run is parsed when first requested, then tailed incrementally (byte offset per file).
* Parsed runs live in an LRU bounded by a memory budget; query results are cached per run generation.
"""
from __future__ import annotations

import gc
import os
import threading
import time
from collections import OrderedDict

from ..charting.histogram import rebin
from ..charting.line import scalar_payload
from ..utils.lru import LRUCache
from ..utils.naming import unique_name
from ..utils.numbers import sample_indices
from .blobs import read_blob, read_graph, read_json
from .run import RunData
from .scan import RunMeta, Scanner, stat_files

__all__ = ["Store"]


class Store:
    def __init__(self, specs, reload_interval=5.0, max_memory=1 << 30, purge=True, follow_links=True):
        self.specs = specs  # [(prefix_or_None, path)]
        self.interval, self.max_memory, self.purge = reload_interval, max_memory, purge
        self.meta: dict[str, RunMeta] = {}
        self._scanner = Scanner(follow_links)
        self._scan_lock = threading.Lock()
        self._last_scan = 0.0
        self._runs: OrderedDict[str, RunData] = OrderedDict()
        self._runs_lock = threading.Lock()
        self._cache = LRUCache(512)
        self._born: dict[str, float] = {}
        self.last_access = time.time()   # updated by the server on every API request

    # ---- idle handling (background-service friendly) ---------------------------------------
    def touch(self):
        self.last_access = time.time()

    def idle_for(self) -> float:
        return time.time() - self.last_access

    def release(self) -> None:
        """Drop every parsed run and cached result; names stay listed and runs re-parse lazily when needed."""
        with self._runs_lock:
            self._runs.clear()
        self._cache.clear()
        gc.collect()
        try:   # hand freed arenas back to the OS (glibc only)
            import ctypes
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except Exception:
            pass

    def keep(self, names) -> int:
        """Free every parsed run that is not in ``names`` (and all cached query results); returns how many remain."""
        names = set(names)
        with self._runs_lock:
            for n in [n for n in self._runs if n not in names]:
                del self._runs[n]
            left = len(self._runs)
        self._cache.clear()
        gc.collect()
        return left

    # ---- scanning (names + stat only) ----------------------------------------------------
    def scan(self, force=False):
        with self._scan_lock:
            if not force and self.meta and time.time() - self._last_scan < max(self.interval, 0.5):
                return self.meta
            meta: dict[str, RunMeta] = {}
            multi = len(self.specs) > 1
            for prefix, root in self.specs:
                root = os.path.abspath(root)
                pre = prefix or (os.path.basename(root.rstrip("/\\")) if multi else "")
                for d, files in self._scanner.walk(root).items():
                    rel = os.path.relpath(d, root).replace(os.sep, "/")
                    if rel == ".":
                        name = pre or "."
                    else:
                        name = pre + "/" + rel if pre else rel
                    name = unique_name(name, meta)
                    meta[name] = RunMeta(name, d, files)
            self.meta, self._last_scan = meta, time.time()
            return meta

    def runs_list(self, force=False):
        m = self.scan(force)
        return [dict(name=r.name, size=r.size, mtime=r.mtime, created=self._created(r), files=len(r.files), rev=r.rev)
                for r in sorted(m.values(), key=lambda r: r.name)]

    def _created(self, r) -> float:
        """Earliest file creation time of a run (stat'ed once per file, then cached)."""
        best = None
        for p, _, _ in r.files:
            t = self._born.get(p)
            if t is None:
                try:
                    st = os.stat(p)
                    t = getattr(st, "st_birthtime", None) or st.st_ctime
                except OSError:
                    continue
                self._born[p] = t
            best = t if best is None or t < best else best
        return best or r.mtime

    # ---- loading -------------------------------------------------------------------------
    def run(self, name):
        meta = self.meta.get(name) or self.scan().get(name)
        if meta is None:
            return None
        with self._runs_lock:
            rd = self._runs.get(name)
            if rd is None:
                rd = self._runs[name] = RunData(name, self.purge)
            self._runs.move_to_end(name)
        if time.time() - rd.last_check > 0.5:
            rd.refresh(stat_files(p for p, _, _ in meta.files))
        self._evict(name)
        return rd

    def run_dir(self, name):
        meta = self.meta.get(name) or self.scan().get(name)
        return meta.dir if meta else None

    def _evict(self, keep):
        with self._runs_lock:
            total = sum(r.loaded_bytes for r in self._runs.values())
            for n in list(self._runs):
                if total <= self.max_memory or len(self._runs) <= 1:
                    break
                if n != keep:
                    total -= self._runs.pop(n).loaded_bytes

    # ---- queries -------------------------------------------------------------------------
    def tags(self, names):
        sc, hi, ot, desc, layout = {}, {}, {}, {}, {}
        for n in names:
            rd = self.run(n)
            if rd is None:
                continue
            with rd.lock:
                for t in rd.scalars:
                    sc.setdefault(t, []).append(n)
                    self._desc(desc, "scalars", t, rd)
                for t in rd.hists:
                    hi.setdefault(t, []).append(n)
                    self._desc(desc, "histograms", t, rd)
                if rd.graph and self.graph(n):
                    ot.setdefault("graphs", {}).setdefault("Default graph", []).append(n)
                for kind, tags in rd.items.items():
                    for t, lst in tags.items():
                        if lst:
                            ot.setdefault(kind, {}).setdefault(t, []).append(n)
                            self._desc(desc, kind, t, rd)
                if "custom_scalars" in rd.items:
                    self._merge_layout(layout, rd)
        return dict(scalars=sc, histograms=hi, other=ot, desc=desc, layout=layout)

    def _merge_layout(self, layout, rd):
        def build():
            out = {}
            for tag, lst in rd.items["custom_scalars"].items():
                obj = read_json(tag, lst[-1]) if lst else None
                for cat, charts in (obj.items() if isinstance(obj, dict) else ()):
                    if isinstance(charts, dict):
                        out.setdefault(cat, {}).update(charts)
            return out
        for cat, charts in self._cache.get_or_compute(("layout", rd.name, rd.gen), build).items():
            layout.setdefault(cat, {}).update(charts)

    @staticmethod
    def _desc(desc, kind, tag, rd):
        d = rd.desc.get(tag)
        if d and tag not in desc.get(kind, {}):
            desc.setdefault(kind, {})[tag] = d

    def scalars(self, names, tag, max_points=1500, lo=None, hi=None):
        out = {}
        for n in names:
            rd = self.run(n)
            if rd is None or tag not in rd.scalars:
                continue
            key = ("s", n, tag, rd.gen, max_points, lo, hi)

            def build(rd=rd):
                with rd.lock:
                    return scalar_payload(rd.scalars[tag], max_points, lo, hi)
            out[n] = self._cache.get_or_compute(key, build)
        return out

    def histograms(self, name, tag, bins=30, max_steps=50):
        rd = self.run(name)
        if rd is None or tag not in rd.hists:
            return None
        return self._cache.get_or_compute(("h", name, tag, rd.gen, bins, max_steps),
                                          lambda: self._hist(rd, tag, bins, max_steps))

    def _hist(self, rd, tag, bins, max_steps):
        with rd.lock:
            lst = list(rd.hists[tag])
        n = len(lst)
        if n > max_steps > 1:
            idx = sorted({round(i * (n - 1) / (max_steps - 1)) for i in range(max_steps)})
            lst = [lst[i] for i in idx]
        lo, hi = min(h[2].min for h in lst), max(h[2].max for h in lst)
        if hi <= lo:
            lo, hi = lo - 0.5, hi + 0.5
        width = (hi - lo) / bins
        counts = [[round(c, 2) for c in rebin(h[2], lo, width, bins)] for h in lst]
        return dict(min=lo, max=hi, bins=bins, n=n, steps=[h[0] for h in lst],
                    walls=[round(h[1], 3) for h in lst], counts=counts)

    # ---- media ---------------------------------------------------------------------------
    def entries(self, name, kind, tag):
        """Snapshot of one tag's item list as ``(entries, generation)`` or ``None``."""
        rd = self.run(name)
        if rd is None:
            return None
        with rd.lock:
            lst = rd.items.get(kind, {}).get(tag)
            return (list(lst), rd.gen) if lst else None

    def blob(self, name, kind, tag, index):
        """``(mime, bytes)`` for entry ``index`` of an image/audio tag, read from disk on demand."""
        r = self.entries(name, kind, tag)
        if r is None or not 0 <= index < len(r[0]):
            return None
        return read_blob(kind, tag, r[0][index])

    # ---- structured kinds --------------------------------------------------------------------
    def data(self, name, kind, tag, index=None, cap=1000):
        """One step of a JSON-backed tag: ``dict(gen, n, rows=[[i, step, wall]], i, obj)`` or ``None``."""
        r = self.entries(name, kind, tag)
        if r is None:
            return None
        lst, gen = r
        i = len(lst) - 1 if index is None or not 0 <= index < len(lst) else index
        rows = [[j, lst[j][0], round(lst[j][1], 3)] for j in sample_indices(len(lst), cap)]
        obj = self._cache.get_or_compute(("d", name, kind, tag, gen, i), lambda: read_json(tag, lst[i]))
        return None if obj is None else dict(gen=gen, n=len(lst), rows=rows, i=i, obj=obj)

    def hparams(self, names):
        """Rows of ``{run, hparams, metrics}`` for every selected run that logged hyper-parameters."""
        rows, hn, mn = [], [], []
        for n in names:
            r = self.entries(n, "hparams", "Hyperparameters")
            rd = self.run(n)
            obj = read_json("Hyperparameters", r[0][-1]) if r else None
            if not isinstance(obj, dict) or not isinstance(obj.get("hparams"), dict) or rd is None:
                continue
            with rd.lock:
                metrics = {k: rd.scalars[k].v[-1] for k in obj.get("metrics", []) if k in rd.scalars and len(rd.scalars[k].v)}
            rows.append(dict(run=n, hparams=obj["hparams"], metrics=metrics))
            hn += [k for k in obj["hparams"] if k not in hn]
            mn += [k for k in metrics if k not in mn]
        return dict(rows=rows, hparams=hn, metrics=mn)

    def graph(self, name):
        rd = self.run(name)
        if rd is None or not rd.graph:
            return None
        return self._cache.get_or_compute(("g", name, rd.graph), lambda: read_graph(*rd.graph))
