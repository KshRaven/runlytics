"""``runlytics`` entry point."""
from __future__ import annotations

import os
import sys
import threading
import webbrowser

from .._version import __version__
from ..server import App, serve, start_scanner
from ..store import Store
from .args import build_parser, parse_samples, parse_specs, resolve_path

__all__ = ["main"]


def main(argv=None) -> None:
    p = build_parser()
    a = p.parse_args(argv)
    if a.logdir is None and not a.logdir_spec:
        a.logdir = ""   # no logdir given: use the directory runlytics was started in
    specs = parse_specs(a.logdir, a.logdir_spec)
    if a.logdir == "":
        specs.insert(0, (None, resolve_path("")))
    for _, d in specs:
        if not os.path.isdir(d):
            print("warning: %s is not a directory (yet)" % d, file=sys.stderr)
    store = Store(specs, a.reload_interval, a.max_memory_mb << 20, a.purge_orphaned_data)
    n = len(store.scan(force=True))
    start_scanner(store, a.idle_scan_secs, a.idle_release_secs)
    host = a.host or ("0.0.0.0" if a.bind_all else "127.0.0.1")
    app = App(store, a.path_prefix, a.window_title, parse_samples(a.samples_per_plugin), dev=a.dev)
    srv, port = serve(app, host, a.port)
    url = "http://%s:%d%s/" % ("localhost" if host in ("127.0.0.1", "0.0.0.0") else host, port, app.prefix)
    if a.dev:
        print("dev mode: web assets reload from disk on every request, requests are logged", file=sys.stderr)
    print("Log directory: %s" % ", ".join(d for _, d in specs))
    if port != a.port:
        print("Port %d is already in use; using %d instead (pass --port to choose another)." % (a.port, port))
    print("Runlytics %s: %d run(s) found, serving at %s (Ctrl+C to quit)" % (__version__, n, url))
    if a.open:
        threading.Timer(0.5, webbrowser.open, (url,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
