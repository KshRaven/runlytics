"""Tensor message encode/decode (numeric and string tensors)."""
from __future__ import annotations

import struct
from typing import NamedTuple

from .wire import f_bytes, f_int, iter_fields, read_varint, to_array

__all__ = ["DT_FLOAT", "DT_DOUBLE", "DT_INT32", "DT_UINT8", "DT_STRING", "DT_INT64", "Tensor", "decode_tensor",
           "encode_tensor", "encode_float_tensor", "encode_string_tensor", "numel"]

DT_FLOAT, DT_DOUBLE, DT_INT32, DT_UINT8, DT_STRING, DT_INT64 = 1, 2, 3, 4, 7, 9
_CODES = {DT_FLOAT: "f", DT_DOUBLE: "d", DT_INT32: "i", DT_UINT8: "B", DT_INT64: "q"}


class Tensor(NamedTuple):
    dtype: int
    shape: list
    values: object  # array/list of numbers, or list[bytes] for strings


def numel(shape) -> int:
    n = 1
    for d in shape:
        n *= d
    return n


def _shape(shape) -> bytes:
    return f_bytes(2, b"".join(f_bytes(2, f_int(1, d)) for d in shape))


def encode_tensor(dtype: int, shape, raw_le: bytes) -> bytes:
    """Dense tensor with little-endian ``raw_le`` content."""
    return f_int(1, dtype) + _shape(shape) + f_bytes(4, raw_le)


def encode_float_tensor(shape, floats_le: bytes, dtype: int = DT_FLOAT) -> bytes:
    return encode_tensor(dtype, shape, floats_le)


def encode_string_tensor(strings) -> bytes:
    items = [s.encode("utf-8") if isinstance(s, str) else bytes(s) for s in strings]
    return f_int(1, DT_STRING) + _shape([len(items)]) + b"".join(f_bytes(8, s) for s in items)


def _packed_ints(v) -> list[int]:
    out, i = [], 0
    while i < len(v):
        x, i = read_varint(v, i)
        out.append(x - (1 << 64) if x >= 1 << 63 else x)
    return out


def decode_tensor(buf) -> Tensor | None:
    dtype, shape, content, vals, strings = 0, [], b"", [], []
    for f, w, v in iter_fields(buf):
        if f == 1 and w == 0:
            dtype = v
        elif f == 2 and w == 2:
            for f2, w2, v2 in iter_fields(v):
                if f2 == 2 and w2 == 2:
                    for f3, w3, v3 in iter_fields(v2):
                        if f3 == 1 and w3 == 0:
                            shape.append(v3)
        elif f == 4 and w == 2:
            content = v
        elif f == 5:
            vals.extend(to_array("f", v) if w == 2 else [struct.unpack("<f", v)[0]])
        elif f == 6:
            vals.extend(to_array("d", v) if w == 2 else [struct.unpack("<d", v)[0]])
        elif f in (7, 10):
            vals.extend(_packed_ints(v) if w == 2 else [v - (1 << 64) if v >= 1 << 63 else v])
        elif f == 8 and w == 2:
            strings.append(bytes(v))
    if dtype == DT_STRING:
        return Tensor(dtype, shape, strings)
    if dtype not in _CODES:
        return None
    if len(content):
        vals = to_array(_CODES[dtype], content)
    elif not vals and numel(shape) == 1:
        vals = [0]
    return Tensor(dtype, shape, vals)
