"""Application state shared by all requests."""
from __future__ import annotations

import time

from .static import load_static

__all__ = ["App"]


class App:
    def __init__(self, store, prefix: str = "", title: str = "Runlytics", samples: dict | None = None, dev: bool = False):
        self.store, self.title = store, title
        self.prefix = "/" + prefix.strip("/") if prefix.strip("/") else ""
        self.samples = samples or {"scalars": 1500, "histograms": 50}
        self.dev, self._static = dev, load_static()
        self.boot = int(time.time() * 1000)   # changes on every fresh start; lets the browser tell a new instance from a long-running service

    @property
    def static(self):
        """Bundled web assets; in dev mode they are re-read from disk on every request (edit, then just refresh)."""
        return load_static() if self.dev else self._static
