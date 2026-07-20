# Contributing

Thanks for your interest in img2person. This document is the contract between
you and the maintainers; please read it before opening a pull request.

## Commit conventions

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<optional scope>): <imperative summary>
```

Types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `ci`, `build`,
`perf`. Scope is a package or app name when useful, e.g.
`feat(api): add avatar status endpoint`. The changelog is generated from these
messages, so write them for a reader, not for the diff.

## Pull requests

- One logical change per PR. Split refactors from features.
- Describe the _why_, not just the _what_; link issues and ADRs.
- Keep the diff reviewable. If a PR needs more than ~400 changed lines of
  substance, it probably needs to be split.
- All CI checks must be green: lint, typecheck, tests, build.

## Quality gates

- **Zero-warning policy.** `pnpm lint` runs with `--max-warnings 0`. A warning
  is a failed build, not a suggestion.
- **Types are non-negotiable.** Strict TypeScript everywhere; `any` is banned
  by lint. If you reach for a cast, expect to justify it in review.
- **Tests.** New behavior ships with tests. Unit tests use Vitest and must not
  require a GPU or live infrastructure; use `@img2person/testkit` (fake
  inference server, fixtures) instead of real model calls.

## Code style

The bar is _edited, not generated_. Code should read as if a senior engineer
wrote it deliberately:

- No comments that narrate what the code plainly does. Comment the _why_, or
  nothing.
- No dead code, unused exports, or speculative abstractions. Build what the
  milestone requires.
- Consistent naming within a module; prefer the existing vocabulary over
  introducing synonyms.
- Errors are part of the API. Use the problem-details envelope
  (`@img2person/contracts`) for every non-2xx response.

## Licensing rules

img2person is AGPL-3.0. Do not add dependencies or model weights under
non-commercial licenses (FLAME, SMPL-X, CC BY-NC, MPI research licenses).
Every model checkpoint must have an entry in `models/manifest.json` with a
verified license — see [ADR-0003](docs/adr/0003-license-policy.md).

## Development setup

See the [README quickstart](README.md#quickstart). Run the full gate before
pushing:

```bash
pnpm lint && pnpm typecheck && pnpm test && pnpm build
```
