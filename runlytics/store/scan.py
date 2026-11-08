"""Directory scanning: only names and stat() results are read, never file contents."""
from __future__ import annotations

import os
import time
from typing import Iterable

__all__ = ["RunMeta", "Scanner", "EVENT_MARK"]

EVENT_MARK = "events.out."
FileInfo = tuple  # (path, size, mtime_ns)


class RunMeta:
    __slots__ = ("name", "dir", "files", "size", "mtime", "rev")

    def __init__(self, name: str, d: str, files: list[FileInfo]):
        self.name, self.dir, self.files = name, d, files
        self.size = sum(f[1] for f in files)
        newest = max(f[2] for f in files)
        self.mtime = newest / 1e9
        self.rev = "%d-%d" % (self.size, newest)


class Scanner:
    """Walks a root directory; listings of directories that have not changed are served from a cache."""

    def __init__(self, follow_links: bool = True):
        self.follow = follow_links
        self._dirs: dict[str, tuple] = {}

    def walk(self, root: str) -> dict[str, list[FileInfo]]:
        found: dict[str, list[FileInfo]] = {}
        seen, stack = set(), [root]
        now = time.time_ns()
        while stack:
            d = stack.pop()
            try:
                st = os.stat(d)
            except OSError:
                continue
            if st.st_ino:
                key = (st.st_dev, st.st_ino)
                if key in seen:
                    continue
                seen.add(key)
            c = self._dirs.get(d)
            if c and c[0] == st.st_mtime_ns and now - st.st_mtime_ns > 2_000_000_000:
                subdirs, evs = c[1], c[2]
            else:
                subdirs, evs = self._list(d)
                self._dirs[d] = (st.st_mtime_ns, subdirs, evs)
            stack.extend(subdirs)
            files = []
            for p in sorted(evs):
                try:
                    s = os.stat(p)
                    files.append((p, s.st_size, s.st_mtime_ns))
                except OSError:
                    pass
            if files:
                found[d] = files
        return found

    def _list(self, d: str) -> tuple[list[str], list[str]]:
        subdirs: list[str] = []
        evs: list[str] = []
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=self.follow):
                            subdirs.append(e.path)
                        elif e.name.startswith(EVENT_MARK):
                            evs.append(e.path)
                    except OSError:
                        pass
        except OSError:
            pass
        return subdirs, evs


def stat_files(paths: Iterable[str]) -> list[FileInfo]:
    out = []
    for p in paths:
        try:
            s = os.stat(p)
            out.append((p, s.st_size, s.st_mtime_ns))
        except OSError:
            pass
    return out
