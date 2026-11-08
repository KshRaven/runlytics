"""Route registry and query-string helpers."""
from __future__ import annotations

from typing import Callable
from urllib.parse import parse_qs

__all__ = ["ROUTES", "route", "Query"]

ROUTES: dict[str, Callable] = {}


def route(path: str):
    """Register ``fn(app, query) -> JSON | Raw`` for ``path``."""
    def deco(fn):
        ROUTES[path] = fn
        return fn
    return deco


class Query:
    def __init__(self, qs: str):
        self.q = parse_qs(qs)

    def __contains__(self, k):
        return k in self.q

    def str(self, k: str, default: str = "") -> str:
        return self.q.get(k, [default])[0]

    def list(self, k: str) -> list[str]:
        return self.q.get(k, [])

    def int(self, k: str, default: int, lo: int = 1, hi: int = 100000) -> int:
        try:
            return min(max(int(self.q.get(k, [default])[0]), lo), hi)
        except (ValueError, TypeError):
            return default

    def opt_int(self, k: str):
        try:
            return int(self.q[k][0]) if k in self.q else None
        except ValueError:
            return None
