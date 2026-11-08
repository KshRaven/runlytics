"""Response value objects returned by route functions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

__all__ = ["JSON", "Raw"]


@dataclass
class JSON:
    obj: object
    status: int = 200


@dataclass
class Raw:
    body: bytes
    content_type: str
    etag: Optional[str] = None
    gz: Optional[bytes] = None   # pre-compressed body for static assets
    status: int = 200
