# img2person

> One photo in, photoreal 3D person out — open source and self-hostable.

![Status: early development](https://img.shields.io/badge/status-early%20development-orange)

img2person turns a single uploaded photo of a person into a downloadable,
animatable 3D avatar. It is the open-source answer to a market that lost Ready
Player Me (shut down January 2026) and CSM (acquired January 2026): photoreal,
identity-gated, and runnable on your own hardware.

The pipeline is quality-gated in the spirit of
[img2threejs](https://github.com/hoainho/img2threejs): every stage is checked,
and likeness is measured, not assumed. The web UI shows an identity-similarity
score and a per-stage status for every reconstruction.

## Honesty about limits

A single photo cannot show hidden sides — the back of a head is synthesized,
not captured. img2person reports per-region confidence and tells you when a
second view would help instead of faking certainty.

## Quickstart

Prerequisites: Node 24 (>= 22 works locally), pnpm 10, Python 3.11+ with
[uv](https://docs.astral.sh/uv/). No GPU is required for the default mock
inference mode; real reconstruction needs an NVIDIA GPU (>= 8 GB VRAM for
LHM++).

```bash
pnpm install
pnpm build

# Terminal 1 — inference service (mock mode by default)
cd services/inference && uv sync && uv run img2person-inference

# Terminal 2 — API on :3000
pnpm --filter api dev

# Terminal 3 — web on :5173
pnpm --filter web dev
```

Open http://localhost:5173, upload a photo, and watch the pipeline run. The
result page shows the avatar in a Gaussian-splat viewer with its identity
score, and offers the `.ply` artifact for download.

Real reconstruction mode (GPU): see
[services/inference/README.md](services/inference/README.md).

## Repository layout

```
apps/
  api/        Hono REST API under /v1: uploads, jobs, artifacts
  web/        Vite + React 19: upload UI, pipeline status, splat viewer
services/
  inference/  Python (uv, FastAPI): reconstruction models + identity scoring
packages/
  config/     Zod-validated environment configuration, fail-fast
  contracts/  API conventions: RFC 9457 problem details, job/artifact types
  pipeline/   Job state machine and stage gates
  testkit/    Fake inference server, fixtures — tests need no GPU or infra
vendor/
  img2threejs/  Vendored stylized-reconstruction track (MIT, see THIRD_PARTY_NOTICES)
docs/adr/     Architecture decision records
```

## Documentation

- [Architecture decision records](docs/adr/)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

## License

[AGPL-3.0](LICENSE). See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for
vendored components and model-weight licensing policy.
