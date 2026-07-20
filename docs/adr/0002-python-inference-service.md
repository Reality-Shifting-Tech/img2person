# ADR-0002: Python inference service behind an HTTP boundary

- Status: accepted
- Date: 2026-07-20

## Context

The state-of-the-art single-image avatar models we build on (LHM++/IDOL for
body, LAM-class for head) are PyTorch codebases. The monorepo is TypeScript.
Porting these models to TypeScript would be busywork with no upside, and
running them inside the API process would couple web-serving lifetimes to
GPU-model lifetimes.

## Decision

`services/inference` is a standalone Python service (FastAPI, managed with
`uv`). The TypeScript side reaches it over HTTP only, via the client contract
in `@img2person/contracts`. The service has two modes:

- `mock` (default): deterministic synthetic artifact generation, no GPU, no
  model weights — used in dev, CI, and tests.
- `lhm`: loads LHM++ (SMPLX-FREE checkpoint) when weights and a CUDA GPU are
  present.

## Consequences

- Dev and CI never need a GPU; `@img2person/testkit` fakes the HTTP boundary.
- Python code is excluded from the TypeScript lint/typecheck gates and has
  its own gate (`uv run pytest`, `ruff`).
- Real reconstruction requires self-hosters to run the inference service on a
  GPU host; this is documented as an operational requirement, not a dev one.
