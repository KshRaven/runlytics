"""Event / summary message encode and decode."""
from __future__ import annotations

import json
import struct
from array import array
from typing import NamedTuple

from .tensors import Tensor, decode_tensor, encode_string_tensor
from .wire import f_bytes, f_double, f_doubles, f_float, f_int, f_str, iter_fields, to_array

__all__ = ["Event", "Value", "Meta", "Histo", "SESSION_START", "encode_event", "decode_event", "decode_value",
           "metadata", "value", "summary", "scalar_value", "histogram_value", "image_value", "audio_value",
           "tensor_value", "json_value", "extract_blob", "sniff_image", "tensor_of"]

SESSION_START = 1


class Meta(NamedTuple):
    plugin: str | None
    display_name: str | None
    description: str | None
    content: bytes = b""


class Value(NamedTuple):
    tag: str
    kind: str | None
    payload: object
    meta: Meta | None


class Event(NamedTuple):
    wall: float
    step: int
    file_version: str | None
    graph: object  # memoryview of graph_def or None
    session: int | None
    values: list


class Histo:
    __slots__ = ("min", "max", "num", "sum", "sum_squares", "limits", "counts")

    def __init__(self):
        self.min = self.max = self.num = self.sum = self.sum_squares = 0.0
        self.limits, self.counts = array("d"), array("d")


# ------------------------------------------------------------------ encode
def metadata(plugin: str | None = None, display_name: str | None = None, description: str | None = None,
             content: bytes = b"") -> bytes:
    """Encode a SummaryMetadata message (plugin name + opaque content, display name, description)."""
    out = b""
    if plugin:
        out += f_bytes(1, f_str(1, plugin) + (f_bytes(2, content) if content else b""))
    if display_name:
        out += f_str(2, display_name)
    if description:
        out += f_str(3, description)
    return out


def value(tag: str, body: bytes, meta: bytes = b"") -> bytes:
    return f_str(1, tag) + (f_bytes(9, meta) if meta else b"") + body


def summary(*values: bytes) -> bytes:
    return b"".join(f_bytes(1, v) for v in values)


def scalar_value(tag: str, v: float, meta: bytes = b"") -> bytes:
    return value(tag, f_float(2, v), meta)


def histogram_value(tag: str, h: dict, meta: bytes = b"") -> bytes:
    body = (f_double(1, h["min"]) + f_double(2, h["max"]) + f_double(3, h["num"]) + f_double(4, h["sum"]) +
            f_double(5, h["sum_squares"]) + f_doubles(6, h["limits"]) + f_doubles(7, h["counts"]))
    return value(tag, f_bytes(5, body), meta)


def image_value(tag: str, height: int, width: int, channels: int, encoded: bytes, meta: bytes = b"") -> bytes:
    body = f_int(1, height) + f_int(2, width) + f_int(3, channels) + f_bytes(4, encoded)
    return value(tag, f_bytes(4, body), meta)


def audio_value(tag: str, rate: float, channels: int, frames: int, wav: bytes, meta: bytes = b"") -> bytes:
    body = (f_float(1, rate) + f_int(2, channels) + f_int(3, frames) + f_bytes(4, wav) + f_str(5, "audio/wav"))
    return value(tag, f_bytes(6, body), meta)


def tensor_value(tag: str, tensor: bytes, meta: bytes = b"") -> bytes:
    return value(tag, f_bytes(8, tensor), meta)


def json_value(tag: str, obj, plugin: str, description: str | None = None) -> bytes:
    """Structured payloads (hparams, layouts, meshes) are stored as a JSON string tensor."""
    t = encode_string_tensor([json.dumps(obj, separators=(",", ":"))])
    return tensor_value(tag, t, metadata(plugin, None, description))


def encode_event(wall: float, step: int = 0, summary: bytes | None = None, file_version: str | None = None,
                 session_status: int | None = None, graph_def: bytes | None = None) -> bytes:
    out = f_double(1, wall) + f_int(2, step)
    if file_version:
        out += f_str(3, file_version)
    if graph_def is not None:
        out += f_bytes(4, graph_def)
    if summary is not None:
        out += f_bytes(5, summary)
    if session_status is not None:
        out += f_bytes(7, f_int(1, session_status))
    return out


# ------------------------------------------------------------------ decode
def _decode_histo(buf) -> Histo:
    h = Histo()
    names = {1: "min", 2: "max", 3: "num", 4: "sum", 5: "sum_squares"}
    for f, w, v in iter_fields(buf):
        if w == 1 and f in names:
            setattr(h, names[f], struct.unpack("<d", v)[0])
        elif f in (6, 7):
            tgt = h.limits if f == 6 else h.counts
            if w == 2:
                tgt.extend(to_array("d", v))
            elif w == 1:
                tgt.append(struct.unpack("<d", v)[0])
    return h


def _decode_meta(buf) -> Meta:
    plugin = display = desc = None
    content = b""
    for f, w, v in iter_fields(buf):
        if f == 1 and w == 2:
            for f2, w2, v2 in iter_fields(v):
                if f2 == 1 and w2 == 2:
                    plugin = bytes(v2).decode("utf-8", "replace")
                elif f2 == 2 and w2 == 2:
                    content = bytes(v2)
        elif f == 2 and w == 2:
            display = bytes(v).decode("utf-8", "replace")
        elif f == 3 and w == 2:
            desc = bytes(v).decode("utf-8", "replace")
    return Meta(plugin, display, desc, content)


def _decode_image_info(buf) -> tuple[int, int, int]:
    h = w_ = c = 0
    for f, w, v in iter_fields(buf):
        if w == 0:
            if f == 1:
                h = v
            elif f == 2:
                w_ = v
            elif f == 3:
                c = v
    return h, w_, c


def _decode_audio_info(buf) -> tuple[float, int, int]:
    rate, ch, frames = 0.0, 0, 0
    for f, w, v in iter_fields(buf):
        if f == 1 and w == 5:
            rate = struct.unpack("<f", v)[0]
        elif f == 2 and w == 0:
            ch = v
        elif f == 3 and w == 0:
            frames = v
    return rate, ch, frames


def decode_value(buf) -> Value:
    """Decode one summary value. Large payloads (image/audio bytes, tensors) are not copied."""
    tag, kind, payload, meta = "", None, None, None
    for f, w, v in iter_fields(buf):
        if f == 1 and w == 2:
            tag = bytes(v).decode("utf-8", "replace")
        elif f == 2 and w == 5:
            kind, payload = "scalars", struct.unpack("<f", v)[0]
        elif f == 5 and w == 2:
            kind, payload = "histograms", _decode_histo(v)
        elif f == 4 and w == 2:
            kind, payload = "images", _decode_image_info(v)
        elif f == 6 and w == 2:
            kind, payload = "audio", _decode_audio_info(v)
        elif f == 8 and w == 2:
            kind, payload = "tensor", v
        elif f == 9 and w == 2:
            meta = _decode_meta(v)
    return Value(tag, kind, payload, meta)


def decode_event(buf) -> Event:
    wall, step, fv, graph, session, values = 0.0, 0, None, None, None, []
    for f, w, v in iter_fields(buf):
        if f == 1 and w == 1:
            wall = struct.unpack("<d", v)[0]
        elif f == 2 and w == 0:
            step = v - (1 << 64) if v >= 1 << 63 else v
        elif f == 3 and w == 2:
            fv = bytes(v).decode("utf-8", "replace")
        elif f == 4 and w == 2:
            graph = v
        elif f == 5 and w == 2:
            for f2, w2, v2 in iter_fields(v):
                if f2 == 1 and w2 == 2:
                    values.append(decode_value(v2))
        elif f == 7 and w == 2:
            for f2, w2, v2 in iter_fields(v):
                if f2 == 1 and w2 == 0:
                    session = v2
    return Event(wall, step, fv, graph, session, values)


def sniff_image(b) -> str:
    head = bytes(b[:4])
    return "image/png" if head[:2] == b"\x89P" else "image/gif" if head[:3] == b"GIF" else \
        "image/jpeg" if head[:2] == b"\xff\xd8" else "application/octet-stream"


def extract_blob(event_buf, tag: str) -> tuple[str, bytes] | None:
    """Pull the encoded image/audio bytes for ``tag`` out of one event record."""
    for f, w, v in iter_fields(event_buf):
        if f == 5 and w == 2:
            for f2, w2, v2 in iter_fields(v):
                if f2 != 1:
                    continue
                t, blob, mime = "", None, None
                for f3, w3, v3 in iter_fields(v2):
                    if f3 == 1:
                        t = bytes(v3).decode("utf-8", "replace")
                    elif f3 in (4, 6) and w3 == 2:
                        for f4, w4, v4 in iter_fields(v3):
                            if f4 == 4 and w4 == 2:
                                blob = bytes(v4)
                            elif f4 == 5 and w4 == 2 and f3 == 6:
                                mime = bytes(v4).decode()
                if t == tag and blob is not None:
                    return (mime or sniff_image(blob)), blob
    return None


def tensor_of(payload) -> Tensor | None:
    return decode_tensor(payload) if payload is not None else None
