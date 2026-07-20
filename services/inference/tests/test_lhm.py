"""LHM pipeline tests with injected fakes (no torch, no GPU, no network)."""

import base64
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from img2person_inference import lhm
from img2person_inference.config import Settings
from img2person_inference.mock import ReconstructionError, ReconstructionResult
from img2person_inference.server import create_app

PLY_BYTES = b"ply\nformat binary_little_endian 1.0\nfake\n"


def make_png(size: int = 128) -> bytes:
    img = Image.new("RGB", (size, size), (200, 120, 60))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_image(size: int = 128) -> Image.Image:
    img = Image.open(io.BytesIO(make_png(size)))
    img.load()
    return img


class FakePipeline:
    def __init__(self, front_view: Image.Image | None = None) -> None:
        self.front_view = front_view
        self.seen: list[Image.Image] = []

    def reconstruct(self, image: Image.Image) -> lhm.LhmArtifacts:
        self.seen.append(image)
        return lhm.LhmArtifacts(
            ply_bytes=PLY_BYTES, front_view=self.front_view, detail="fake reconstruction"
        )


def test_run_lhm_raises_without_torch() -> None:
    # CI/dev machines have no torch: the loader must fail as RuntimeError (-> 503).
    with pytest.raises(RuntimeError, match="README"):
        lhm.run_lhm(make_png())


def test_scored_reconstruction_passes_gate() -> None:
    image = make_image()
    result = lhm.reconstruct_with(image, FakePipeline(front_view=image), lambda _a, _b: 0.83)
    assert result.ply_bytes is PLY_BYTES  # artifact passthrough, no ply.py round-trip
    assert result.identity_score == 0.83
    assert result.confidence == {"front": 0.83, "profile": 0.0, "back": 0.0}
    assert [s["stage"] for s in result.stages] == ["intake", "reconstruction", "identity-gate"]
    assert all(s["status"] == "passed" for s in result.stages)
    assert "unmeasured" in result.stages[2]["detail"]


def test_gate_threshold_boundary() -> None:
    image = make_image()
    at = lhm.reconstruct_with(image, FakePipeline(image), lambda _a, _b: 0.5)
    assert at.stages[2]["status"] == "passed"
    below = lhm.reconstruct_with(image, FakePipeline(image), lambda _a, _b: 0.49)
    assert below.stages[2]["status"] == "failed"
    assert "below gate" in below.stages[2]["detail"]
    assert below.identity_score == 0.49


def test_unscored_when_no_front_view() -> None:
    result = lhm.reconstruct_with(make_image(), FakePipeline(front_view=None), lambda _a, _b: 0.9)
    assert result.identity_score is None
    assert result.confidence == {"front": 0.0, "profile": 0.0, "back": 0.0}
    gate = result.stages[2]
    assert gate["status"] == "passed"
    assert "unscored" in gate["detail"]


def test_unscored_when_scorer_missing_or_failing() -> None:
    image = make_image()
    no_scorer = lhm.reconstruct_with(image, FakePipeline(image), None)
    assert no_scorer.identity_score is None

    def boom(_a: Image.Image, _b: Image.Image) -> float:
        raise RuntimeError("no face detected")

    failing = lhm.reconstruct_with(image, FakePipeline(image), boom)
    assert failing.identity_score is None
    assert failing.stages[2]["status"] == "passed"  # scoring failure must not fail the request


def test_small_image_rejected() -> None:
    with pytest.raises(ReconstructionError) as excinfo:
        lhm.reconstruct_with(make_image(32), FakePipeline(), None)
    assert excinfo.value.stage == "intake"
    assert "too small" in excinfo.value.detail


def _lhm_client() -> TestClient:
    return TestClient(create_app(Settings(mode="lhm", port=8000)))


def test_server_503_when_pipeline_unavailable() -> None:
    c = _lhm_client()
    assert c.get("/health").json() == {"status": "ok", "mode": "lhm"}
    resp = c.post("/v1/reconstruct", files={"image": ("photo.png", make_png(), "image/png")})
    assert resp.status_code == 503
    assert resp.headers["content-type"] == "application/problem+json"
    assert "README" in resp.json()["detail"]


def test_server_success_omits_unavailable_identity_score(monkeypatch: pytest.MonkeyPatch) -> None:
    result = ReconstructionResult(
        ply_bytes=PLY_BYTES,
        identity_score=None,
        confidence={"front": 0.0, "profile": 0.0, "back": 0.0},
        stages=[
            {"stage": "intake", "status": "passed", "detail": "ok"},
            {"stage": "reconstruction", "status": "passed", "detail": "ok"},
            {"stage": "identity-gate", "status": "passed", "detail": "unscored"},
        ],
    )
    monkeypatch.setattr(lhm, "run_lhm", lambda _data: result)
    resp = _lhm_client().post(
        "/v1/reconstruct", files={"image": ("photo.png", make_png(), "image/png")}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "lhm"
    assert "identityScore" not in body
    assert base64.b64decode(body["artifact"]["data"]) == PLY_BYTES
    assert body["confidence"] == {"front": 0.0, "profile": 0.0, "back": 0.0}


def test_server_success_includes_identity_score(monkeypatch: pytest.MonkeyPatch) -> None:
    result = ReconstructionResult(
        ply_bytes=PLY_BYTES,
        identity_score=0.71,
        confidence={"front": 0.71, "profile": 0.0, "back": 0.0},
        stages=[{"stage": "intake", "status": "passed", "detail": "ok"}],
    )
    monkeypatch.setattr(lhm, "run_lhm", lambda _data: result)
    resp = _lhm_client().post(
        "/v1/reconstruct", files={"image": ("photo.png", make_png(), "image/png")}
    )
    assert resp.status_code == 200
    assert resp.json()["identityScore"] == 0.71


def test_server_intake_rejection_is_422(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(_data: bytes) -> ReconstructionResult:
        raise ReconstructionError("image too small: 32x32px", stage="intake")

    monkeypatch.setattr(lhm, "run_lhm", reject)
    resp = _lhm_client().post(
        "/v1/reconstruct", files={"image": ("photo.png", make_png(), "image/png")}
    )
    assert resp.status_code == 422
    assert resp.headers["content-type"] == "application/problem+json"
