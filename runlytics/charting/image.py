"""Image data: layout conversion, grids, boxes, PNG/GIF encoding (numpy required; Pillow only for video)."""
from __future__ import annotations

import io
import struct
import zlib

from ..utils.arrays import np, require_numpy, to_numpy

__all__ = ["to_nhwc", "to_uint8", "make_grid", "encode_png", "encode_gif", "draw_boxes", "figure_to_array"]

_PALETTE = ((255, 64, 64), (64, 200, 64), (64, 128, 255), (255, 200, 0), (200, 80, 255), (0, 210, 210))


def to_nhwc(img, dataformats: str):
    """Reorder ``img`` to ``(N, H, W, C)``; missing N / C axes are added with size 1."""
    a = to_numpy(img)
    fmt = dataformats.upper()
    if a.ndim != len(fmt) or any(c not in "NHWC" for c in fmt) or len(set(fmt)) != len(fmt):
        raise ValueError("dataformats %r does not match array with %d dims" % (dataformats, a.ndim))
    a = a.transpose([fmt.index(c) for c in "NHWC" if c in fmt])
    present = [c for c in "NHWC" if c in fmt]
    for i, c in enumerate("NHWC"):
        if c not in present:
            a = np.expand_dims(a, i)
    return a


def to_uint8(a):
    """uint8 arrays pass through; everything else is treated as 0..1 floats and scaled."""
    if a.dtype == np.uint8:
        return a
    return np.clip(a.astype(np.float64) * 255.0, 0, 255).astype(np.uint8)


def make_grid(nhwc, ncols: int = 8):
    """Tile a ``(N, H, W, C)`` batch into one ``(H', W', C)`` image (no padding)."""
    n, h, w, c = nhwc.shape
    if n == 1:
        return nhwc[0]
    ncols = min(n, ncols)
    nrows = -(-n // ncols)
    grid = np.zeros((nrows * h, ncols * w, c), dtype=nhwc.dtype)
    for i in range(n):
        r, k = divmod(i, ncols)
        grid[r * h:(r + 1) * h, k * w:(k + 1) * w] = nhwc[i]
    return grid


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def encode_png(a) -> bytes:
    """Encode a ``(H, W, C)`` uint8 array (C in 1..4) as PNG."""
    h, w, c = a.shape
    color = {1: 0, 2: 4, 3: 2, 4: 6}.get(c)
    if color is None:
        raise ValueError("images need 1-4 channels, got %d" % c)
    rows = np.concatenate([np.zeros((h, 1), np.uint8), np.ascontiguousarray(a).reshape(h, w * c)], axis=1)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, color, 0, 0, 0)) +
            _chunk(b"IDAT", zlib.compress(rows.tobytes(), 6)) + _chunk(b"IEND", b""))


def encode_gif(frames, fps: float = 4) -> bytes:
    """Animated GIF from a list of ``(H, W, C)`` uint8 arrays (needs Pillow)."""
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        raise ImportError("add_video needs Pillow: pip install pillow") from None
    ims = [Image.fromarray(f if f.shape[2] != 1 else f[:, :, 0]).convert("RGB") for f in frames]
    buf = io.BytesIO()
    ims[0].save(buf, format="GIF", save_all=True, append_images=ims[1:], duration=max(1, int(1000 / fps)), loop=0)
    return buf.getvalue()


def draw_boxes(img, boxes, rescale: float = 1.0):
    """Draw 2px rectangles for ``(N, 4)`` ``x0, y0, x1, y1`` boxes on a copy of ``(H, W, C)`` ``img``."""
    img = img.copy()
    h, w, c = img.shape
    for k, b in enumerate(np.asarray(to_numpy(boxes), dtype=np.float64).reshape(-1, 4)):
        x0, y0, x1, y1 = (int(round(float(v) * rescale)) for v in b)
        x0, x1 = sorted((min(max(x0, 0), w - 1), min(max(x1, 0), w - 1)))
        y0, y1 = sorted((min(max(y0, 0), h - 1), min(max(y1, 0), h - 1)))
        col = np.array(_PALETTE[k % len(_PALETTE)] + (255,), dtype=np.uint8)[:c] if c >= 3 else np.full(c, 255, np.uint8)
        img[y0:y0 + 2, x0:x1 + 1] = col
        img[max(y1 - 1, 0):y1 + 1, x0:x1 + 1] = col
        img[y0:y1 + 1, x0:x0 + 2] = col
        img[y0:y1 + 1, max(x1 - 1, 0):x1 + 1] = col
    return img


def figure_to_array(fig):
    """Render a matplotlib figure to an ``(H, W, 3)`` uint8 array."""
    require_numpy("figures")
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    canvas = FigureCanvasAgg(fig)
    canvas.draw()
    return np.asarray(canvas.buffer_rgba())[:, :, :3].copy()
