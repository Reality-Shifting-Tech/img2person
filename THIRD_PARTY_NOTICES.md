# Third-Party Notices

## Vendored components

### img2threejs (`vendor/img2threejs/`)

- Source: https://github.com/hoainho/img2threejs
- License: MIT (see `vendor/img2threejs/LICENSE`)
- Used as the stylized, code-only reconstruction track and as the design
  basis for the quality-gated pipeline (stage gates, comparison review).

## Model weights

Model checkpoints are never committed to this repository. They are downloaded
by the scripts in `services/inference/models/` and each has a verified license
entry in `services/inference/models/manifest.json` (see
[ADR-0003](docs/adr/0003-license-policy.md)).

Non-commercial-licensed models (FLAME, SMPL-X, CC BY-NC weights, MPI research
licenses) must not be shipped, required, or downloaded by default. Local
experimentation with such weights is permitted but is outside the support and
license scope of this project.
