#!/usr/bin/env bash
# Bootstrap a fresh RunPod GPU pod into a running img2person lhm-mode
# inference service. Mirrors Dockerfile.cuda, but runs natively on the pod
# (linux/amd64 + CUDA) so no prebuilt registry image is needed.
#
# Expected environment:
#   IMG2PERSON_ACCEPT_DISPUTED=1   download disputed-license checkpoints too
#                                  (see models/manifest.json / ADR-0003)
# Pod requirements: pytorch/pytorch:2.3.0-cuda12.1-cudnn8-devel (or newer),
# >= 60 GB container disk, port 8000 exposed.
set -euo pipefail

WORKSPACE=/workspace
REPO_DIR="$WORKSPACE/img2person"
LHMPP_DIR="$WORKSPACE/LHM-plusplus"

curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

if [ ! -d "$REPO_DIR" ]; then
  git clone --depth 1 https://github.com/Reality-Shifting-Tech/img2person.git "$REPO_DIR"
fi
if [ ! -d "$LHMPP_DIR" ]; then
  git clone https://github.com/aigc3d/LHM-plusplus "$LHMPP_DIR"
  git -C "$LHMPP_DIR" submodule update --init --recursive
fi

cd "$REPO_DIR/services/inference"
uv sync --locked --no-dev --extra lhm

uv pip install --no-cache -r "$LHMPP_DIR/requirements.txt"
uv pip install --no-cache spconv-cu121
uv pip install --no-cache "git+https://github.com/facebookresearch/pytorch3d.git@v0.7.7"
uv pip install --no-cache "git+https://github.com/ashawkey/diff-gaussian-rasterization/"
uv pip install --no-cache "git+https://github.com/camenduru/simple-knn/"
uv pip install --no-cache "gsplat==1.4.0"
"$REPO_DIR/services/inference/.venv/bin/python" "$LHMPP_DIR/lib/pointops/setup.py" install

export IMG2PERSON_INFERENCE_MODE=lhm
export IMG2PERSON_INFERENCE_PORT=8000
export IMG2PERSON_LHM_ROOT="$LHMPP_DIR"
export IMG2PERSON_LHM_CHECKPOINTS="$REPO_DIR/services/inference/models/checkpoints"

uv run --no-sync python models/download.py birefnet-general
uv run --no-sync python models/download.py insightface-buffalo-l
if [ "${IMG2PERSON_ACCEPT_DISPUTED:-0}" = "1" ]; then
  uv run --no-sync python models/download.py lhmpp-700m-smplx-free \
    --accept-terms lhmpp-700m-smplx-free
  uv run --no-sync python models/download.py lhmpp-prior-voxel-grid \
    --accept-terms lhmpp-prior-voxel-grid
  uv run --no-sync python models/download.py lhmpp-prior-dense-sample-points \
    --accept-terms lhmpp-prior-dense-sample-points
  uv run --no-sync python models/download.py smplx-human-model-files \
    --accept-terms smplx-human-model-files
else
  echo "IMG2PERSON_ACCEPT_DISPUTED!=1: skipping disputed checkpoints (lhm mode will 503)"
fi

exec uv run --no-sync img2person-inference
