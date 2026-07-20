"""Server tests via fastapi TestClient (no network, no GPU)."""

import base64
import io

from fastapi.testclient import TestClient
from PIL import Image

from img2person_inference.config import Settings
from img2person_inference.server import create_app


def make_png(size: int = 128, color: tuple = (200, 120, 60)) -> bytes:
    img = Image.new("RGB", (size, size), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def client(mode: str = "mock") -> TestClient:
    return TestClient(create_app(Settings(mode=mode, port=8000)))


def test_health() -> None:
    resp = client().get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "mode": "mock"}


def test_reconstruct_round_trip() -> None:
    resp = client().post(
        "/v1/reconstruct", files={"image": ("photo.png", make_png(), "image/png")}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "mock"
    assert body["artifact"]["format"] == "ply"
    assert body["artifact"]["encoding"] == "base64"
    assert base64.b64decode(body["artifact"]["data"]).startswith(b"ply\n")
    assert 0.82 <= body["identityScore"] <= 0.94
    assert set(body["confidence"]) == {"front", "profile", "back"}
    assert [s["stage"] for s in body["stages"]] == ["intake", "reconstruction", "identity-gate"]

    # determinism through the HTTP boundary
    resp2 = client().post(
        "/v1/reconstruct", files={"image": ("photo.png", make_png(), "image/png")}
    )
    assert resp2.json()["identityScore"] == body["identityScore"]
    assert resp2.json()["artifact"]["data"] == body["artifact"]["data"]


def test_empty_upload_422() -> None:
    resp = client().post("/v1/reconstruct", files={"image": ("empty.png", b"", "image/png")})
    assert resp.status_code == 422
    assert resp.headers["content-type"] == "application/problem+json"
    body = resp.json()
    assert body["type"] == "about:blank"
    assert body["status"] == 422
    assert "title" in body and "detail" in body


def test_non_image_content_type_422() -> None:
    resp = client().post(
        "/v1/reconstruct", files={"image": ("notes.txt", b"hello world", "text/plain")}
    )
    assert resp.status_code == 422
    assert resp.headers["content-type"] == "application/problem+json"


def test_corrupt_image_422() -> None:
    resp = client().post(
        "/v1/reconstruct", files={"image": ("bad.png", b"\x89PNG garbage", "image/png")}
    )
    assert resp.status_code == 422
    assert "readable image" in resp.json()["detail"]


def test_too_small_image_422() -> None:
    resp = client().post(
        "/v1/reconstruct", files={"image": ("tiny.png", make_png(32), "image/png")}
    )
    assert resp.status_code == 422
    assert "too small" in resp.json()["detail"]


def test_lhm_mode_503() -> None:
    c = client(mode="lhm")
    assert c.get("/health").json() == {"status": "ok", "mode": "lhm"}
    resp = c.post("/v1/reconstruct", files={"image": ("photo.png", make_png(), "image/png")})
    assert resp.status_code == 503
    assert resp.headers["content-type"] == "application/problem+json"
    body = resp.json()
    assert body["status"] == 503
    assert "README" in body["detail"]


def test_main_guarded() -> None:
    # importing server must not start uvicorn
    import img2person_inference.server as server

    assert callable(server.main)
