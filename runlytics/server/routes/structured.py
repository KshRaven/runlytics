"""Structured-data API: PR curves, embeddings, mesh, hyper-parameters and graphs."""
from __future__ import annotations

from ..responses import JSON
from .base import route

_KINDS = ("pr_curves", "projector", "mesh")


@route("/api/data")
def data(app, q):
    kind = q.str("kind")
    if kind not in _KINDS:
        return JSON({"error": "bad kind"}, 400)
    r = app.store.data(q.str("run"), kind, q.str("tag"), q.opt_int("i"))
    return JSON(r or {"error": "no such data"}, 200 if r else 404)


@route("/api/hparams")
def hparams(app, q):
    return JSON(app.store.hparams(q.list("run")))


@route("/api/graph")
def graph(app, q):
    g = app.store.graph(q.str("run"))
    return JSON(g or {"error": "no graph"}, 200 if g else 404)
