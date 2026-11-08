"""Media API: image / audio / text listings and raw blobs."""
from __future__ import annotations

from ...utils.numbers import sample_indices
from ..responses import JSON, Raw
from .base import route

_CAP = 1000  # max rows per listing (evenly sampled, last row always included)


def _row(kind, i, e):
    if kind == "images":
        return dict(i=i, step=e[0], wall=round(e[1], 3), h=e[4], w=e[5])
    if kind == "audio":
        return dict(i=i, step=e[0], wall=round(e[1], 3), rate=round(e[4]), ch=e[5], frames=e[6])
    return dict(i=i, step=e[0], wall=round(e[1], 3), text=e[2])


@route("/api/media")
def media(app, q):
    kind = q.str("kind", "images")
    if kind not in ("images", "audio", "text"):
        return JSON({"error": "bad kind"}, 400)
    r = app.store.entries(q.str("run"), kind, q.str("tag"))
    if r is None:
        return JSON({"error": "no such data"}, 404)
    lst, gen = r
    return JSON(dict(gen=gen, n=len(lst), rows=[_row(kind, i, lst[i]) for i in sample_indices(len(lst), _CAP)]))


@route("/api/blob")
def blob(app, q):
    kind = q.str("kind", "images")
    r = app.store.entries(q.str("run"), kind, q.str("tag"))
    i = q.int("i", 0, 0, 10 ** 9)
    b = app.store.blob(q.str("run"), kind, q.str("tag"), i) if r else None
    if b is None:
        return JSON({"error": "no such blob"}, 404)
    return Raw(b[1], b[0], '"%d-%d"' % (r[1], i))
