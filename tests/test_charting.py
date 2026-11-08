import pytest

from runlytics.charting import lttb, make_histogram, rebin, tensor_to_histo
from runlytics.charting.image import encode_png, make_grid, to_nhwc, to_uint8


def test_lttb_keeps_endpoints_and_count():
    x = list(range(1000))
    y = [(i % 50) * 1.0 for i in x]
    idx = lttb(x, y, 100)
    assert len(idx) == 100 and idx[0] == 0 and idx[-1] == 999


def test_lttb_short_series_untouched():
    assert lttb([1, 2, 3], [1, 2, 3], 10) == [0, 1, 2]


def test_histogram_statistics():
    h = make_histogram([1.0, 2.0, 3.0, 4.0], bins=4)
    assert h["min"] == 1.0 and h["max"] == 4.0 and h["num"] == 4.0 and h["sum"] == 10.0
    assert sum(h["counts"]) == 4.0


def test_histogram_empty_raises():
    with pytest.raises(ValueError):
        make_histogram([])


def test_histogram_default_bins_cover_values():
    h = make_histogram([0.5, 1.5, 2.5])
    assert sum(h["counts"]) == 3.0 and len(h["limits"]) == len(h["counts"])


def test_png_encoding_signature():
    np = pytest.importorskip("numpy")
    a = to_uint8(to_nhwc(np.random.rand(3, 8, 8), "CHW"))
    assert encode_png(make_grid(a)[...])[:8] == b"\x89PNG\r\n\x1a\n"
