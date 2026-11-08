"""Line-chart data: LTTB downsampling and scalar window payloads."""
from __future__ import annotations

import math
from bisect import bisect_left, bisect_right

from ..utils.arrays import np
from ..utils.numbers import g7

__all__ = ["lttb", "scalar_payload"]


def _lttb_py(x, y, n):
    m = len(x)
    idx, a, every = [0], 0, (m - 2) / (n - 2)
    for i in range(n - 2):
        s, e = int((i + 1) * every) + 1, min(int((i + 2) * every) + 1, m)
        if e <= s:
            s, e = m - 1, m
        ax, ay = sum(x[s:e]) / (e - s), sum(y[s:e]) / (e - s)
        rs, re_ = int(i * every) + 1, int((i + 1) * every) + 1
        px, py = x[a], y[a]
        best, bi = -1.0, rs
        for j in range(rs, re_):
            area = abs((px - ax) * (y[j] - py) - (px - x[j]) * (ay - py))
            if area > best:
                best, bi = area, j
        idx.append(bi)
        a = bi
    idx.append(m - 1)
    return idx


def _lttb_np(x, y, n):
    m = len(x)
    xs, ys = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
    idx, a, every = [0], 0, (m - 2) / (n - 2)
    for i in range(n - 2):
        s, e = int((i + 1) * every) + 1, min(int((i + 2) * every) + 1, m)
        if e <= s:
            s, e = m - 1, m
        ax, ay = xs[s:e].mean(), ys[s:e].mean()
        rs, re_ = int(i * every) + 1, int((i + 1) * every) + 1
        px, py = xs[a], ys[a]
        area = np.abs((px - ax) * (ys[rs:re_] - py) - (px - xs[rs:re_]) * (ay - py))
        a = rs + int(area.argmax())
        idx.append(a)
    idx.append(m - 1)
    return idx


def lttb(x, y, n: int) -> list[int]:
    """Largest-Triangle-Three-Buckets: indices of ``n`` points that best preserve the line's shape."""
    m = len(x)
    if n >= m or n < 3:
        return list(range(m))
    return _lttb_np(x, y, n) if np is not None and m > 2000 else _lttb_py(x, y, n)


def scalar_payload(ser, max_points: int, lo=None, hi=None) -> dict:
    """Window (``lo``/``hi`` steps), drop non-finite values, downsample. ``ser`` is a ``store.Series``."""
    total, t0 = len(ser.s), ser.w[0]
    if lo is None and hi is None:
        s, w, v = list(ser.s), list(ser.w), list(ser.v)
    elif ser.sorted:
        a = max(0, (bisect_left(ser.s, lo) if lo is not None else 0) - 1)
        b = min(total, (bisect_right(ser.s, hi) if hi is not None else total) + 1)
        s, w, v = list(ser.s[a:b]), list(ser.w[a:b]), list(ser.v[a:b])
    else:
        ix = [i for i in range(total) if (lo is None or ser.s[i] >= lo) and (hi is None or ser.s[i] <= hi)]
        s, w, v = [ser.s[i] for i in ix], [ser.w[i] for i in ix], [ser.v[i] for i in ix]
    nan = 0
    if not all(map(math.isfinite, v)):
        keep = [i for i, x in enumerate(v) if math.isfinite(x)]
        nan = len(v) - len(keep)
        s, w, v = [s[i] for i in keep], [w[i] for i in keep], [v[i] for i in keep]
    if len(s) > max_points:
        ix = lttb(s, v, max_points)
        s, w, v = [s[i] for i in ix], [w[i] for i in ix], [v[i] for i in ix]
    return dict(s=s, w=[round(x, 3) for x in w], v=[g7(x) for x in v], n=total, t0=round(t0, 3), nan=nan)
