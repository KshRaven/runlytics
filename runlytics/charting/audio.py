"""Audio data: WAV encoding (16-bit PCM)."""
from __future__ import annotations

import io
import wave

from ..utils.arrays import np, to_numpy

__all__ = ["encode_wav"]


def encode_wav(snd, sample_rate: int = 44100) -> tuple[bytes, int, int]:
    """Return ``(wav_bytes, channels, frames)`` for a 1-D mono signal or a 2-D ``(channels, frames)`` array in [-1, 1]."""
    a = np.squeeze(to_numpy(snd)).astype(np.float64)
    if a.ndim == 0:
        a = a.reshape(1)
    if a.ndim == 2 and a.shape[0] > a.shape[1]:
        a = a.T  # given as (frames, channels)
    if a.ndim == 1:
        a = a[None, :]
    if a.ndim != 2:
        raise ValueError("audio must be 1-D or 2-D, got %d dims" % a.ndim)
    ch, frames = a.shape
    pcm = (np.clip(a, -1.0, 1.0) * 32767).astype("<i2").T.reshape(-1)  # interleaved frames
    buf = io.BytesIO()
    with wave.open(buf, "wb") as f:
        f.setnchannels(ch)
        f.setsampwidth(2)
        f.setframerate(int(sample_rate))
        f.writeframes(pcm.tobytes())
    return buf.getvalue(), ch, frames
