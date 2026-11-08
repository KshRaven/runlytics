"""Name helpers for runs and tags."""
from __future__ import annotations

import re

__all__ = ["safe_filename", "unique_name"]

_BAD = re.compile(r"[^\w.\-]+")


def safe_filename(name: str) -> str:
    return _BAD.sub("_", name).strip("_") or "unnamed"


def unique_name(base: str, taken) -> str:
    name, k = base, 2
    while name in taken:
        name, k = "%s_%d" % (base, k), k + 1
    return name
