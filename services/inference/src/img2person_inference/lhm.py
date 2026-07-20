"""LHM mode: real single-image reconstruction via LHM++ (SMPLX-FREE checkpoint).

Not implemented yet — this module is the integration seam. Per ADR-0002 the
`lhm` mode loads LHM++ when weights and a CUDA GPU are present; per ADR-0003
only manifest-listed, license-verified checkpoints are eligible (the original
LHM weights carry an Apache-vs-CC-BY-NC license dispute and are excluded, the
SMPLX-FREE variant drops the SMPL-X research-license dependency).

When wired up, `run_lhm` will:
1. Load the checkpoint named in `models/manifest.json` (fetched via
   `models/download.py`).
2. Run LHM++ inference on the decoded photo.
3. Return the same ReconstructionResult shape the mock pipeline produces,
   with a real PLY artifact and real identity/confidence scores.
"""

from img2person_inference.mock import ReconstructionResult

_UNAVAILABLE = (
    "lhm mode is not available: no LHM++ SMPLX-FREE checkpoint is registered in "
    "models/manifest.json, and torch/CUDA weights are not installed. "
    "See services/inference/README.md for how to enable lhm mode."
)


def run_lhm(image_bytes: bytes) -> ReconstructionResult:
    raise RuntimeError(_UNAVAILABLE)
