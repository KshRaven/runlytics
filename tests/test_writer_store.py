import json
import os

import pytest

from runlytics import SummaryWriter
from runlytics.store import Store


def _store(root):
    s = Store([(None, str(root))], reload_interval=0, max_memory=1 << 28)
    s.scan(force=True)
    return s


def test_lazy_scan_lists_runs_without_loading(logroot, store):
    assert sorted(r["name"] for r in store.runs_list()) == ["run_a", "run_b"]
    assert not store._runs  # nothing parsed yet


def test_scalars_and_description(store):
    out = store.scalars(["run_a", "run_b"], "loss/train")
    assert len(out["run_a"]["s"]) == 100 and out["run_a"]["v"][0] > out["run_a"]["v"][-1]
    tags = store.tags(["run_a"])
    assert "loss/train" in tags["scalars"] and tags["desc"]["scalars"]["loss/train"].startswith("Training loss")


def test_downsampling_and_step_window(store):
    assert len(store.scalars(["run_a"], "loss/train", max_points=10)["run_a"]["s"]) == 10
    w = store.scalars(["run_a"], "loss/train", lo=40, hi=50)["run_a"]["s"]
    assert 40 in w and 50 in w and max(w) <= 51


def test_histograms(store):
    h = store.histograms("run_a", "weights/fc", bins=10)
    assert h["n"] == 10 and len(h["counts"][0]) == 10


def test_text_media(store):
    lst, _ = store.entries("run_a", "text", "notes")
    assert len(lst) == 10 and "**0**" in lst[0][2]


def test_incremental_tail(tmp_path):
    w = SummaryWriter(str(tmp_path / "live"))
    w.add_scalar("x", 1.0, 0)
    w.flush()
    s = _store(tmp_path)
    assert len(s.scalars(["live"], "x")["live"]["s"]) == 1
    w.add_scalar("x", 2.0, 1)
    w.flush()
    s.run("live").last_check = 0
    assert len(s.scalars(["live"], "x")["live"]["s"]) == 2
    w.close()


def test_purge_step_discards_orphans(tmp_path):
    with SummaryWriter(str(tmp_path / "r")) as w:
        for i in range(10):
            w.add_scalar("x", i, i)
    with SummaryWriter(str(tmp_path / "r"), purge_step=5) as w:
        w.add_scalar("x", 99, 5)
    v = _store(tmp_path).scalars(["r"], "x")["r"]
    assert v["s"][-1] == 5 and v["v"][-1] == 99 and 6 not in v["s"]


def test_add_scalars_makes_sub_runs(tmp_path):
    with SummaryWriter(str(tmp_path / "p")) as w:
        w.add_scalars("acc", {"train": 0.5, "val": 0.4}, 1)
    assert len(_store(tmp_path).runs_list()) == 3


def test_export_scalars_to_json(tmp_path):
    with SummaryWriter(str(tmp_path / "e")) as w:
        w.add_scalar("a", 1.5, 3)
        out = tmp_path / "s.json"
        w.export_scalars_to_json(str(out))
    assert json.loads(out.read_text())["a"][0][1:] == [3, 1.5]


def test_unknown_method_raises(tmp_path):
    with SummaryWriter(str(tmp_path / "u")) as w:
        with pytest.raises(AttributeError):
            w.add_nothing("x")


def test_structured_kinds(tmp_path):
    np = pytest.importorskip("numpy")
    with SummaryWriter(str(tmp_path / "exp")) as w:
        w.add_pr_curve("pr", np.array([0, 1, 1, 0, 1]), np.array([0.1, 0.8, 0.7, 0.3, 0.9]), 0, description="PR")
        w.add_embedding(np.random.rand(20, 6), metadata=list("abcdefghijklmnopqrst"), tag="emb", global_step=0)
        w.add_mesh("m", np.random.rand(1, 12, 3), faces=np.array([[[0, 1, 2], [2, 3, 4]]]), global_step=0)
        w.add_custom_scalars_multilinechart(["loss.*"], category="c", title="t")
        w.add_graph({"nodes": [{"name": "in", "op": "Input", "inputs": []}, {"name": "fc", "op": "Linear", "inputs": ["in"]}]})
        w.add_hparams({"lr": 0.1, "opt": "sgd"}, {"acc": 0.9}, run_name="trial", global_step=1)
        w.add_scalar("loss/a", 1.0, 0)
    s = _store(tmp_path)
    d = s.data("exp", "pr_curves", "pr")
    assert len(d["obj"]["precision"]) == 127 and d["obj"]["recall"][0] == 1.0
    e = s.data("exp", "projector", "emb")["obj"]
    assert e["shape"] == [20, 6] and len(e["data"]) == 120 and e["header"] == ["label"]
    assert len(s.data("exp", "mesh", "m")["obj"]["v"]) == 12
    assert s.graph("exp")["nodes"][1]["op"] == "Linear"
    assert s.tags(["exp"])["layout"]["c"]["t"] == ["Multiline", ["loss.*"]]
    hp = s.hparams(["exp/trial"])
    assert hp["rows"][0]["hparams"]["lr"] == 0.1 and hp["rows"][0]["metrics"]["acc"] == pytest.approx(0.9)
    assert s.tags(["exp"])["desc"]["pr_curves"]["pr"] == "PR"


def test_media_kinds(tmp_path):
    np = pytest.importorskip("numpy")
    with SummaryWriter(str(tmp_path / "m")) as w:
        w.add_image("img", np.random.rand(3, 8, 8), 0)
        w.add_images("imgs", np.random.rand(4, 3, 8, 8), 0)
        w.add_audio("snd", np.sin(np.linspace(0, 100, 8000))[None, :], 0, sample_rate=8000)
    s = _store(tmp_path)
    assert s.blob("m", "images", "img", 0)[0] == "image/png"
    assert s.blob("m", "images", "imgs", 0)[1][:4] == b"\x89PNG"
    assert s.blob("m", "audio", "snd", 0)[1][:4] == b"RIFF"


def test_release_frees_runs_and_reloads_lazily(store):
    store.scalars(["run_a"], "loss/train")
    assert store._runs
    store.release()
    assert not store._runs and len(store._cache) == 0
    assert len(store.scalars(["run_a"], "loss/train")["run_a"]["s"]) == 100


def test_foreign_payloads_never_break_tags(tmp_path):
    """Non-JSON structured payloads (as other tools write them) are skipped; the rest of the run still loads."""
    from runlytics.core import (DT_FLOAT, encode_event, encode_float_tensor, encode_string_tensor, frame_record,
                                metadata, summary, tensor_value)
    import struct
    d = tmp_path / "foreign"
    d.mkdir()
    ev = lambda step, val: frame_record(encode_event(1.0, step, summary=summary(val)))  # noqa: E731
    blob = (frame_record(encode_event(1.0, 0, file_version="x"))
            + ev(0, tensor_value("lay", encode_string_tensor([b"\x08\x01binary-not-json"]), metadata("custom_scalars")))
            + ev(0, tensor_value("hp", encode_string_tensor([b"\x0a\x02zz"]), metadata("hparams")))
            + ev(0, tensor_value("pr", encode_float_tensor([6, 3], struct.pack("<18f", *range(18))), metadata("pr_curves")))
            + frame_record(encode_event(2.0, 1, graph_def=b"\x0a\x03not-json")))
    (d / "events.out.tfevents.1.host").write_bytes(blob)
    s = _store(tmp_path)
    t = s.tags(["foreign"])
    assert t["layout"] == {} and "graphs" not in t["other"] and "hparams" not in t["other"]
    assert len(s.data("foreign", "pr_curves", "pr")["obj"]["precision"]) == 3
    assert s.hparams(["foreign"])["rows"] == [] and s.graph("foreign") is None
