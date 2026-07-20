# AGENTS.md

Guidance for AI agents working in this repository. Human-facing contribution
rules live in [CONTRIBUTING.md](CONTRIBUTING.md); this file is the operational
quick-reference. Where the two overlap, CONTRIBUTING wins.

## What this is

img2person is an AGPL-3.0, self-hostable, single-photo → photoreal 3D avatar
platform. TypeScript ESM monorepo (pnpm 10 workspaces + Turbo) plus a Python
inference service (`uv`). Currently at milestone M1 ("first photoreal avatar") —
see `docs/adr/` for decisions.

## Toolchain

- Node >= 22 (`.nvmrc` pins 24), pnpm >= 10 (`packageManager: pnpm@10.10.0`).
- Python >= 3.11 with `uv` for `services/inference`.
- No GPU required for dev or tests: the inference service defaults to mock
  mode and `@img2person/testkit` provides a fake inference server.

## Commands

Run from the repo root unless noted.

```bash
pnpm install
pnpm build            # turbo run build (all packages/apps)
pnpm dev              # api on :3000, web on :5173
pnpm lint             # eslint . --max-warnings 0 (warnings fail)
pnpm format:check     # prettier --check .
pnpm typecheck        # turbo run typecheck
pnpm test             # turbo run test (vitest run per package)

cd services/inference && uv sync && uv run pytest   # Python service tests
cd services/inference && uv run img2person-inference # serve on :8000
```

Full pre-push gate: `pnpm lint && pnpm typecheck && pnpm test && pnpm build`.

Scoped work: `pnpm --filter @img2person/<name> <script>`; apps are filtered by
directory name (e.g. `pnpm --filter api`).

## Layout

```
apps/
  api/      Hono REST API under /v1: uploads, jobs, artifacts
  web/      Vite + React 19: upload UI, pipeline status, splat viewer
services/
  inference/  Python (uv, FastAPI): reconstruction + identity scoring
packages/
  config/     Zod-validated environment configuration, fail-fast
  contracts/  API conventions: RFC 9457 problem details, job/artifact types
  pipeline/   Job state machine and stage gates
  testkit/    Fake inference server, fixtures
vendor/
  img2threejs/  Vendored stylized-reconstruction track (MIT)
docs/adr/   architecture decision records
```

Dependency direction: apps depend on packages; `contracts` is the low-level
shared core. `services/inference` is a separate Python service reached over
HTTP — never import across the language boundary. Check an ADR before
reversing or adding edges.

## Conventions (enforced in review/CI)

- Conventional Commits: `<type>(<scope>): <imperative summary>`; types
  `feat|fix|chore|docs|refactor|test|ci|build|perf`, scope = package/app name.
  The changelog is generated from these messages.
- Strict TypeScript; `any` is banned by lint. Zero-warning lint policy.
- New behavior ships with tests. Unit tests are Vitest, must not require a
  GPU or live infrastructure — use `packages/testkit`.
- Every non-2xx API response uses the problem-details envelope from
  `@img2person/contracts`.
- Never ship or require non-commercial-licensed model weights (FLAME, SMPL-X,
  CC BY-NC, MPI). Every checkpoint needs a `manifest.json` entry — ADR-0003.
- Style bar is "edited, not generated": no narrating comments (comment the
  why or nothing), no dead code, no speculative abstractions beyond what the
  current milestone requires, reuse existing vocabulary.
- One logical change per PR; keep diffs reviewable (~400 lines of substance).

## Working agreement for agents

- Never commit or push unless explicitly asked.
- Photos of people are biometric-adjacent data: never upload fixtures or
  user photos to third-party services; tests use synthetic fixtures only.
