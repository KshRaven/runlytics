"""On-demand reading of image / audio payloads from their event-file records."""
from __future__ import annotations

import json

from ..core import decode_event, decode_tensor, extract_blob, read_record_at, sniff_image

__all__ = ["read_blob", "read_json", "read_graph"]


def read_blob(kind: str, tag: str, entry: tuple):
    """Return ``(mime, bytes)`` for an image/audio ``entry`` (``(step, wall, path, offset, ..., sub)``) or ``None``."""
    path, off = entry[2], entry[3]
    record = read_record_at(path, off)
    if kind == "images" and entry[6] >= 0:  # tensor-form image: pick the entry[6]-th encoded image
        for v in decode_event(record).values:
            if v.tag == tag and v.kind == "tensor":
                t = decode_tensor(v.payload)
                if t is not None and len(t.values) > 2 + entry[6]:
                    b = bytes(t.values[2 + entry[6]])
                    return sniff_image(b), b
        return None
    return extract_blob(record, tag)


def read_json(tag: str, entry: tuple):
    """Decode the structured payload of ``tag`` at ``entry``'s offset; ``None`` if it is missing or foreign."""
    try:
        for v in decode_event(read_record_at(entry[2], entry[3])).values:
            if v.tag == tag and v.kind == "tensor":
                t = decode_tensor(v.payload)
                if t is None or not len(t.values):
                    return None
                if len(entry) > 4 and entry[4] == "raw":   # [tp, fp, tn, fn, precision, recall] x thresholds
                    n = t.shape[1]
                    rows = [[round(float(x), 6) for x in t.values[r * n:(r + 1) * n]] for r in range(6)]
                    return dict(zip(("tp", "fp", "tn", "fn", "precision", "recall"), rows))
                return json.loads(bytes(t.values[0]))
    except (ValueError, OSError, IndexError, TypeError):
        return None
    return None


def read_graph(path: str, offset: int):
    """Decode the graph definition stored in the event record at ``offset`` (``None`` if not ours)."""
    try:
        g = decode_event(read_record_at(path, offset)).graph
        obj = json.loads(bytes(g)) if g is not None else None
    except (ValueError, OSError, TypeError):
        return None
    return obj if isinstance(obj, dict) and "nodes" in obj else None
