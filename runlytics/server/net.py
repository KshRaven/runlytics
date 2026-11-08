"""Threaded HTTP server and the background directory scanner."""
from __future__ import annotations

import os
import socket
import sys
import threading
from http.server import ThreadingHTTPServer

from .handler import make_handler

__all__ = ["Server", "serve", "start_scanner"]


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 128
    # On Windows SO_REUSEADDR lets a second process bind a port that is already being listened on (silently stealing
    # or sharing it), so it is only enabled on POSIX; Windows gets SO_EXCLUSIVEADDRUSE instead.
    allow_reuse_address = os.name != "nt"

    def server_bind(self):
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def handle_error(self, request, client_address):
        """Browsers routinely drop keep-alive sockets (reload, tab close); that is not an error worth printing."""
        if isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):
            return
        super().handle_error(request, client_address)


def port_in_use(host: str, port: int) -> bool:
    """True when something already accepts connections on ``port`` (checked on loopback and on ``host``)."""
    for h in {"127.0.0.1", host if host not in ("0.0.0.0", "", "::") else "127.0.0.1"}:
        try:
            with socket.create_connection((h, port), timeout=0.3):
                return True
        except OSError:
            continue
    return False


def serve(app, host: str, port: int, tries: int = 20):
    """Bind to the first free port in ``[port, port + tries)``. Returns ``(server, port)``."""
    for p in range(port, port + tries):
        if port_in_use(host, p):
            continue
        try:
            return Server((host, p), make_handler(app)), p
        except OSError:
            continue
    raise OSError("no free port in %d-%d" % (port, port + tries - 1))


def start_scanner(store, idle_scan: float = 60.0, idle_release: float = 300.0) -> threading.Event:
    """Periodic rescan while someone is looking; fully quiet otherwise.

    * No request for ``idle_scan`` seconds: no more directory scanning (nothing touches the disk).
    * No request for ``idle_release`` seconds: parsed runs and caches are freed once.
    The next request resumes everything transparently (and rescans immediately).
    """
    stop = threading.Event()
    if store.interval > 0:
        def loop():
            released = False
            while not stop.wait(store.interval):
                idle = store.idle_for()
                try:
                    if idle > idle_release and not released:
                        store.release()
                        released = True
                    if idle <= idle_scan:
                        released = False
                        store.scan(force=True)
                except Exception:
                    pass
        threading.Thread(target=loop, daemon=True, name="runlytics-scan").start()
    return stop
