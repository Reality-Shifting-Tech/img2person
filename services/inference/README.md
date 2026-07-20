# img2person-inference

Python inference service for img2person (ADR-0002): FastAPI, managed with
[uv](https://docs.astral.sh/uv/), Python >= 3.11. The TypeScript API reaches it
over HTTP only.

## Modes

- **`mock` (default)** — deterministic synthetic 3D Gaussian-splat avatar
  generated from the uploaded photo. No GPU, no model weights, no network.
  Seeded by the SHA-256 of the image bytes: the same photo always produces the
  same avatar and the same identity score. Used in dev, CI, and tests.
- **`lhm`** — real reconstruction via LHM++ (SMPLX-FREE checkpoint). Currently a
  documented stub: without weights + torch + a CUDA GPU the endpoint returns a
  `503` problem JSON. See below.

## Running

```bash
uv sync
uv run img2person-inference          # mock mode on :8000

IMG2PERSON_INFERENCE_MODE=lhm uv run img2person-inference
IMG2PERSON_INFERENCE_PORT=8001 uv run img2person-inference
```

Configuration is environment-driven (`src/img2person_inference/config.py`):

| Variable | Default | Values |
| --- | --- | --- |
| `IMG2PERSON_INFERENCE_MODE` | `mock` | `mock`, `lhm` |
| `IMG2PERSON_INFERENCE_PORT` | `8000` | 1–65535 |

Docker (mock mode by default):

```bash
docker build -t img2person-inference .
docker run -p 8000:8000 img2person-inference
```

## API

- `GET /health` → `{"status": "ok", "mode": "<mode>"}`
- `POST /v1/reconstruct` — multipart form field `image`. Returns the base64 PLY
  artifact, `identityScore`, per-region `confidence`, `mode`, and per-stage
  statuses. Errors are RFC 9457 problem JSON (`application/problem+json`):
  empty upload / non-image content type / corrupt image → `422`; lhm mode
  without weights → `503`.

## Enabling `lhm` mode (GPU)

The integration seam is `src/img2person_inference/lhm.py`. To make it real:

1. **Checkpoint.** The target is **LHM++ SMPLX-FREE**. The original LHM weights
   carry an unresolved Apache-vs-CC-BY-NC license dispute
   ([aigc3d/LHM#175](https://github.com/aigc3d/LHM/issues/175)), and the
   SMPL-X-dependent variants inherit the SMPL-X non-commercial research license
   — both are excluded by ADR-0003. The SMPLX-FREE variant removes the SMPL-X
   dependency; it becomes eligible once its license is verified to permit
   commercial use and redistribution.
2. **Register it** in `models/manifest.json` with `name`, `url`, `sha256`, and
   `license`, then fetch with `uv run python models/download.py <name>`. The
   downloader refuses anything not in the manifest or with an unverified
   license (`--list` shows what is registered; today: none).
3. **Hardware.** NVIDIA GPU with >= 8 GB VRAM, plus `torch` with CUDA (add it
   as an optional dependency when wiring this up; the base install stays
   CPU-only so dev and CI never pull CUDA wheels).
4. **Implement** `lhm.run_lhm(image_bytes)` to run inference and return the
   same `ReconstructionResult` shape the mock pipeline produces.

## License policy (ADR-0003 summary)

img2person is AGPL-3.0 and meant for unrestricted self-hosting. Therefore:

- No model weights are ever committed to this repository.
- Every downloadable checkpoint must be registered in `models/manifest.json`
  with source URL, SHA-256, and license.
- Only licenses verified to permit commercial use and redistribution
  (Apache-2.0, MIT, BSD, CC BY) are eligible; non-commercial or disputed
  licenses are excluded until resolved.
- `mock` mode is always weight-free.

## Development

```bash
uv sync                 # install incl. dev group
uv run pytest           # tests: no network, no GPU
uv run ruff check .     # lint
```

The PLY writer (`src/img2person_inference/ply.py`) emits the standard
binary-little-endian 3DGS layout (`x y z nx ny nz f_dc_* opacity scale_* rot_*`,
float32), readable by common Gaussian-splat viewers.
