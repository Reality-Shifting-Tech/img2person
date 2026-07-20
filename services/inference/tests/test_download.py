"""download.py tests: license gating, acceptance markers, hash checks (no network)."""

import hashlib
import importlib.util
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

_DOWNLOAD_PY = Path(__file__).resolve().parents[1] / "models" / "download.py"
_spec = importlib.util.spec_from_file_location("img2person_download", _DOWNLOAD_PY)
assert _spec is not None and _spec.loader is not None
download = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = download
_spec.loader.exec_module(download)

CONTENT = b"fake-weights"
CONTENT_SHA = hashlib.sha256(CONTENT).hexdigest()


@pytest.fixture
def manifest_path(tmp_path: Path) -> Path:
    manifest = {
        "checkpoints": [
            {
                "name": "verified-thing",
                "dest": "verified",
                "license": "MIT",
                "licenseStatus": "verified",
                "files": [{"path": "w.bin", "url": "https://x.test/w.bin", "sha256": CONTENT_SHA}],
            },
            {
                "name": "disputed-thing",
                "dest": "disputed",
                "license": "Apache-2.0",
                "licenseStatus": "disputed",
                "dispute": "HF tag Apache-2.0 vs repo CC BY-NC (upstream issue #175).",
                "files": [{"path": "w.bin", "url": "https://x.test/d.bin", "sha256": CONTENT_SHA}],
            },
            {
                "name": "zip-thing",
                "dest": "zipped",
                "license": "MIT",
                "licenseStatus": "verified",
                "files": [
                    {"path": "pack.zip", "url": "https://x.test/pack.zip", "sha256": None,
                     "unpack": "zip"}
                ],
            },
        ]
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


@pytest.fixture
def fetcher() -> download.Fetcher:
    def fake(url: str, dest: Path) -> None:
        if url.endswith("pack.zip"):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr("pack/inner.onnx", b"onnx-bytes")
            dest.write_bytes(buf.getvalue())
        else:
            dest.write_bytes(CONTENT)

    return fake


def run(args: list[str], manifest_path: Path, tmp_path: Path, fetcher: download.Fetcher) -> int:
    return download.main(
        args, manifest_path=manifest_path, checkpoints_dir=tmp_path / "ckpt", fetcher=fetcher
    )


def test_verified_download_allowed(manifest_path: Path, tmp_path: Path, fetcher) -> None:
    assert run(["verified-thing"], manifest_path, tmp_path, fetcher) == 0
    assert (tmp_path / "ckpt" / "verified" / "w.bin").read_bytes() == CONTENT


def test_sha_mismatch_refused(manifest_path: Path, tmp_path: Path) -> None:
    def bad_fetcher(_url: str, dest: Path) -> None:
        dest.write_bytes(b"tampered")

    assert run(["verified-thing"], manifest_path, tmp_path, bad_fetcher) == 1
    assert not (tmp_path / "ckpt" / "verified" / "w.bin").exists()


def test_disputed_requires_accept_terms(
    manifest_path: Path, tmp_path: Path, fetcher, capsys: pytest.CaptureFixture
) -> None:
    assert run(["disputed-thing"], manifest_path, tmp_path, fetcher) == 1
    assert not (tmp_path / "ckpt" / "disputed" / "w.bin").exists()
    assert "dispute" in capsys.readouterr().out  # dispute text is printed

    assert run(
        ["disputed-thing", "--accept-terms", "disputed-thing"], manifest_path, tmp_path, fetcher
    ) == 0
    marker = tmp_path / "ckpt" / ".accepted-disputed-thing.json"
    assert marker.exists()
    recorded = json.loads(marker.read_text(encoding="utf-8"))
    assert recorded["licenseStatus"] == "disputed"
    assert "acceptedAt" in recorded

    # marker on disk: no flag needed on later runs
    assert run(["disputed-thing"], manifest_path, tmp_path, fetcher) == 0


def test_unknown_name_refused(manifest_path: Path, tmp_path: Path, fetcher) -> None:
    assert run(["nope"], manifest_path, tmp_path, fetcher) == 1
    assert run(["verified-thing", "--accept-terms", "nope"], manifest_path, tmp_path, fetcher) == 1


def test_list_shows_license_status(
    manifest_path: Path, tmp_path: Path, fetcher, capsys: pytest.CaptureFixture
) -> None:
    assert run(["--list"], manifest_path, tmp_path, fetcher) == 0
    out = capsys.readouterr().out
    assert "verified-thing\tverified\tMIT" in out
    assert "disputed-thing\tdisputed\tApache-2.0" in out


def test_zip_unpack(manifest_path: Path, tmp_path: Path, fetcher) -> None:
    assert run(["zip-thing"], manifest_path, tmp_path, fetcher) == 0
    assert (tmp_path / "ckpt" / "zipped" / "pack" / "inner.onnx").read_bytes() == b"onnx-bytes"
    assert not (tmp_path / "ckpt" / "zipped" / "pack.zip").exists()


def test_all_skips_disputed_without_acceptance(
    manifest_path: Path, tmp_path: Path, fetcher
) -> None:
    assert run(["--all"], manifest_path, tmp_path, fetcher) == 1
    assert (tmp_path / "ckpt" / "verified" / "w.bin").exists()
    assert not (tmp_path / "ckpt" / "disputed" / "w.bin").exists()
