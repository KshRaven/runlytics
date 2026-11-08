"""CRC32C (Castagnoli) with optional C accelerators and the masked variant used by record framing."""
from __future__ import annotations

__all__ = ["crc32c", "masked_crc"]

_TABLE: list[int] = []
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = (_c >> 1) ^ 0x82F63B78 if _c & 1 else _c >> 1
    _TABLE.append(_c)


def _crc32c_py(data: bytes, crc: int = 0) -> int:
    crc ^= 0xFFFFFFFF
    table = _TABLE
    for b in data:
        crc = table[(crc ^ b) & 0xFF] ^ (crc >> 8)
    return crc ^ 0xFFFFFFFF


try:  # optional accelerators
    from google_crc32c import value as crc32c  # type: ignore
except Exception:  # pragma: no cover
    try:
        from crc32c import crc32c  # type: ignore
    except Exception:
        crc32c = _crc32c_py


def masked_crc(data: bytes) -> int:
    c = crc32c(data) & 0xFFFFFFFF
    return ((((c >> 15) | (c << 17)) & 0xFFFFFFFF) + 0xA282EAD8) & 0xFFFFFFFF
