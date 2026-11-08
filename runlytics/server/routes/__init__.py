"""API routes. Importing a submodule registers its routes."""
from __future__ import annotations

from . import core, media, structured  # noqa: F401  (importing registers the routes)
from .base import ROUTES, Query, route

__all__ = ["ROUTES", "Query", "route"]
