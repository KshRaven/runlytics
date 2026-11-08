"""Runlytics: a fast, modern experiment dashboard and ``SummaryWriter``."""
from __future__ import annotations

from ._version import __version__
from .writer import SummaryWriter

__all__ = ["SummaryWriter", "__version__"]
