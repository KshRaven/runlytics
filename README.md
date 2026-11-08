# Runlytics

A fast, lazy, modern experiment dashboard with a drop-in `SummaryWriter`. Pure standard library; numpy,
Pillow and matplotlib are optional.

```
pip install .                 # or: pip install ".[fast]"  /  ".[media]"
python examples/demo.py
runlytics --logdir demo_runs  # http://localhost:6006
```

```python
from runlytics import SummaryWriter

with SummaryWriter("runs/exp1") as w:
    w.add_scalar("loss/train", 0.5, step,
                 description="Cross-entropy on the training batch. Lower is better.")
    w.add_histogram("weights/fc1", tensor, step)
```

## The "i" button
Every chart has an **i** button. Pass `description="..."` (Markdown allowed) to any `add_*` call and that text
is shown there, so nobody has to open the code to learn what a chart means. Charts without a description show a
generic explanation of the chart type.

## Features
Scalars, custom scalars, histograms, images, graphs, text, audio, video, embeddings, PR curves, HParams and mesh
views, with smoothing, log axes, outlier clipping, zoom, CSV/PNG export, relative and wall-time axes and live reload.

## Why it is fast
- **Lazy**: startup only lists and stats `events.out.*` file names; a run is parsed only when selected.
- **Incremental**: live runs are tailed by byte offset; partial trailing records are handled.
- **Bounded**: LRU memory budget (`--max_memory_mb`), compact array storage, per-generation result caches.
- **Lean transfer**: LTTB downsampling, gzip + ETag, one request per tag for all runs.
- **UI**: charts are built only when scrolled into view; virtualized run list; no frameworks.
- **Writer**: async queue; CRC and I/O happen off your training thread.

## Running as a background service
Runlytics does no work while nobody is looking: after `--idle_scan_secs` (default 60) without a request it stops
rescanning directories, and after `--idle_release_secs` (default 300) it frees every parsed run and cache.
The next browser request resumes transparently. Event files that are not selected are never opened.

Existing event files written by other tools are read as-is (any `events.out.*` file), so old logs open directly.

## CLI
`--logdir`, `--logdir_spec name:path,...`, `--host`, `--bind_all`, `--port`, `--reload_interval`,
`--path_prefix`, `--purge_orphaned_data`, `--samples_per_plugin scalars=1500,histograms=50`,
`--max_memory_mb`, `--idle_scan_secs`, `--idle_release_secs`, `--window_title`, `--open`.

## Layout
```
runlytics/
  core/       binary format: CRC, records, wire, tensors, events
  charting/   line (LTTB), histogram, image, audio builders
  store/      lazy scanner, incremental run parser, cached queries
  server/     HTTP app, handler, routes/
  writer/     SummaryWriter, async file writer, mixins
  cli/        argument parsing and entry point
  utils/      small helpers
  web/        dependency-free UI (css/, js/)
```

See `CONTRIBUTING.md`, `CHANGELOG.md`, and `TODO.md`.

## Log directory

`--logdir` is resolved from the directory you start `runlytics` in: relative paths are tried relative to it first, then as written. Omit `--logdir` (or pass it without a value) to use the current directory.

## Development

`runlytics --dev ...` is meant for working on the dashboard itself: bundled web files are re-read from disk on every request (edit, then refresh; no restart) and each request is logged to stderr. It is intentionally not listed in `--help`.
