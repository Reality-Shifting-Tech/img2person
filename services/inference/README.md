# img2person-inference

Python inference service for img2person (ADR-0002): FastAPI, managed with
[uv](https://docs.astral.sh/uv/), Python >= 3.11. The TypeScript API reaches it
over HTTP only.

## Modes

- **`mock` (default)** — deterministic synthetic 3D Gaussian-splat avatar
  generated from the uploaded photo. No GPU, no model weights, no network.
  Seeded by the SHA-256 of the image bytes: the same photo always produces the
  same avatar and the same identity score. Used in dev, CI, and tests.
- **`lhm`** — real reconstruction via **LHM++** (`LHMPP-700M-SMPLX-FREE`,
  [aigc3d/LHM-plusplus](https://github.com/aigc3d/LHM-plusplus)): BiRefNet
  matting → mask-guided center crop → `infer_single_view` → `inference_gs` →
  canonical T-pose 3DGS `.ply`. Requires an NVIDIA GPU (>= 8 GB VRAM), torch
  with CUDA, the LHM++ source checkout, and downloaded checkpoints. Without any
  of these the endpoint returns a `503` problem JSON.

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
| `IMG2PERSON_LHM_ROOT` | `vendor/LHM-plusplus` | path to the LHM++ checkout |
| `IMG2PERSON_LHM_CHECKPOINTS` | `models/checkpoints` | checkpoint root |

Docker (mock mode by default):

```bash
docker build -t img2person-inference .
docker run -p 8000:8000 img2person-inference
```

## API

- `GET /health` → `{"status": "ok", "mode": "<mode>"}`
- `POST /v1/reconstruct` — multipart form field `image`. Returns the base64 PLY
  artifact, per-region `confidence`, `mode`, and per-stage statuses.
  `identityScore` is present when a score was computed (always in mock mode) and
  omitted when no real score could be produced (lhm mode without a usable
  insightface scorer or front render — the `identity-gate` stage then reports
  `unscored`). Errors are RFC 9457 problem JSON
  (`application/problem+json`): empty upload / non-image content type /
  corrupt image / too-small image → `422`; lhm mode without weights → `503`.

## Enabling `lhm` mode (GPU)

1. **Dependencies.** `uv sync --extra lhm` installs torch 2.3.0 (cu121 on
   Linux via the PyTorch index), insightface, and the other runtime deps. The
   base install stays CPU-only, so dev and CI never pull CUDA wheels.
2. **LHM++ source.** The upstream repo is not pip-installable (custom CUDA
   extensions); clone it and point `IMG2PERSON_LHM_ROOT` at it (or use
   `Dockerfile.cuda`, which does this for you):

   ```bash
   git clone https://github.com/aigc3d/LHM-plusplus vendor/LHM-plusplus
   ```

   Inference requirements verified from the upstream source (2026-07):
   - The SMPLX-FREE checkpoint sets `use_pred_shape_for_render: true`, which
     disables the SMPL-X shape/pose estimator
     (`scripts/inference/app_inference.py`) — **no MultiHMR/Sapiens pose
     dependency at inference**; the model's shape head predicts betas.
   - The renderer still instantiates SMPL-X template layers at load time
     (`core/models/rendering/skinnings/base_skinning.py`), so
     `human_model_files` (SMPL-X weights, non-commercial research license) is
     required. "SMPLX-FREE" drops the pose estimator, not the SMPL-X template.
   - LHM++ resolves `./pretrained_models` relative to the process CWD; the
     loader chdirs to the checkpoints dir to satisfy this.
3. **Checkpoints.** All entries live in `models/manifest.json` with URL,
   SHA-256, license, and license status (ADR-0003). Download into
   `models/checkpoints/` (gitignored):

   ```bash
   uv run python models/download.py --list          # names + license status
   uv run python models/download.py birefnet-general
   uv run python models/download.py insightface-buffalo-l
   # disputed entries print the dispute and refuse without explicit acceptance:
   uv run python models/download.py lhmpp-700m-smplx-free --accept-terms lhmpp-700m-smplx-free
   uv run python models/download.py lhmpp-prior-voxel-grid --accept-terms lhmpp-prior-voxel-grid
   uv run python models/download.py lhmpp-prior-dense-sample-points --accept-terms lhmpp-prior-dense-sample-points
   uv run python models/download.py smplx-human-model-files --accept-terms smplx-human-model-files
   ```

   `--accept-terms` prints the dispute text and writes a marker file
   (`models/checkpoints/.accepted-<name>.json`); later runs need no flag.
   Disputed means: the LHM family's unresolved Apache-2.0-vs-CC-BY-NC conflict
   ([aigc3d/LHM#175](https://github.com/aigc3d/LHM/issues/175)) for the LHM++
   weights, and the MPI non-commercial SMPL-X license for the template files.
4. **Hardware.** NVIDIA GPU with >= 8 GB VRAM (upstream model card: RTX
   4090 / L4 class). The model loads once and is reused across requests;
   intermediates are freed after each request.

### Dockerfile.cuda

```bash
docker build -f Dockerfile.cuda -t img2person-inference:lhm .
docker run --gpus all -p 8000:8000 \
  -e IMG2PERSON_ACCEPT_DISPUTED=1 \
  -v lhm-checkpoints:/app/models/checkpoints \
  img2person-inference:lhm
```

Checkpoints download at container start via `models/download.py` (never baked
into the image). `IMG2PERSON_ACCEPT_DISPUTED=1` passes `--accept-terms` for
each disputed entry; without it only license-verified checkpoints download and
lhm mode stays at 503. The image is **not built in CI** (no CUDA on CI); treat
the recipe as validated-on-first-GPU-run.

### RunPod quickstart

- Template: PyTorch 2.3 / CUDA 12.1, GPU RTX 4090 or L4 (>= 8 GB VRAM),
  >= 30 GB volume for checkpoints.
- Image: build and push `img2person-inference:lhm` (above), set it as the pod
  image, add env `IMG2PERSON_ACCEPT_DISPUTED=1` (after reading the dispute
  texts via `download.py --list` / manifest) and mount a network volume at
  `/app/models/checkpoints` so pods skip re-downloading ~12 GB.
- Expose TCP port `8000`, or keep the pod private and tunnel:
  `ssh -L 8000:localhost:8000 root@<pod-host> -p <pod-ssh-port>`.
- Cost: RTX 4090-class pods run about **$0.34/hr**; inference itself is
  ~1 s/photo, so a single pod handles bursts fine.

### Modal note

The same image works on [Modal](https://modal.com): define a `modal.Image`
from the Dockerfile.cuda recipe, attach a `modal.Volume` at
`/app/models/checkpoints`, request `gpu="L4"` (or `T4` for lower cost at higher
latency), and use `min_containers=0` for scale-to-zero — you pay only while
reconstructing, at similar per-second GPU rates. Warm the volume once by
running the download commands above inside the image.

### Privacy reminder

Uploaded photos transit the GPU host (RunPod/Modal/your box) and are processed
in memory there. They are never written to disk by the service, but the host
operator can observe them — pick a provider you are comfortable with and say
so in the product's privacy notes.

## License policy (ADR-0003 summary)

img2person is AGPL-3.0 and meant for unrestricted self-hosting. Therefore:

- No model weights are ever committed to this repository.
- Every downloadable checkpoint must be registered in `models/manifest.json`
  with source URL, SHA-256 (when programmatically verifiable), and license.
- `verified` licenses permit commercial use and redistribution (Apache-2.0,
  MIT, BSD, CC BY). `disputed` entries download only after explicit
  `--accept-terms` acceptance, which is recorded on disk.
- `mock` mode is always weight-free.

## Development

```bash
uv sync                 # install incl. dev group (no torch, no GPU needed)
uv run pytest           # tests: no network, no GPU
uv run ruff check .     # lint
```

The PLY writer (`src/img2person_inference/ply.py`) emits the standard
binary-little-endian 3DGS layout (`x y z nx ny nz f_dc_* opacity scale_* rot_*`,
float32), readable by common Gaussian-splat viewers. It is used by mock mode
only — lhm mode returns LHM++'s own `save_ply` output untouched.
