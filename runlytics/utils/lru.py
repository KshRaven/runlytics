"""Thread-safe LRU cache with compute-on-miss."""
from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any, Callable, Hashable

__all__ = ["LRUCache"]


class LRUCache:
    def __init__(self, maxsize: int = 512):
        self.maxsize = maxsize
        self._d: OrderedDict[Hashable, Any] = OrderedDict()
        self._lock = threading.Lock()

    def get_or_compute(self, key: Hashable, fn: Callable[[], Any]) -> Any:
        with self._lock:
            if key in self._d:
                self._d.move_to_end(key)
                return self._d[key]
        val = fn()
        with self._lock:
            self._d[key] = val
            while len(self._d) > self.maxsize:
                self._d.popitem(last=False)
        return val

    def clear(self) -> None:
        with self._lock:
            self._d.clear()

    def __len__(self) -> int:
        return len(self._d)
