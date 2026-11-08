from runlytics.cli.args import build_parser, parse_samples, parse_specs, resolve_path
from runlytics.utils import LRUCache, safe_filename, sample_indices, unique_name


def test_parse_specs():
    assert parse_specs("a", "exp:/p,/q") == [(None, resolve_path("a")), ("exp", resolve_path("/p")), (None, resolve_path("/q"))]


def test_resolve_path_relative_to_cwd(tmp_path, monkeypatch):
    (tmp_path / "runs").mkdir()
    monkeypatch.chdir(tmp_path)
    assert resolve_path("") == str(tmp_path) and resolve_path("runs") == str(tmp_path / "runs")


def test_dev_flag_hidden_from_help():
    p = build_parser()
    assert p.parse_args(["--dev"]).dev and "--dev" not in p.format_help()


def test_parse_samples():
    assert parse_samples("scalars=10,bogus=3") == {"scalars": 10, "histograms": 50}


def test_parser_defaults():
    a = build_parser().parse_args(["--logdir", "d"])
    assert a.port == 6006 and a.reload_interval == 5.0


def test_lru_evicts_oldest():
    c = LRUCache(2)
    for k in "abc":
        c.get_or_compute(k, lambda k=k: k)
    assert len(c) == 2


def test_sample_indices_keeps_last():
    idx = sample_indices(5000, 100)
    assert len(idx) <= 100 and idx[-1] == 4999 and sample_indices(3, 10) == [0, 1, 2]


def test_naming():
    assert unique_name("a", {"a": 1}) != "a"
    assert "/" not in safe_filename("a/b")
