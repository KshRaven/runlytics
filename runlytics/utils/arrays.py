"""Array helpers: optional numpy and tensor-library interop."""
from __future__ import annotations

from typing import Any

try:  # numpy is optional; everything has a pure-Python fallback unless noted
    import numpy as np
except Exception:  # pragma: no cover
    np = None  # type: ignore[assignment]

__all__ = ["np", "to_float", "to_numpy", "require_numpy"]


def to_float(value: Any) -> float:
    """Convert python / numpy / framework scalars to ``float``."""
    if hasattr(value, "item"):
        value = value.item()
    return float(value)


def to_numpy(x: Any):
    """Convert tensors / lists to a numpy array (framework tensors are detached and moved to CPU)."""
    require_numpy("array conversion")
    if hasattr(x, "detach"):
        x = x.detach().cpu().numpy()
    return np.asarray(x)


def require_numpy(feature: str = "this feature") -> None:
    if np is None:
        raise ImportError("numpy is required for %s: pip install numpy" % feature)
