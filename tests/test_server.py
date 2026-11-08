import gzip
import urllib.request


def test_config_runs_tags(api):
    assert api("api/config")["title"] == "Runlytics"
    assert {r["name"] for r in api("api/runs")["runs"]} == {"run_a", "run_b"}
    tags = api("api/tags", run=["run_a"])
    assert "loss/train" in tags["scalars"] and tags["desc"]["scalars"]["loss/train"]


def test_scalars_endpoint_multi_run(api):
    d = api("api/scalars", tag="loss/train", run=["run_a", "run_b"], max_points=20)
    assert set(d) == {"run_a", "run_b"} and len(d["run_a"]["s"]) == 20


def test_histogram_and_media_endpoints(api):
    assert api("api/histograms", run="run_a", tag="weights/fc")["n"] == 10
    m = api("api/media", run="run_a", tag="notes", kind="text")
    assert m["n"] == 10 and "step" in m["rows"][0]["text"]


def test_unknown_route_and_bad_kind(api):
    for path, kw in (("api/nope", {}), ("api/data", {"kind": "x"})):
        try:
            api(path, **kw)
        except Exception as e:
            assert "40" in str(e)
        else:
            raise AssertionError("expected an HTTP error")


def test_static_assets_gzip_and_etag(api):
    req = urllib.request.Request(api.base + "static/js/main.js", headers={"Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req) as r:
        assert r.headers["Content-Encoding"] == "gzip" and b"renderTabs" in gzip.decompress(r.read())
        tag = r.headers["ETag"]
    req = urllib.request.Request(api.base + "static/js/main.js", headers={"If-None-Match": tag})
    try:
        urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        assert e.code == 304


def test_index_serves_title(api):
    with urllib.request.urlopen(api.base) as r:
        assert b"<title>Runlytics</title>" in r.read()
