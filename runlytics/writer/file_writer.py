"""Asynchronous event-file writer: callers enqueue raw event bytes, a thread frames and writes them."""
from __future__ import annotations

import atexit
import os
import queue
import socket
import threading
import time
import warnings
import weakref

from ..core import encode_event, frame_record

__all__ = ["EventFileWriter"]

_FLUSH, _CLOSE = object(), object()
_OPEN: weakref.WeakSet[EventFileWriter] = weakref.WeakSet()
_uid = 0
_uid_lock = threading.Lock()


def _next_uid() -> int:
    global _uid
    with _uid_lock:
        _uid += 1
        return _uid


class EventFileWriter(threading.Thread):
    """One ``events.out.runlytics.*`` file; CRC + I/O happen off the caller's thread."""

    def __init__(self, logdir: str, max_queue: int = 10, flush_secs: float = 120, suffix: str = ""):
        super().__init__(daemon=True, name="runlytics-writer")
        os.makedirs(logdir, exist_ok=True)
        self.logdir = logdir
        name = "events.out.runlytics.%d.%s.%d.%d%s" % (
            time.time(), socket.gethostname(), os.getpid(), _next_uid(), suffix)
        self.path = os.path.join(logdir, name)
        self._f = open(self.path, "wb", buffering=1 << 16)
        self._q: queue.Queue = queue.Queue(maxsize=max(1, max_queue))
        self._flush_secs = max(1, flush_secs)
        self._closed = False
        self._f.write(frame_record(encode_event(time.time(), 0, file_version="runlytics.event:1")))
        self._f.flush()
        self.start()
        _OPEN.add(self)

    def add(self, event_bytes: bytes) -> None:
        if self._closed:
            raise ValueError("writer is closed")
        self._q.put(event_bytes)

    def run(self) -> None:
        last = time.time()
        while True:
            try:
                item = self._q.get(timeout=self._flush_secs)
            except queue.Empty:
                self._f.flush()
                continue
            try:
                if item is _CLOSE:
                    self._f.flush()
                    self._f.close()
                    return
                if item is _FLUSH:
                    self._f.flush()
                else:
                    self._f.write(frame_record(item))
                    if time.time() - last > self._flush_secs:
                        self._f.flush()
                        last = time.time()
            except Exception as e:  # pragma: no cover
                warnings.warn("runlytics writer error: %s" % e)
            finally:
                self._q.task_done()

    def flush(self) -> None:
        if not self._closed:
            self._q.put(_FLUSH)
            self._q.join()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._q.put(_CLOSE)
            self.join(timeout=30)


@atexit.register
def _close_all() -> None:  # flush anything the user forgot to close
    for w in list(_OPEN):
        try:
            w.close()
        except Exception:
            pass
