"""Histogram data: construction (writer side) and re-binning / percentile bands (reader side)."""
from __future__ import annotations

import math
from bisect import bisect_left

from ..core import Histo, Tensor
from ..utils.arrays import np

__all__ = ["make_histogram", "rebin", "tensor_to_histo", "percentiles", "BASIS_POINTS"]

_EDGES = None
BASIS_POINTS = (0, 668, 1587, 3085, 5000, 6915, 8413, 9332, 10000)


def _default_edges():
    global _EDGES
    if _EDGES is None:
        pos, v = [], 1e-12
        while v < 1e20:
            pos.append(v)
            v *= 1.1
        pos.append(1.7976931348623157e308)
        _EDGES = [-x for x in reversed(pos)] + [0.0] + pos
    return _EDGES


def _flatten(values):
    if hasattr(values, "detach"):
        values = values.detach().cpu().numpy()
    if np is not None:
        a = np.asarray(values, dtype=np.float64).ravel()
        return a[np.isfinite(a)]
    out = []

    def rec(x):
        if isinstance(x, (list, tuple)):
            for y in x:
                rec(y)
        elif hasattr(x, "tolist") and not isinstance(x, (int, float)):
            rec(x.tolist())
        else:
            f = float(x)
            if math.isfinite(f):
                out.append(f)
    rec(values)
    return out


def _trim(edges, counts):
    nz = [i for i, c in enumerate(counts) if c]
    if not nz:
        return [edges[0], edges[1]], [0.0]
    a, b = max(nz[0] - 1, 0), min(nz[-1] + 1, len(counts) - 1)
    return list(edges[a:b + 2]), list(counts[a:b + 1])


def _merge(limits, counts, max_bins):
    if not max_bins or len(counts) <= max_bins:
        return limits, counts
    g = math.ceil(len(counts) / max_bins)
    return ([limits[min(i + g - 1, len(limits) - 1)] for i in range(0, len(limits), g)],
            [sum(counts[i:i + g]) for i in range(0, len(counts), g)])


def make_histogram(values, bins="default", max_bins=None) -> dict:
    """Return ``dict(min, max, num, sum, sum_squares, limits, counts)``; raises ``ValueError`` when empty."""
    v = _flatten(values)
    n = len(v)
    if n == 0:
        raise ValueError("histogram values are empty (or all non-finite)")
    if np is not None:
        mn, mx = float(v.min()), float(v.max())
        s, ss = float(v.sum()), float((v * v).sum())
        if isinstance(bins, str) and bins == "default":
            e = np.asarray(_default_edges())
        elif isinstance(bins, (str, int)):
            e = np.histogram_bin_edges(v, bins=bins)
        else:
            e = np.asarray(bins, dtype=np.float64)
        counts, e = np.histogram(v, bins=e)
        edges, counts = e.tolist(), counts.astype(float).tolist()
    else:
        mn, mx, s = min(v), max(v), sum(v)
        ss = sum(x * x for x in v)
        if isinstance(bins, str) and bins == "default":
            edges = _default_edges()
        elif isinstance(bins, (list, tuple)):
            edges = list(bins)
        else:
            k = bins if isinstance(bins, int) else max(1, math.ceil(math.log2(n)) + 1)
            w = (mx - mn) / k or 1.0
            edges = [mn + i * w for i in range(k + 1)]
        counts = [0.0] * (len(edges) - 1)
        for x in v:
            i = 0 if x == edges[0] else min(max(bisect_left(edges, x) - 1, 0), len(counts) - 1)
            counts[i] += 1
    edges, counts = _trim(edges, counts)
    limits, counts = _merge(edges[1:], counts, max_bins)
    return dict(min=mn, max=mx, num=float(n), sum=s, sum_squares=ss, limits=limits, counts=counts)


# ------------------------------------------------------------------ reader side
def tensor_to_histo(t: Tensor | None) -> Histo | None:
    """Convert an ``[N, 3]`` (left, right, count) histogram tensor to a :class:`Histo`."""
    if t is None or len(t.shape) != 2 or t.shape[1] != 3 or len(t.values) < 3:
        return None
    vals = t.values
    h = Histo()
    rows = len(vals) // 3
    for i in range(rows):
        h.limits.append(float(vals[3 * i + 1]))
        h.counts.append(float(vals[3 * i + 2]))
    h.min, h.max = float(vals[0]), float(vals[3 * (rows - 1) + 1])
    h.num = sum(h.counts)
    return h


def rebin(h: Histo, lo: float, width: float, bins: int) -> list[float]:
    """Redistribute ``h`` into ``bins`` uniform bins starting at ``lo`` (mass is spread proportionally)."""
    out = [0.0] * bins
    left = h.min
    for lim, c in zip(h.limits, h.counts):
        right = min(lim, h.max)
        lft = max(left, h.min)
        left = lim
        if not c:
            continue
        ja = min(max(int((lft - lo) / width), 0), bins - 1)
        if right <= lft:
            out[ja] += c
            continue
        jb = min(max(int((right - lo) / width), 0), bins - 1)
        if ja == jb:
            out[ja] += c
            continue
        d = c / (right - lft)
        out[ja] += d * (lo + (ja + 1) * width - lft)
        for j in range(ja + 1, jb):
            out[j] += d * width
        out[jb] += d * (right - (lo + jb * width))
    return out


def percentiles(h: Histo, bps=BASIS_POINTS) -> list[float]:
    """Values at the given basis points (0..10000) of the distribution described by ``h``."""
    total = sum(h.counts)
    if total <= 0 or not h.counts:
        return [h.min] * len(bps)
    spans, left = [], h.min
    for lim, c in zip(h.limits, h.counts):
        right = max(min(lim, h.max), left)
        spans.append((left, right, c))
        left = right
    out = []
    for bp in bps:
        target, cum, val = total * bp / 10000.0, 0.0, h.max
        for lft, right, c in spans:
            if c and cum + c >= target:
                val = lft + ((target - cum) / c) * (right - lft)
                break
            cum += c
        out.append(val)
    return out
