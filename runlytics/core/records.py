"""Length-prefixed, CRC-protected record framing used by event files."""
from __future__ import annotations

import struct

from .crc import masked_crc

__all__ = ["CorruptRecord", "frame_record", "parse_records", "read_record_at"]

_Q = struct.Struct("<Q")
_I = struct.Struct("<I")


class CorruptRecord(ValueError):
    """Raised when a record header or payload fails its checksum."""


def frame_record(data: bytes) -> bytes:
    header = _Q.pack(len(data))
    return b"".join((header, _I.pack(masked_crc(header)), data, _I.pack(masked_crc(data))))


def parse_records(buf: bytes, verify: bool = False) -> tuple[list[tuple[int, int]], int]:
    """Locate complete records in ``buf``.

    Returns ``(spans, consumed)`` where each span is ``(start, end)`` of a record payload.
    A trailing partial record is left unconsumed because the file may still be growing.
    """
    spans: list[tuple[int, int]] = []
    i, n = 0, len(buf)
    while i + 12 <= n:
        (length,) = _Q.unpack_from(buf, i)
        if _I.unpack_from(buf, i + 8)[0] != masked_crc(buf[i:i + 8]):
            raise CorruptRecord("bad length checksum at offset %d" % i)
        end = i + 12 + length + 4
        if end > n:
            break
        if verify and _I.unpack_from(buf, end - 4)[0] != masked_crc(buf[i + 12:end - 4]):
            raise CorruptRecord("bad data checksum at offset %d" % i)
        spans.append((i + 12, end - 4))
        i = end
    return spans, i


def read_record_at(path: str, offset: int) -> bytes:
    """Read the single record whose frame starts at ``offset``."""
    with open(path, "rb") as f:
        f.seek(offset)
        (length,) = _Q.unpack(f.read(8))
        f.seek(offset + 12)
        return f.read(length)
