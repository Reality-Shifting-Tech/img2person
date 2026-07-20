"""PLY writer tests: header layout, binary round-trip, determinism, f_dc math."""

import math
import struct

import numpy as np

from img2person_inference import ply


def _cloud(n: int = 3) -> ply.SplatCloud:
    return ply.SplatCloud(
        positions=np.array([[0.0, 1.0, 0.0], [1.0, 0.0, -1.0], [0.5, 0.5, 0.5]], dtype=np.float32),
        colors=np.tile(np.array([[0.8, 0.5, 0.3]], dtype=np.float32), (n, 1)),
        radii=np.full((n, 3), 0.02, dtype=np.float32),
    )


def _parse_header(blob: bytes) -> tuple[list[str], int]:
    end = blob.index(b"end_header\n") + len(b"end_header\n")
    lines = blob[:end].decode("ascii").splitlines()
    return lines, end


def test_header_layout() -> None:
    blob = ply.write_ply(_cloud())
    lines, _ = _parse_header(blob)
    assert lines[0] == "ply"
    assert lines[1] == "format binary_little_endian 1.0"
    assert lines[2] == "element vertex 3"
    props = [line.removeprefix("property float ") for line in lines[3:-1]]
    assert props == [
        "x", "y", "z", "nx", "ny", "nz", "f_dc_0", "f_dc_1", "f_dc_2", "opacity",
        "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3",
    ]


def test_first_vertex_bytes() -> None:
    blob = ply.write_ply(_cloud())
    _, offset = _parse_header(blob)
    floats = struct.unpack_from("<17f", blob, offset)
    assert floats[0:3] == (0.0, 1.0, 0.0)
    assert floats[3:6] == (0.0, 0.0, 0.0)  # normals
    expected_dc = [(c - 0.5) / ply.SH_C0 for c in (0.8, 0.5, 0.3)]
    assert np.allclose(floats[6:9], expected_dc, atol=1e-5)
    assert math.isclose(floats[9], 2.1972246, rel_tol=1e-5)  # sigmoid^-1(0.9)
    assert np.allclose(floats[10:13], [math.log(0.02)] * 3, atol=1e-6)
    assert floats[13:17] == (0.0, 0.0, 0.0, 1.0)  # unit quaternion
    # total size: header + N * 17 float32
    assert len(blob) == offset + 3 * 17 * 4


def test_determinism() -> None:
    assert ply.write_ply(_cloud()) == ply.write_ply(_cloud())


def test_f_dc_round_trip() -> None:
    blob = ply.write_ply(_cloud())
    _, offset = _parse_header(blob)
    floats = struct.unpack_from("<17f", blob, offset)
    recovered = [f * ply.SH_C0 + 0.5 for f in floats[6:9]]
    assert np.allclose(recovered, [0.8, 0.5, 0.3], atol=1e-5)
