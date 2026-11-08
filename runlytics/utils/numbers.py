"""Small numeric helpers shared by the store and server."""
from __future__ import annotations

import math

__all__ = ["g7", "finite", "clamp", "sample_indices"]


def g7(v: float) -> float:
    """Round to 7 significant digits (keeps JSON payloads compact)."""
    return float("%.7g" % v)


def finite(v: float) -> bool:
    return math.isfinite(v)


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def sample_indices(n: int, cap: int) -> list[int]:
    """At most ``cap`` evenly spaced indices of ``range(n)``; the last index is always included."""
    if n <= cap:
        return list(range(n))
    return sorted({round(i * (n - 1) / (cap - 1)) for i in range(cap)})
