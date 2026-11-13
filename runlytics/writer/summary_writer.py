"""Drop-in ``SummaryWriter``: scalars, histograms (here) plus media and structured summaries (mixins)."""
from __future__ import annotations

import os
import socket
import struct
import time

from ..charting.histogram import make_histogram
from ..core import (
    DT_DOUBLE, DT_FLOAT, 
    encode_event, encode_float_tensor, histogram_value, metadata, 
    scalar_value, summary, tensor_value
)
from ..utils.arrays import to_float
from .file_writer import EventFileWriter
from .media import MediaMixin
from .structured import StructuredMixin

__all__ = ["SummaryWriter"]


class SummaryWriter(MediaMixin, StructuredMixin):
    def __init__(self, logdir=None, comment="", purge_step=None, max_queue=10, flush_secs=120,
                 filename_suffix="", write_to_disk=True, log_dir=None, **kwargs):
        logdir = logdir or log_dir
        if not logdir:
            logdir = os.path.join("runs", time.strftime("%b%d_%H-%M-%S") + "_" + socket.gethostname() + comment)
        self.logdir = str(logdir)
        self._kw = dict(max_queue=max_queue, flush_secs=flush_secs, suffix=filename_suffix)
        self._write = write_to_disk
        self._writers: dict[str, EventFileWriter] = {}
        self._scalar_log: dict[str, list] = {}   # for export_scalars_to_json
        self._described: set = set()   # (writer dir, tag) pairs whose description was already written
        self._main = self._writer(self.logdir)
        if purge_step is not None and self._main:
            self._main.add(encode_event(time.time(), int(purge_step), session_status=1))

    # ---- plumbing --------------------------------------------------------------------------
    def _writer(self, d):
        if not self._write:
            return None
        w = self._writers.get(d)
        if w is None:
            w = self._writers[d] = EventFileWriter(d, **self._kw)
        return w

    def get_logdir(self):
        return self.logdir

    def _meta(self, tag, description, w_dir=None, plugin=None, content=b""):
        """SummaryMetadata for ``tag``; written once per tag and file so descriptions cost nothing afterwards."""
        key = (w_dir or self.logdir, tag)
        if (not description and not plugin) or key in self._described:
            return b""
        self._described.add(key)
        return metadata(plugin, None, description, content)

    def _log_scalar(self, tag, step, walltime, v):
        self._scalar_log.setdefault(tag, []).append([time.time() if walltime is None else walltime,
                                                     0 if step is None else int(step), v])

    def _emit(self, summary_bytes, step, walltime, w=None):
        w = w or self._main
        if w is not None:
            w.add(encode_event(time.time() if walltime is None else walltime,
                               0 if step is None else int(step), summary=summary_bytes))

    # ---- scalars / histograms --------------------------------------------------------------
    # ``description`` (keyword-only, optional) is shown behind the chart's "i" button in the dashboard.
    def add_scalar(self, tag, scalar_value_, global_step=None, walltime=None, new_style=False,
                   double_precision=False, *, description=None, **kw):
        v = to_float(scalar_value_)
        self._log_scalar(tag, global_step, walltime, v)
        if new_style or double_precision:
            dt, fmt = (DT_DOUBLE, "<d") if double_precision else (DT_FLOAT, "<f")
            t = encode_float_tensor([], struct.pack(fmt, v), dt)
            val = tensor_value(tag, t, self._meta(tag, description, plugin="scalars") or metadata("scalars"))
        else:
            val = scalar_value(tag, v, self._meta(tag, description))
        self._emit(summary(val), global_step, walltime)

    def add_scalars(self, main_tag, tag_scalar_dict, global_step=None, walltime=None, *, description=None):
        for tag, v in tag_scalar_dict.items():
            d = os.path.join(self.logdir, "%s_%s" % (main_tag.replace("/", "_"), tag))
            self._log_scalar(main_tag + "/" + tag, global_step, walltime, to_float(v))
            val = scalar_value(main_tag, to_float(v), self._meta(main_tag, description, d))
            self._emit(summary(val), global_step, walltime, self._writer(d))

    def add_histogram(self, tag, values, global_step=None, bins="default", walltime=None, max_bins=None, *,
                      description=None):
        h = make_histogram(values, bins, max_bins)
        self._emit(summary(histogram_value(tag, h, self._meta(tag, description))), global_step, walltime)

    def add_histogram_raw(self, tag, min, max, num, sum, sum_squares, bucket_limits, bucket_counts,
                          global_step=None, walltime=None, *, description=None):
        h = dict(min=float(min), max=float(max), num=float(num), sum=float(sum),
                 sum_squares=float(sum_squares), limits=list(bucket_limits), counts=list(bucket_counts))
        self._emit(summary(histogram_value(tag, h, self._meta(tag, description))), global_step, walltime)

    # ---- lifecycle -------------------------------------------------------------------------
    def flush(self):
        for w in self._writers.values():
            w.flush()

    def close(self):
        for w in self._writers.values():
            w.close()
        self._writers.clear()
        self._main = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
