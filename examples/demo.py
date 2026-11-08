"""Generate a few synthetic runs: python examples/demo.py && runlytics --logdir demo_runs"""
import math
import random

from runlytics import SummaryWriter

for name, lr in [("lr_0.1", 0.1), ("lr_0.01", 0.01), ("lr_0.001", 0.001)]:
    with SummaryWriter("demo_runs/" + name) as w:
        for step in range(2000):
            loss = math.exp(-step * lr * 0.01) + random.gauss(0, 0.03)
            w.add_scalar("loss/train", loss, step)
            if step % 50 == 0:
                w.add_scalar("loss/val", loss * 1.1, step)
                w.add_histogram("weights/layer1", [random.gauss(step / 2000, 1 - step / 4000) for _ in range(1000)], step)
                w.add_histogram("grads/layer1", [random.gauss(0, 1 / (1 + step / 100)) for _ in range(1000)], step)
print("wrote demo_runs/")
