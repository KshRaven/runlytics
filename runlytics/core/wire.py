"""Minimal protobuf wire-format primitives."""
from __future__ import annotations

import struct
import sys
from array import array
from typing import Iterator

__all__ = ["varint", "f_bytes", "f_str", "f_double", "f_float", "f_int", "f_doubles", "iter_fields",
           "read_varint", "to_array"]


def varint(n: int) -> bytes:
    if n < 0:
        n += 1 << 64
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _tag(field: int, wire: int) -> bytes:
    return varint((field << 3) | wire)


def f_bytes(field: int, b: bytes) -> bytes:
    return _tag(field, 2) + varint(len(b)) + b


def f_str(field: int, s: str) -> bytes:
    return f_bytes(field, s.encode("utf-8"))


def f_double(field: int, v: float) -> bytes:
    return _tag(field, 1) + struct.pack("<d", v)


def f_float(field: int, v: float) -> bytes:
    return _tag(field, 5) + struct.pack("<f", v)


def f_int(field: int, v: int) -> bytes:
    return _tag(field, 0) + varint(v)


def f_doubles(field: int, vals) -> bytes:
    vals = list(vals)
    return f_bytes(field, struct.pack("<%dd" % len(vals), *vals))


def read_varint(buf, i: int) -> tuple[int, int]:
    v = shift = 0
    while True:
        b = buf[i]
        i += 1
        v |= (b & 0x7F) << shift
        if b < 0x80:
            return v, i
        shift += 7


def iter_fields(buf) -> Iterator[tuple[int, int, object]]:
    """Yield ``(field, wire_type, value)``; length-delimited values are zero-copy memoryviews."""
    mv = memoryview(buf)
    i, n = 0, len(mv)
    while i < n:
        k, i = read_varint(mv, i)
        field, wire = k >> 3, k & 7
        if wire == 0:
            v, i = read_varint(mv, i)
        elif wire == 2:
            ln, i = read_varint(mv, i)
            v = mv[i:i + ln]
            i += ln
        elif wire == 1:
            v = mv[i:i + 8]
            i += 8
        elif wire == 5:
            v = mv[i:i + 4]
            i += 4
        else:
            raise ValueError("unsupported wire type %d" % wire)
        yield field, wire, v


def to_array(code: str, raw) -> array:
    a = array(code)
    a.frombytes(raw)
    if sys.byteorder == "big":  # pragma: no cover
        a.byteswap()
    return a
