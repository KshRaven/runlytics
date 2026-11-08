"""Writer methods for images, video, audio and text."""
from __future__ import annotations

from ..charting import audio as _audio
from ..charting import image as _img
from ..core import audio_value, encode_string_tensor, image_value, metadata, summary, tensor_value
from ..utils.arrays import np, to_numpy

__all__ = ["MediaMixin"]


class MediaMixin:
    def _add_image_array(self, tag, hwc, global_step, walltime, description):
        a = _img.to_uint8(hwc)
        h, w, c = a.shape
        self._emit(summary(image_value(tag, h, w, c, _img.encode_png(a), self._meta(tag, description))),
                   global_step, walltime)

    def add_image(self, tag, img_tensor, global_step=None, walltime=None, dataformats="CHW", *, description=None):
        nhwc = _img.to_nhwc(img_tensor, dataformats)
        self._add_image_array(tag, _img.make_grid(_img.to_uint8(nhwc)), global_step, walltime, description)

    def add_images(self, tag, img_tensor, global_step=None, walltime=None, dataformats="NCHW", *, description=None):
        nhwc = _img.to_uint8(_img.to_nhwc(img_tensor, dataformats))
        self._add_image_array(tag, _img.make_grid(nhwc), global_step, walltime, description)

    def add_image_with_boxes(self, tag, img_tensor, box_tensor, global_step=None, walltime=None, rescale=1,
                             dataformats="CHW", labels=None, *, description=None):
        """Draws the boxes (``x0, y0, x1, y1``); ``labels`` is accepted for compatibility but not rendered."""
        hwc = _img.to_uint8(_img.to_nhwc(img_tensor, dataformats))[0]
        self._add_image_array(tag, _img.draw_boxes(hwc, box_tensor, rescale), global_step, walltime, description)

    def add_figure(self, tag, figure, global_step=None, close=True, walltime=None, *, description=None):
        figs = figure if isinstance(figure, (list, tuple)) else [figure]
        batch = np.stack([_img.figure_to_array(f) for f in figs])
        self._add_image_array(tag, _img.make_grid(batch), global_step, walltime, description)
        if close:
            import matplotlib.pyplot as plt
            for f in figs:
                plt.close(f)

    def add_video(self, tag, vid_tensor, global_step=None, fps=4, walltime=None, *, description=None):
        """``vid_tensor``: ``(N, T, C, H, W)``. Stored as an animated GIF (needs Pillow)."""
        v = _video_frames(vid_tensor)
        gif = _img.encode_gif(v, fps)
        h, w, c = v[0].shape
        self._emit(summary(image_value(tag, h, w, c, gif, self._meta(tag, description))), global_step, walltime)

    def add_audio(self, tag, snd_tensor, global_step=None, sample_rate=44100, walltime=None, *, description=None):
        wav, ch, frames = _audio.encode_wav(snd_tensor, sample_rate)
        self._emit(summary(audio_value(tag, float(sample_rate), ch, frames, wav, self._meta(tag, description))),
                   global_step, walltime)

    def add_text(self, tag, text_string, global_step=None, walltime=None, *, description=None):
        t = encode_string_tensor([str(text_string)])
        meta = self._meta(tag, description, plugin="text") or metadata("text")
        self._emit(summary(tensor_value(tag, t, meta)), global_step, walltime)


def _video_frames(vid):
    """``(N, T, C, H, W)`` -> list of T grid frames ``(H', W', C)`` uint8."""
    a = to_numpy(vid)
    if a.ndim != 5:
        raise ValueError("add_video expects (N, T, C, H, W), got %d dims" % a.ndim)
    a = _img.to_uint8(a.transpose(1, 0, 3, 4, 2))  # T, N, H, W, C
    return [_img.make_grid(a[t]) for t in range(a.shape[0])]
