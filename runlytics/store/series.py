"""Compact columnar storage for one scalar series."""
from __future__ import annotations

from array import array

__all__ = ["Series"]


class Series:
    __slots__ = ("s", "w", "v", "sorted")

    def __init__(self):
        self.s, self.w, self.v, self.sorted = array("q"), array("d"), array("d"), True
