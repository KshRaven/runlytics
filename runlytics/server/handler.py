"""HTTP request handling: gzip, ETag/304, keep-alive, prefix mounting."""
from __future__ import annotations

import gzip
import hashlib
import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

from .. import __version__
from .responses import JSON, Raw
from .routes import ROUTES, Query

__all__ = ["make_handler"]


def _etag(body: bytes) -> str:
    return '"%s"' % hashlib.md5(body).hexdigest()[:16]


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "Runlytics/" + __version__

        def log_message(self, fmt, *a):
            if app.dev:
                import sys
                print("[dev] " + fmt % a, file=sys.stderr)

        def _send(self, r: Raw):
            if r.etag and self.headers.get("If-None-Match") == r.etag:
                self.send_response(304)
                self.send_header("ETag", r.etag)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body, gz = r.body, r.gz
            enc = "gzip" in self.headers.get("Accept-Encoding", "")
            if gz is None and enc and len(body) > 1024 and r.content_type.split(";")[0] in _COMPRESSIBLE:
                gz = gzip.compress(body, 4)
            self.send_response(r.status)
            self.send_header("Content-Type", r.content_type)
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Vary", "Accept-Encoding")
            if r.etag:
                self.send_header("ETag", r.etag)
            if gz is not None and enc:
                body = gz
                self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, status=200):
            body = json.dumps(obj, separators=(",", ":")).encode()
            self._send(Raw(body, "application/json", _etag(body), status=status))

        def do_GET(self):
            try:
                self._route()
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as e:  # keep the server alive, report to client
                try:
                    self._json({"error": str(e)}, 500)
                except Exception:
                    pass

        def _route(self):
            u = urlparse(self.path)
            path = u.path
            if app.prefix:
                if path == app.prefix:
                    self.send_response(301)
                    self.send_header("Location", app.prefix + "/")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if not path.startswith(app.prefix + "/"):
                    return self._json({"error": "not found"}, 404)
                path = path[len(app.prefix):]
            if path in ("/", "/index.html") or path.strip("/") in TAB_PATHS:
                app.store.touch()
                d = app.static["index.html"]
                body = d[0].replace(b"__TITLE__", app.title.encode()).replace(b"__BOOT__", str(app.boot).encode())
                return self._send(Raw(body, d[2], _etag(body)))
            if path.startswith("/static/"):
                d = app.static.get(path[8:])
                if not d:
                    return self._json({"error": "not found"}, 404)
                return self._send(Raw(d[0], d[2], d[3], gz=d[1]))
            app.store.touch()
            fn = ROUTES.get(path)
            if fn is None:
                return self._json({"error": "not found"}, 404)
            res = fn(app, Query(u.query))
            if isinstance(res, JSON):
                return self._json(res.obj, res.status)
            self._send(res)

    return Handler


TAB_PATHS = {"scalars", "timeseries", "histograms", "images", "graphs", "text", "audio", "projector", "pr_curves", "hparams", "custom_scalars", "mesh"}
_COMPRESSIBLE = {"application/json", "text/html", "text/css", "text/plain", "application/javascript"}
