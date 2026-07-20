# ADR-0003: Model-weight license policy — nothing non-commercial ships

- Status: accepted
- Date: 2026-07-20

## Context

Most single-image avatar research sits on non-commercial-licensed assets:
FLAME and SMPL-X (MPI/Meshcapade research licenses), CC BY-NC weights
(FlexAvatar, CAP4D), ambiguous ones (LHM's Apache-vs-CC-BY-NC dispute,
[aigc3d/LHM#175](https://github.com/aigc3d/LHM/issues/175)). img2person is
AGPL-3.0 and meant for unrestricted self-hosting; shipping or requiring
non-commercial weights would silently restrict every user.

## Decision

1. No model weights are committed to the repository, ever.
2. Every checkpoint the inference service can download has an entry in
   `services/inference/models/manifest.json` recording source URL, SHA-256,
   and license. `mock` mode is always weight-free.
3. A checkpoint is eligible only under a license verified to permit
   commercial use and redistribution (Apache-2.0, MIT, BSD, CC BY).
   Non-commercial or disputed licenses are excluded until resolved.
4. Prefer license-clean variants when they exist (e.g. LHM++ SMPLX-FREE over
   SMPL-X-dependent checkpoints).

## Consequences

- The `lhm` inference mode stays opt-in and downloads only manifest-listed,
  verified checkpoints.
- The long-term research track (training our own permissively-licensed prior
  on synthetic/open data) is the permanent fix; this policy is the interim
  guardrail.
- Local experimentation with non-commercial weights is possible but outside
  the project's license scope and never the default.
