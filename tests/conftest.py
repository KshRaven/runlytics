"""Shared fixtures: a populated log directory and a running dashboard server."""
from __future__ import annotations

import json
import math
import os
import sys
import threading
import urllib.parse
import urllib.request

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runlytics import SummaryWriter  # noqa: E402
from runlytics.server import App, serve  # noqa: E402
from runlytics.store import Store  # noqa: E402


@pytest.fixture()
def logroot(tmp_path):
    """Two runs with scalars, histograms, text and a description on one tag."""
    for name, k in (("run_a", 1.0), ("run_b", 2.0)):
        with SummaryWriter(str(tmp_path / name)) as w:
            for step in range(100):
                w.add_scalar("loss/train", math.exp(-step * k / 50), step,
                             description="Training loss. Lower is better.")
                if step % 10 == 0:
                    w.add_histogram("weights/fc", [math.sin(i + step) for i in range(200)], step)
                    w.add_text("notes", "step **%d**" % step, step)
    return tmp_path


@pytest.fixture()
def store(logroot):
    s = Store([(None, str(logroot))], reload_interval=0, max_memory=1 << 28)
    s.scan(force=True)
    return s


@pytest.fixture()
def api(store):
    srv, _ = serve(App(store), "127.0.0.1", 0, tries=1)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d/" % srv.server_address[1]

    def get(path, **params):
        q = urllib.parse.urlencode(params, doseq=True)
        with urllib.request.urlopen(base + path + ("?" + q if q else "")) as r:
            return json.loads(r.read())
    get.base = base
    yield get
    srv.shutdown()
    srv.server_close()
