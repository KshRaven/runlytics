# Runlytics

Runlytics is a Python package for logging experiment data and viewing it in a local web dashboard. It includes a
`SummaryWriter` API and reads existing event files named `events.out.*`. Python 3.10 or newer is required.

## Install

```sh
python -m pip install runlytics
```

Optional dependencies are available as extras:

```sh
python -m pip install "runlytics[fast]"   # NumPy and Google CRC32C
python -m pip install "runlytics[media]"  # NumPy, Pillow, and Matplotlib
```

## Quick start

Write data to a log directory:

```python
from runlytics import SummaryWriter

with SummaryWriter("runs/experiment-1") as writer:
    writer.add_scalar("loss/train", 0.42, 1)
    writer.add_histogram("weights/layer1", [0.1, 0.2, 0.3], 1)
```

Start the dashboard and open `http://localhost:6006`:

```sh
runlytics --logdir runs --open
```

Runlytics searches the selected directory recursively. If `--logdir` is omitted, it uses the current directory.
Use `--logdir_spec name:path,...` to display multiple log directories. Run `runlytics --help` for server and
display options.

## Data and charts

The writer and dashboard support scalars, histograms, images, audio, video, text, graphs, embeddings, PR curves,
HParams, and meshes. Some media and structured-data operations require the optional dependencies listed above.
Writer methods accept an optional `description` string for chart context.

## Development

```sh
python -m pip install -e ".[dev]"
pytest -q
ruff check .
```

`python examples/demo.py` creates sample runs in `demo_runs/`; view them with
`runlytics --logdir demo_runs`. The main package areas are `writer/`, `store/`, `charting/`, `server/`, `cli/`,
and `web/`.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development conventions, [pypimgr documentation](scripts/pypimgr/README.md)
for release instructions, [CHANGELOG.md](CHANGELOG.md) for release history, and [LICENSE](LICENSE) for the license.
