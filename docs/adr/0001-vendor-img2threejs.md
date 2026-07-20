# ADR-0001: Vendor img2threejs as the stylized track, don't port it

- Status: accepted
- Date: 2026-07-20

## Context

[img2threejs](https://github.com/hoainho/img2threejs) is an agent skill:
pure-Python-stdlib scripts (`forge/`) plus rubric docs (`grimoire/`) that drive
a staged, quality-gated pipeline producing procedural Three.js models. Its
character track is explicitly stylized, not photoreal. img2person's
differentiator is photoreal output from a single photo, which requires learned
models, not procedural code generation.

## Decision

Vendor `forge/`, `grimoire/`, and `LICENSE` under `vendor/img2threejs/`
unchanged. Treat it as (a) the design basis for our stage-gate philosophy and
(b) a future stylized fallback track when photoreal reconstruction fails its
identity gate. Do not port the scripts to TypeScript.

## Consequences

- The MIT license is preserved in-place and credited in
  `THIRD_PARTY_NOTICES.md`.
- Vendored code is excluded from lint/format gates (`eslint.config.js`,
  `.prettierignore`).
- The staged pass-gate vocabulary (probe → assess → spec → gated passes →
  review) is reused in `packages/pipeline`.
