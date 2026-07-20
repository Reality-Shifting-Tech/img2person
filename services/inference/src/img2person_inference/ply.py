"""Binary 3D Gaussian-splat PLY writer.

Layout matches the standard used by 3DGS renderers and splat viewers:
float32 little-endian vertex records, properties in this exact order:
x y z nx ny nz f_dc_0 f_dc_1 f_dc_2 opacity scale_0 scale_1 scale_2 rot_0 rot_1 rot_2 rot_3
"""

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

SH_C0 = 0.28209
_FLOATS_PER_VERTEX = 17


@dataclass(frozen=True)
class SplatCloud:
    positions: npt.NDArray[np.float32]  # (N, 3)
    colors: npt.NDArray[np.float32]  # (N, 3), linear RGB in [0, 1]
    radii: npt.NDArray[np.float32]  # (N, 3), per-axis radius in world units


def _floats(cloud: SplatCloud) -> npt.NDArray[np.float32]:
    n = cloud.positions.shape[0]
    zeros = np.zeros((n, 3), dtype=np.float32)  # normals
    f_dc = (cloud.colors - 0.5) / SH_C0
    opacity = np.full((n, 1), -math.log(1.0 / 0.9 - 1.0), dtype=np.float32)  # sigmoid^-1(0.9)
    scales = np.log(cloud.radii)
    rot = np.zeros((n, 4), dtype=np.float32)
    rot[:, 3] = 1.0  # unit quaternion (x, y, z, w) = (0, 0, 0, 1)
    return np.concatenate([cloud.positions, zeros, f_dc, opacity, scales, rot], axis=1)


def write_ply(cloud: SplatCloud) -> bytes:
    n = cloud.positions.shape[0]
    props = ["x", "y", "z", "nx", "ny", "nz", "f_dc_0", "f_dc_1", "f_dc_2", "opacity"]
    props += [f"scale_{i}" for i in range(3)] + [f"rot_{i}" for i in range(4)]
    lines = [
        "ply",
        "format binary_little_endian 1.0",
        f"element vertex {n}",
    ]
    lines += [f"property float {p}" for p in props]
    lines.append("end_header")
    header = ("\n".join(lines) + "\n").encode("ascii")
    floats = _floats(cloud)
    assert floats.shape == (n, _FLOATS_PER_VERTEX)
    return header + floats.astype("<f4", copy=False).tobytes()
