"""Write sample logs for every chart type into tests/tmp and boot the dashboard on them.

    python tests/dashboard_demo.py [--port 6006] [--no-open]
"""
from __future__ import annotations

import argparse
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from runlytics import SummaryWriter  # noqa: E402
from runlytics.cli import main  # noqa: E402

LOGDIR = os.path.join(HERE, "tmp", "logs")


def write_logs(logdir: str = LOGDIR) -> str:
    try:
        import numpy as np
    except ImportError:
        np = None
    for name, lr in (("lr_0.1", 0.1), ("lr_0.01", 0.01)):
        with SummaryWriter(os.path.join(logdir, name)) as w:
            for step in range(300):
                loss = math.exp(-step * lr * 0.05) + random.gauss(0, 0.02)
                w.add_scalar("loss/train", loss, step,
                             description="Cross-entropy on each training batch. **Lower is better.**")
                w.add_scalar("loss/val", loss * 1.1, step)
                w.add_scalar("lr", lr, step)
                if step % 20 == 0:
                    w.add_histogram("weights/layer1", [random.gauss(step / 300, 1) for _ in range(500)], step,
                                    description="Distribution of the first layer's weights over time.")
                    w.add_text("notes", "### step %d\nloss = **%.3f**" % (step, loss), step)
                    if np is not None:
                        w.add_image("samples", np.random.rand(3, 32, 32), step)
                        w.add_pr_curve("pr/cls0", np.random.randint(0, 2, 200), np.random.rand(200), step)
            if np is not None:
                w.add_audio("tone", np.sin(np.linspace(0, 440 * 6.28, 16000))[None, :], 0, sample_rate=16000)
                w.add_embedding(np.random.randn(300, 16), metadata=[str(i % 5) for i in range(300)], tag="emb",
                                global_step=0)
                theta = np.linspace(0, 6.28, 400)
                w.add_mesh("helix", np.stack([np.cos(theta), np.sin(theta), theta / 3], 1)[None], global_step=0)
            w.add_graph({"nodes": [
                {"name": "input", "op": "Input", "inputs": []},
                {"name": "fc1", "op": "Linear", "inputs": ["input"]},
                {"name": "relu", "op": "ReLU", "inputs": ["fc1"]},
                {"name": "fc2", "op": "Linear", "inputs": ["relu"]},
                {"name": "out", "op": "Softmax", "inputs": ["fc2"]}]})
            w.add_custom_scalars_multilinechart(["loss/.*"], category="Overview", title="Losses")
            w.add_hparams({"lr": lr, "optimizer": "sgd"}, {"final_loss": loss}, run_name="trial", global_step=300)
    return logdir


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=6006)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()
    d = write_logs()
    print("wrote sample logs to", d)
    main(["--logdir", d, "--port", str(a.port)] + ([] if a.no_open else ["--open"]))
