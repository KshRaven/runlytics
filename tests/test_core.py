from runlytics.core import (CorruptRecord, decode_event, encode_event, frame_record, histogram_value, masked_crc,
                            parse_records, scalar_value, summary)
import pytest


def test_crc_is_deterministic_and_masked():
    assert masked_crc(b"abc") == masked_crc(b"abc")
    assert masked_crc(b"abc") != masked_crc(b"abd")


def test_record_roundtrip_and_partial_tail():
    blob = frame_record(b"one") + frame_record(b"two")
    spans, used = parse_records(blob + blob[:5])
    assert [blob[a:b] for a, b in spans] == [b"one", b"two"] and used == len(blob)


def test_corrupt_header_detected():
    bad = bytearray(frame_record(b"x"))
    bad[9] ^= 0xFF
    with pytest.raises(CorruptRecord):
        parse_records(bytes(bad))


def test_scalar_event_roundtrip():
    ev = decode_event(encode_event(12.5, 7, summary=summary(scalar_value("loss", 0.25))))
    assert (ev.wall, ev.step) == (12.5, 7)
    assert ev.values[0].tag == "loss" and ev.values[0].kind == "scalars"
    assert abs(ev.values[0].payload - 0.25) < 1e-7


def test_histogram_event_roundtrip():
    h = dict(min=0.0, max=2.0, num=3.0, sum=3.0, sum_squares=5.0, limits=[1.0, 2.0], counts=[1.0, 2.0])
    v = decode_event(encode_event(1.0, 0, summary=summary(histogram_value("h", h)))).values[0]
    assert v.tag == "h" and list(v.payload.counts) == [1.0, 2.0]
