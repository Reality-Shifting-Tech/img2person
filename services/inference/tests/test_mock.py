"""Mock pipeline tests."""

import io
import json

import pytest
from PIL import Image

from img2person_inference import mock


def make_png(width: int = 128, height: int = 128, top: tuple = (30, 20, 15),
             mid: tuple = (220, 180, 150), bottom: tuple = (20, 60, 120)) -> bytes:
    img = Image.new("RGB", (width, height))
    px = img.load()
    assert px is not None
    for y in range(height):
        color = top if y < height // 3 else (mid if y < 2 * height // 3 else bottom)
        for x in range(width):
            px[x, y] = color
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def open_png(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img.load()
    return img


def test_reconstruct_shape_and_determinism() -> None:
    data = make_png()
    r1 = mock.reconstruct(data, open_png(data))
    r2 = mock.reconstruct(data, open_png(data))
    assert r1.ply_bytes == r2.ply_bytes
    assert r1.identity_score == r2.identity_score
    assert 0.82 <= r1.identity_score <= 0.94
    assert 0.85 <= r1.confidence["front"] <= 0.95
    assert 0.55 <= r1.confidence["profile"] <= 0.70
    assert 0.30 <= r1.confidence["back"] <= 0.45
    assert [s["stage"] for s in r1.stages] == ["intake", "reconstruction", "identity-gate"]
    assert all(s["status"] == "passed" for s in r1.stages)

    # point count in the 20k-30k range, declared in the PLY header
    count = int(r1.ply_bytes.split(b"element vertex ")[1].split(b"\n")[0])
    assert 20_000 <= count <= 30_000


def test_person_bounds() -> None:
    import struct

    data = make_png()
    result = mock.reconstruct(data, open_png(data))
    header_end = result.ply_bytes.index(b"end_header\n") + len(b"end_header\n")
    count = int(result.ply_bytes.split(b"element vertex ")[1].split(b"\n")[0])
    floats = struct.unpack_from(f"<{count * 17}f", result.ply_bytes, header_end)
    ys = floats[1::17]
    assert min(ys) >= -0.1
    assert max(ys) <= 1.75
    assert max(ys) > 1.5  # head reaches the top


def test_different_images_different_palette() -> None:
    a = mock.reconstruct(make_png(), open_png(make_png()))
    b = mock.reconstruct(
        make_png(top=(200, 200, 30), mid=(120, 90, 70), bottom=(180, 20, 20)),
        open_png(make_png(top=(200, 200, 30), mid=(120, 90, 70), bottom=(180, 20, 20))),
    )
    assert a.ply_bytes != b.ply_bytes
    # palette bytes differ: f_dc values (bytes 24..36 of the first vertex) change
    h_end = a.ply_bytes.index(b"end_header\n") + len(b"end_header\n")
    assert a.ply_bytes[h_end + 24:h_end + 36] != b.ply_bytes[h_end + 24:h_end + 36]


def test_small_image_rejected() -> None:
    data = make_png(32, 32)
    with pytest.raises(mock.ReconstructionError) as excinfo:
        mock.reconstruct(data, open_png(data))
    assert excinfo.value.stage == "intake"
    assert "too small" in excinfo.value.detail


def test_response_payload_shape() -> None:
    data = make_png()
    payload = mock.response_payload(mock.reconstruct(data, open_png(data)))
    assert payload["mode"] == "mock"
    assert payload["artifact"]["format"] == "ply"
    assert payload["artifact"]["encoding"] == "base64"
    json.dumps(payload)  # must be JSON-serializable
