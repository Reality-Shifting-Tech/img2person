"""Mock reconstruction pipeline: deterministic synthetic 3DGS avatar, no GPU, no weights."""

import base64
import hashlib
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
from PIL import Image

from img2person_inference import ply, scoring

MIN_DIMENSION_PX = 64
PERSON_HEIGHT = 1.7


class ReconstructionError(Exception):
    """Input rejected by the pipeline; mapped to a 422 problem response."""

    def __init__(self, detail: str, stage: str) -> None:
        super().__init__(detail)
        self.detail = detail
        self.stage = stage


@dataclass(frozen=True)
class ReconstructionResult:
    ply_bytes: bytes
    identity_score: float
    confidence: dict[str, float]
    stages: list[dict[str, str]]


def _dominant_colors(image: Image.Image) -> list[tuple[float, float, float]]:
    # Strip means: top of the frame tends to be hair, the middle the face, the
    # bottom clothing — a crude stand-in for the palette a real model would use.
    small = image.convert("RGB").resize((8, 8))
    pixels = np.asarray(small, dtype=np.float32) / 255.0
    strips = [pixels[0:2, :, :], pixels[3:5, :, :], pixels[6:8, :, :]]
    return [tuple(float(c) for c in strip.mean(axis=(0, 1))) for strip in strips]


def _cylinder(rng: np.random.Generator, count: int, rx: float, rz: float,
              y0: float, y1: float) -> npt.NDArray[np.float32]:
    t = rng.uniform(0.0, 2.0 * np.pi, count)
    r = np.sqrt(rng.uniform(0.0, 1.0, count))
    return np.stack([rx * r * np.cos(t), rng.uniform(y0, y1, count), rz * r * np.sin(t)],
                    axis=1).astype(np.float32)


def _sphere(rng: np.random.Generator, count: int, center: tuple[float, float, float],
            radius: float) -> npt.NDArray[np.float32]:
    t = rng.uniform(0.0, 2.0 * np.pi, count)
    z = rng.uniform(-1.0, 1.0, count)
    radial = radius * np.cbrt(rng.uniform(0.0, 1.0, count))
    xy = np.sqrt(1.0 - z**2)
    pts = np.stack([xy * np.cos(t), z, xy * np.sin(t)], axis=1) * radial[:, None]
    return (pts + np.array(center, dtype=np.float32)).astype(np.float32)


def _splat_person(rng: np.random.Generator,
                  palette: list[tuple[float, float, float]]) -> ply.SplatCloud:
    hair, face, clothes = palette
    counts = {
        "head": 4000, "hair": 1000, "torso": 8000,
        "arm_l": 2500, "arm_r": 2500, "leg_l": 3500, "leg_r": 3500,
    }
    head_center = (0.0, 1.55, 0.0)
    parts: list[tuple[str, npt.NDArray[np.float32], tuple[float, float, float], float]] = [
        ("head", _sphere(rng, counts["head"], head_center, 0.13), face, 0.020),
        # hair: upper shell of the head
        ("hair", _sphere(rng, counts["hair"], (0.0, 1.59, 0.0), 0.135), hair, 0.018),
        ("torso", _cylinder(rng, counts["torso"], 0.17, 0.11, 0.82, 1.42), clothes, 0.028),
        ("arm_l", _cylinder(rng, counts["arm_l"], 0.045, 0.045, 0.82, 1.40), clothes, 0.014),
        ("arm_r", _cylinder(rng, counts["arm_r"], 0.045, 0.045, 0.82, 1.40), clothes, 0.014),
        ("leg_l", _cylinder(rng, counts["leg_l"], 0.065, 0.055, 0.0, 0.82), clothes, 0.016),
        ("leg_r", _cylinder(rng, counts["leg_r"], 0.065, 0.055, 0.0, 0.82), clothes, 0.016),
    ]
    # shift arms and legs off the torso axis
    offsets = {"arm_l": -0.23, "arm_r": 0.23, "leg_l": -0.10, "leg_r": 0.10}
    positions_parts: list[npt.NDArray[np.float32]] = []
    colors_parts: list[npt.NDArray[np.float32]] = []
    radii_parts: list[npt.NDArray[np.float32]] = []
    for name, pts, color, radius in parts:
        if name in offsets:
            pts = pts + np.array([offsets[name], 0.0, 0.0], dtype=np.float32)
        n = pts.shape[0]
        jitter = rng.uniform(0.85, 1.15, (n, 3)).astype(np.float32)
        positions_parts.append(pts)
        colors_parts.append(np.tile(np.array(color, dtype=np.float32), (n, 1)) * jitter)
        radii_parts.append(np.full((n, 3), radius, dtype=np.float32) * jitter)
    return ply.SplatCloud(
        positions=np.concatenate(positions_parts, axis=0),
        colors=np.clip(np.concatenate(colors_parts, axis=0), 0.0, 1.0),
        radii=np.concatenate(radii_parts, axis=0),
    )


def _stage(stage: str, status: str, detail: str) -> dict[str, str]:
    return {"stage": stage, "status": status, "detail": detail}


def reconstruct(image_bytes: bytes, image: Image.Image) -> ReconstructionResult:
    stages: list[dict[str, str]] = []
    width, height = image.size
    if width < MIN_DIMENSION_PX or height < MIN_DIMENSION_PX:
        raise ReconstructionError(
            f"image too small: {width}x{height}px, minimum is "
            f"{MIN_DIMENSION_PX}x{MIN_DIMENSION_PX}px",
            stage="intake",
        )
    stages.append(
        _stage("intake", "passed", f"{width}x{height}px {image.format or 'image'} accepted")
    )

    image_hash = hashlib.sha256(image_bytes).digest()
    seed = int.from_bytes(image_hash[:8], "big")
    rng = np.random.default_rng(seed)
    palette = _dominant_colors(image)
    cloud = _splat_person(rng, palette)
    ply_bytes = ply.write_ply(cloud)
    stages.append(
        _stage(
            "reconstruction", "passed",
            f"synthetic 3DGS splat cloud, {cloud.positions.shape[0]} points",
        )
    )

    identity, confidence = scoring.score(image_hash)
    stages.append(
        _stage("identity-gate", "passed", f"identity score {identity} (mock gate always passes)")
    )

    return ReconstructionResult(
        ply_bytes=ply_bytes, identity_score=identity, confidence=confidence, stages=stages
    )


def response_payload(result: ReconstructionResult) -> dict[str, Any]:
    return {
        "artifact": {
            "format": "ply",
            "encoding": "base64",
            "data": base64.b64encode(result.ply_bytes).decode("ascii"),
        },
        "identityScore": result.identity_score,
        "confidence": result.confidence,
        "mode": "mock",
        "stages": result.stages,
    }
