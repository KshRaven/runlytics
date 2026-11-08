"""Command-line parsing."""
from __future__ import annotations

import argparse
import os

from .._version import __version__

__all__ = ["build_parser", "parse_specs", "parse_samples", "resolve_path"]


def _bool(s) -> bool:
    return str(s).lower() not in ("0", "false", "no", "off")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="runlytics", description="Fast, modern experiment dashboard.")
    p.add_argument("--logdir", nargs="?", const="", help="directory containing event files, searched recursively "
                   "(relative paths are resolved from the current directory; default: the current directory)")
    p.add_argument("--logdir_spec", help="comma list of [name:]path")
    p.add_argument("--host", default=None)
    p.add_argument("--bind_all", action="store_true", help="listen on all interfaces")
    p.add_argument("--port", type=int, default=6006)
    p.add_argument("--reload_interval", type=float, default=5.0, help="seconds between scans (0 = off)")
    p.add_argument("--path_prefix", default="")
    p.add_argument("--purge_orphaned_data", type=_bool, default=True)
    p.add_argument("--samples_per_plugin", default="", help="e.g. scalars=2000,histograms=50")
    p.add_argument("--max_memory_mb", type=int, default=1024, help="budget for parsed runs")
    p.add_argument("--idle_scan_secs", type=float, default=60.0, help="stop rescanning after this long without requests")
    p.add_argument("--idle_release_secs", type=float, default=300.0, help="free parsed runs after this long without requests")
    p.add_argument("--window_title", default="Runlytics")
    p.add_argument("--open", action="store_true", help="open a browser tab")
    p.add_argument("--dev", action="store_true", help=argparse.SUPPRESS)   # development mode (undocumented in --help)
    p.add_argument("--version", action="version", version=__version__)
    return p


def resolve_path(path) -> str:
    """Resolve a log directory the way a shell user expects: empty -> current directory; a relative path is taken from
    the current directory first; for rooted paths the cwd-relative reading (``/runs`` -> ``./runs``) is tried before the
    path as written."""
    cwd = os.getcwd()
    p = os.path.expanduser((path or "").strip().strip('"'))
    if not p:
        return cwd
    if not os.path.isabs(p):
        return os.path.abspath(os.path.join(cwd, p))
    rel = p.lstrip("/\\")
    if rel and not os.path.splitdrive(p)[0]:
        c = os.path.join(cwd, rel)
        if os.path.isdir(c) and not os.path.isdir(p):
            return c
    return p


def parse_specs(logdir, spec) -> list[tuple]:
    """``--logdir`` + ``--logdir_spec name:path,...`` -> ``[(name_or_None, path)]``."""
    specs = []
    for item in (spec or "").split(","):
        item = item.strip()
        if not item:
            continue
        head, sep, tail = item.partition(":")
        if sep and len(head) > 1 and tail:
            specs.append((head, resolve_path(tail)))
        else:
            specs.append((None, resolve_path(item)))
    if logdir:
        specs.insert(0, (None, resolve_path(logdir)))
    return specs


def parse_samples(text: str, defaults: dict | None = None) -> dict:
    samples = dict(defaults or {"scalars": 1500, "histograms": 50})
    for kv in filter(None, text.split(",")):
        k, _, v = kv.partition("=")
        if k in samples and v.isdigit():
            samples[k] = int(v)
    return samples
