"""Core API: config, runs, tags, scalars, histograms."""
from __future__ import annotations

from ... import __version__
from ..responses import JSON
from .base import route


@route("/api/health")
def health(app, q):
    return JSON({"ok": True})


@route("/api/config")
def config(app, q):
    st = app.store
    return JSON(dict(version=__version__, boot=app.boot, title=app.title, samples=app.samples,
                     logdirs=[p for _, p in st.specs], reload_interval=st.interval))


@route("/api/runs")
def runs(app, q):
    return JSON(dict(runs=app.store.runs_list(force="refresh" in q)))


@route("/api/tags")
def tags(app, q):
    return JSON(app.store.tags(q.list("run")))


@route("/api/scalars")
def scalars(app, q):
    return JSON(app.store.scalars(q.list("run"), q.str("tag"), q.int("max_points", app.samples["scalars"], 10, 100000),
                                  q.opt_int("min_step"), q.opt_int("max_step")))


@route("/api/histograms")
def histograms(app, q):
    r = app.store.histograms(q.str("run"), q.str("tag"), q.int("bins", 30, 5, 200),
                             q.int("max_steps", app.samples["histograms"], 2, 1000))
    return JSON(r or {"error": "no such histogram"}, 200 if r else 404)


@route("/api/keep")
def keep(app, q):
    """The browser tells the server which runs it still shows; everything else is released from memory."""
    return JSON(dict(loaded=app.store.keep(q.list("run"))))
