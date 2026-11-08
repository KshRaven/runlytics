"""In-memory static assets (served gzip-compressed, with ETags)."""
from __future__ import annotations

import gzip
import hashlib
import mimetypes
import os

__all__ = ["WEB_DIR", "load_static"]

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")


def load_static() -> dict[str, tuple]:
    """Map ``relative/path`` -> ``(data, gzipped, content_type, etag)`` for every file under ``web/``."""
    out = {}
    for base, _dirs, names in os.walk(WEB_DIR):
        for n in names:
            p = os.path.join(base, n)
            with open(p, "rb") as f:
                data = f.read()
            ct = mimetypes.guess_type(n)[0] or "application/octet-stream"
            if ct.startswith("text/") or ct.endswith("javascript") or ct.endswith("json"):
                ct += "; charset=utf-8"
            rel = os.path.relpath(p, WEB_DIR).replace(os.sep, "/")
            out[rel] = (data, gzip.compress(data, 6), ct, '"%s"' % hashlib.md5(data).hexdigest()[:16])
    return out
