"""Write one log directory that exercises every chart type and edge case, for dashboard debugging.

    python test/generate_all_logs.py [--logdir test/tmp/logs] [--runs 6] [--steps 200] [--serve] [--port 6006]

Edge cases covered: constant lines (500.0, 1.0, 0.1, 1e-8, 1e8), NaN/inf, step gaps, tiny/huge ranges, negative values,
float32 vs float64 scalars, add_scalars, many runs and tag groups, long tag names, every histogram shape, images (grid,
batch, boxes, video), audio, markdown text, graph, PR curves, hparams, custom scalars (multiline + margin), embeddings, mesh.
Optional libs (numpy, Pillow) are used when present; the matching charts are skipped otherwise.
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

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None


def gauss_list(n, mu, sd):
    return [random.gauss(mu, sd) for _ in range(n)]


def write_run(logdir: str, idx: int, steps: int) -> None:
    random.seed(idx)
    lr = 10 ** (-1 - idx * 0.4)
    name = "run_%02d_lr%.4f" % (idx, lr)
    with SummaryWriter(os.path.join(logdir, name)) as w:
        for step in range(steps):
            decay = math.exp(-step * (idx + 1) / steps * 3)
            loss = decay + random.gauss(0, 0.03)
            # --- scalars: realistic curves
            w.add_scalar("loss/train", loss, step, description="Training loss. **Lower is better.**")
            w.add_scalar("loss/val", loss * 1.15 + 0.05, step)
            w.add_scalar("acc/train", 1 - decay * 0.8 + random.gauss(0, 0.01), step)
            w.add_scalar("acc/val", 1 - decay * 0.9, step)
            # --- scalars: constant lines (must render perfectly flat, with and without smoothing)
            w.add_scalar("const/five_hundred", 500.0, step)
            w.add_scalar("const/one", 1.0, step)
            w.add_scalar("const/tenth_float32", 0.1, step)
            w.add_scalar("const/tiny", 1e-8, step)
            w.add_scalar("const/huge", 1e8, step)
            w.add_scalar("const/zero", 0.0, step)
            w.add_scalar("const/negative", -3.25, step)
            w.add_scalar("const/double", 500.0, step, double_precision=True)
            w.add_scalar("const/new_style", 1.0, step, new_style=True)
            w.add_scalar("lr", lr * (0.5 * (1 + math.cos(math.pi * step / steps))), step)
            # --- scalars: extreme / odd data
            w.add_scalar("odd/linear_up", step, step)
            w.add_scalar("odd/tiny_noise_on_big", 1000 + random.gauss(0, 1e-3), step)
            w.add_scalar("odd/negative_wave", -5 + 3 * math.sin(step / 10), step)
            w.add_scalar("odd/exponential", math.exp(step / 20), step)
            w.add_scalar("odd/spikes", 100 if step % 37 == 0 else random.random(), step)
            w.add_scalar("odd/step_function", 0 if step < steps // 2 else 1, step)
            if step % 50 == 25:
                w.add_scalar("odd/nan_inf", float("nan") if step % 100 == 25 else float("inf"), step)
            else:
                w.add_scalar("odd/nan_inf", random.random(), step)
            if step % 5 == 0:   # sparse: step gaps
                w.add_scalar("odd/sparse_every_5", random.random(), step)
            w.add_scalar("a_very_long_group_name_to_test_header_overflow/and_a_really_long_chart_title_that_should_be_ellipsized", step % 7, step)
            w.add_scalars("compare/metrics", {"precision": 0.5 + 0.4 * (1 - decay), "recall": 0.4 + 0.5 * (1 - decay)}, step)
            for g in range(3):   # extra groups so collapse/expand/pin have something to do
                w.add_scalar("group%d/series_a" % g, math.sin(step / (10 + g)) + idx, step)
                w.add_scalar("group%d/series_b" % g, math.cos(step / (10 + g)), step)
            # --- histograms
            if step % max(1, steps // 20) == 0:
                w.add_histogram("hist/shifting_mean", gauss_list(500, step / steps * 3, 1), step,
                                description="Distribution whose mean drifts right over time.")
                w.add_histogram("hist/narrowing", gauss_list(500, 0, 2 * decay + 0.05), step)
                w.add_histogram("hist/bimodal", gauss_list(250, -2, .5) + gauss_list(250, 2, .5), step)
                w.add_histogram("hist/constant", [1.0] * 100, step)
                w.add_histogram("hist/negative_only", [-abs(x) for x in gauss_list(400, 0, 1 + step / steps)], step)
                w.add_histogram("hist/huge_range", [random.expovariate(1e-3) for _ in range(500)], step)
                w.add_histogram("hist/tiny_range", gauss_list(500, 1e-6, 1e-8), step)
                w.add_histogram_raw("hist/raw", -1, 1, 100, 0.0, 33.3, [-1, -.5, 0, .5, 1], [10, 30, 40, 20, 0], step)
                w.add_text("text/markdown", "### step %d\n* loss = **%.4f**\n* `code`\n\n| a | b |\n|---|---|\n| 1 | 2 |" % (step, loss), step)
                w.add_text("text/plain_long", "lorem ipsum " * 200, step)
                w.add_text("text/unicode_<html>", "héllo 世界 🚀 <b>not bold</b>", step)
            # --- media / structured (numpy)
            if np is not None and step % max(1, steps // 10) == 0:
                w.add_image("images/random_chw", np.random.rand(3, 32, 32), step)
                w.add_image("images/gray_hw", np.random.rand(24, 24), step, dataformats="HW")
                w.add_image("images/gradient", np.tile(np.linspace(0, 1, 64), (3, 64, 1)), step)
                w.add_images("images/batch_grid", np.random.rand(8, 3, 16, 16), step)
                w.add_image_with_boxes("images/boxes", np.random.rand(3, 64, 64), [[8, 8, 40, 40], [30, 20, 60, 58]], step)
                w.add_pr_curve("pr/good", np.random.randint(0, 2, 300), np.clip(np.random.rand(300) * .5 + np.random.randint(0, 2, 300) * .5, 0, 1), step)
                w.add_pr_curve("pr/random", np.random.randint(0, 2, 300), np.random.rand(300), step)
                theta = np.linspace(0, 6.28, 300)
                w.add_mesh("mesh/helix_points", np.stack([np.cos(theta), np.sin(theta), theta / 3 + step / steps], 1)[None], global_step=step)
                try:
                    w.add_video("images/video_gif", np.random.rand(1, 6, 3, 24, 24), step, fps=4)
                except Exception as e:   # needs Pillow
                    if step == 0 and idx == 0:
                        print("skipped add_video:", e)
        if np is not None:
            w.add_audio("audio/sine_440", np.sin(np.linspace(0, 440 * 6.2832, 16000))[None, :], 0, sample_rate=16000)
            w.add_audio("audio/noise_stereo", np.random.uniform(-.3, .3, (2, 16000)), 1, sample_rate=16000)
            for s in (0, steps // 2):
                w.add_embedding(np.random.randn(300, 16) + s / 50, metadata=[str(i % 5) for i in range(300)],
                                tag="embedding/clusters", global_step=s)
            tri = np.array([[0, 1, 2], [0, 2, 3], [0, 3, 1], [1, 3, 2]])
            w.add_mesh("mesh/tetra_faces", np.array([[0, 0, 0], [1, 0, 0], [0.5, 1, 0], [0.5, 0.5, 1]]), colors=np.array([[255, 0, 0], [0, 255, 0], [0, 0, 255], [255, 255, 0]]), faces=tri, global_step=0)
        w.add_graph({"nodes": [
            {"name": "input", "op": "Input", "inputs": []},
            {"name": "conv1", "op": "Conv2d", "inputs": ["input"]},
            {"name": "bn1", "op": "BatchNorm", "inputs": ["conv1"]},
            {"name": "relu1", "op": "ReLU", "inputs": ["bn1"]},
            {"name": "conv2", "op": "Conv2d", "inputs": ["relu1"]},
            {"name": "skip_add", "op": "Add", "inputs": ["relu1", "conv2"]},
            {"name": "fc", "op": "Linear", "inputs": ["skip_add"]},
            {"name": "out", "op": "Softmax", "inputs": ["fc"]}]})
        w.add_custom_scalars_multilinechart(["loss/.*"], category="Overview", title="All losses")
        w.add_custom_scalars_multilinechart(["acc/train", "acc/val"], category="Overview", title="Accuracy")
        w.add_custom_scalars_marginchart(["loss/val", "loss/train", "odd/linear_up"], category="Margins", title="Loss margin")
        w.add_hparams({"lr": lr, "optimizer": random.choice(["sgd", "adam"]), "layers": 2 + idx % 4, "dropout": round(random.random() * .5, 2)},
                      {"final_loss": loss, "final_acc": 1 - decay}, run_name="trial", global_step=steps)


def write_logs(logdir: str, runs: int, steps: int) -> str:
    for i in range(runs):
        write_run(logdir, i, steps)
    return logdir


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--logdir", default=os.path.join(HERE, "tmp", "logs"))
    ap.add_argument("--runs", type=int, default=6)
    ap.add_argument("--steps", type=int, default=200)
    ap.add_argument("--serve", action="store_true", help="start the dashboard on the generated logs")
    ap.add_argument("--port", type=int, default=6006)
    a = ap.parse_args()
    d = write_logs(a.logdir, a.runs, a.steps)
    print("wrote %d runs to %s" % (a.runs, d))
    if a.serve:
        from runlytics.cli import main
        main(["--logdir", d, "--port", str(a.port), "--open"])
