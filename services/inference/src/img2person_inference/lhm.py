"""LHM mode: real single-image reconstruction via LHM++ (LHMPP-700M-SMPLX-FREE).

The pipeline mirrors ``scripts/inference/to_gs_ply.py`` in
https://github.com/aigc3d/LHM-plusplus (verified 2026-07):

- Preprocess: BiRefNet matting (``engine/BiRefNet``) -> mask-guided center crop
  (``core.datasets.data_utils.src_center_crop_according_to_mask``) -> RGBA tensor.
- The SMPLX-FREE checkpoint sets ``use_pred_shape_for_render: true``, which makes
  ``scripts/inference/app_inference.parse_app_configs`` disable the SMPL-X shape
  estimator — no MultiHMR/Sapiens pose dependency at inference; the model's shape
  head predicts betas from the image.
- Reconstruct: ``infer_single_view`` -> ``inference_gs`` -> ``GaussianModel.save_ply``
  with a synthetic single-frame camera and canonical T-pose SMPL-X angles.
- Identity score: insightface ArcFace (buffalo_l) compares the input photo with a
  front view rendered from the reconstructed Gaussians. Best-effort only.

Caveat verified from upstream source: even the SMPLX-FREE checkpoint instantiates
SMPL-X template layers at load time (``core/models/rendering/skinnings/
base_skinning.py``), so ``pretrained_models/human_model_files`` (SMPL-X weights,
non-commercial research license) must be present. "SMPLX-FREE" drops the pose
estimator, not the SMPL-X template.

torch, CUDA and the vendored LHM++ checkout are imported lazily inside the loader
so this module stays importable (and testable) on CPU-only machines.
"""

import importlib
import importlib.util
import io
import os
import sys
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from PIL import Image

from img2person_inference.mock import (
    MIN_DIMENSION_PX,
    ReconstructionError,
    ReconstructionResult,
)

MODEL_NAME = "LHMPP-700M-SMPLX-FREE"
IDENTITY_GATE_THRESHOLD = 0.5

LHM_ROOT_ENV = "IMG2PERSON_LHM_ROOT"
CHECKPOINTS_ENV = "IMG2PERSON_LHM_CHECKPOINTS"

_SERVICE_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_LHM_ROOT = _SERVICE_ROOT / "vendor" / "LHM-plusplus"
_DEFAULT_CHECKPOINTS = _SERVICE_ROOT / "models" / "checkpoints"

_README_HINT = "See services/inference/README.md for how to enable lhm mode."

# Layout produced by models/download.py. LHM++ resolves ./pretrained_models
# relative to the process CWD, so the loader chdirs to the checkpoints dir.
_REQUIRED_CHECKPOINT_FILES = (
    "lhmpp-700m-smplx-free/model.safetensors",
    "lhmpp-700m-smplx-free/config.json",
    "pretrained_models/BiRefNet-general-epoch_244.pth",
    "pretrained_models/voxel_grid/voxel_192.pth",
    "pretrained_models/voxel_grid/cano_1_volume.npz",
    "pretrained_models/voxel_grid/human_prior_constrain.npz",
    "pretrained_models/dense_sample_points/1_160000.ply",
    "pretrained_models/human_model_files/smplx/SMPLX_NEUTRAL.npz",
    "pretrained_models/human_model_files/smplx/SMPLX_MALE.npz",
    "pretrained_models/human_model_files/smplx/SMPLX_FEMALE.npz",
)


@dataclass(frozen=True)
class LhmArtifacts:
    ply_bytes: bytes
    front_view: Image.Image | None  # rendered front view for identity scoring
    detail: str


class ReconstructionPipeline(Protocol):
    def reconstruct(self, image: Image.Image) -> LhmArtifacts: ...


IdentityScorer = Callable[[Image.Image, Image.Image], float]


def _stage(stage: str, status: str, detail: str) -> dict[str, str]:
    return {"stage": stage, "status": status, "detail": detail}


def _intake_stage(image: Image.Image) -> dict[str, str]:
    width, height = image.size
    if width < MIN_DIMENSION_PX or height < MIN_DIMENSION_PX:
        raise ReconstructionError(
            f"image too small: {width}x{height}px, minimum is "
            f"{MIN_DIMENSION_PX}x{MIN_DIMENSION_PX}px",
            stage="intake",
        )
    return _stage("intake", "passed", f"{width}x{height}px {image.format or 'image'} accepted")


def _identity_gate_stage(score: float | None) -> dict[str, str]:
    if score is None:
        return _stage(
            "identity-gate",
            "passed",
            "unscored: identity score unavailable (front render or insightface scorer "
            "missing); identityScore omitted, confidence fields report 0.0",
        )
    if score >= IDENTITY_GATE_THRESHOLD:
        return _stage(
            "identity-gate",
            "passed",
            f"identity score {score} >= gate {IDENTITY_GATE_THRESHOLD}; "
            "profile/back confidence unmeasured in lhm mode (0.0)",
        )
    return _stage(
        "identity-gate",
        "failed",
        f"identity score {score} below gate {IDENTITY_GATE_THRESHOLD}: reconstructed "
        "avatar does not match the input photo; profile/back confidence unmeasured (0.0)",
    )


def _confidence_for(score: float | None) -> dict[str, float]:
    # Only the front view is measurable in lhm mode (input photo vs rendered front
    # view). profile/back have no signal; 0.0 is reported honestly, never interpolated.
    return {"front": score if score is not None else 0.0, "profile": 0.0, "back": 0.0}


def reconstruct_with(
    image: Image.Image,
    pipeline: ReconstructionPipeline,
    scorer: IdentityScorer | None,
) -> ReconstructionResult:
    """Orchestrate intake -> reconstruction -> identity gate with injected components."""
    stages = [_intake_stage(image)]

    artifacts = pipeline.reconstruct(image)
    stages.append(_stage("reconstruction", "passed", artifacts.detail))

    score: float | None = None
    if artifacts.front_view is not None and scorer is not None:
        try:
            score = round(float(scorer(image, artifacts.front_view)), 4)
        except Exception:  # a scoring failure must not fail the reconstruction
            score = None
    stages.append(_identity_gate_stage(score))

    return ReconstructionResult(
        ply_bytes=artifacts.ply_bytes,
        identity_score=score,
        confidence=_confidence_for(score),
        stages=stages,
    )


# ---------------------------------------------------------------------------
# Lazy singletons (GPU model + identity scorer), loaded once per process.
# ---------------------------------------------------------------------------

_pipeline: ReconstructionPipeline | None = None
_scorer: IdentityScorer | None = None
_scorer_loaded = False
_load_lock = threading.Lock()


def _get_pipeline() -> ReconstructionPipeline:
    global _pipeline
    with _load_lock:
        if _pipeline is None:
            _pipeline = _load_pipeline()
        return _pipeline


def _get_scorer() -> IdentityScorer | None:
    global _scorer, _scorer_loaded
    with _load_lock:
        if not _scorer_loaded:
            _scorer = _load_scorer(_checkpoints_dir())
            _scorer_loaded = True
        return _scorer


def _checkpoints_dir() -> Path:
    return Path(os.environ.get(CHECKPOINTS_ENV, str(_DEFAULT_CHECKPOINTS)))


def run_lhm(image_bytes: bytes) -> ReconstructionResult:
    image = Image.open(io.BytesIO(image_bytes))
    image.load()
    return reconstruct_with(image, _get_pipeline(), _get_scorer())


# ---------------------------------------------------------------------------
# GPU loading — everything below imports torch / LHM++ lazily and never runs
# on CPU-only machines (dev, CI, tests).
# ---------------------------------------------------------------------------


def _load_pipeline() -> ReconstructionPipeline:
    try:
        torch = importlib.import_module("torch")
    except ImportError:
        raise RuntimeError(
            "lhm mode is not available: torch is not installed. Install the 'lhm' "
            f"extra (uv sync --extra lhm) on a CUDA host. {_README_HINT}"
        ) from None
    if not torch.cuda.is_available():
        raise RuntimeError(
            "lhm mode is not available: no CUDA GPU is visible "
            f"(LHMPP-700M needs >= 8 GB VRAM). {_README_HINT}"
        )

    root = Path(os.environ.get(LHM_ROOT_ENV, str(_DEFAULT_LHM_ROOT)))
    checkpoints = _checkpoints_dir()
    if not (root / "core").is_dir():
        raise RuntimeError(
            f"lhm mode is not available: LHM++ source checkout not found at {root} "
            f"(set {LHM_ROOT_ENV}). {_README_HINT}"
        )
    missing = [f for f in _REQUIRED_CHECKPOINT_FILES if not (checkpoints / f).is_file()]
    if missing:
        raise RuntimeError(
            "lhm mode is not available: missing checkpoints under "
            f"{checkpoints}: {', '.join(missing)}. Fetch them with "
            f"uv run python models/download.py <name>. {_README_HINT}"
        )
    return _LhmppPipeline.load(torch, root, checkpoints)


def _load_scorer(checkpoints: Path) -> IdentityScorer | None:
    """insightface ArcFace scorer, or None when unavailable (score is then omitted)."""
    try:
        from insightface.app import FaceAnalysis
    except ImportError:
        return None
    try:
        app = FaceAnalysis(name="buffalo_l", root=str(checkpoints / "insightface"))
        app.prepare(ctx_id=0, det_size=(640, 640))
    except Exception:
        return None

    def score(photo: Image.Image, render: Image.Image) -> float:
        emb_photo = _largest_face_embedding(app, photo)
        emb_render = _largest_face_embedding(app, render)
        if emb_photo is None or emb_render is None:
            raise RuntimeError("no face detected in photo or rendered front view")
        cosine = float(np.dot(emb_photo, emb_render))
        return max(0.0, min(1.0, (cosine + 1.0) / 2.0))

    return score


def _largest_face_embedding(app: Any, image: Image.Image) -> Any:
    import cv2  # local import: cv2 only exists with the lhm extra

    frame = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2BGR)
    faces = app.get(frame)
    if not faces:
        return None
    largest = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    return largest.normed_embedding


def _load_module_from_path(unique_name: str, path: Path) -> Any:
    """Load an LHM++ module by path; ``import scripts...`` would hit a PyPI shadow."""
    spec = importlib.util.spec_from_file_location(unique_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load LHM++ module from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _LhmppPipeline:
    """Live LHM++ pipeline. Constructed once; VRAM usage ~8 GB (upstream model card)."""

    def __init__(self, torch: Any, model: Any, cfg: Any, birefnet: Any, app_inference: Any) -> None:
        self._torch = torch
        self._model = model
        self._cfg = cfg
        self._birefnet = birefnet
        self._app_inference = app_inference
        self._device = "cuda"

    @classmethod
    def load(cls, torch: Any, root: Path, checkpoints: Path) -> "_LhmppPipeline":
        # engine/BiRefNet must precede root on sys.path: its scripts import
        # top-level ``utils`` / ``models`` modules local to that directory.
        for path in (root / "engine" / "BiRefNet", root):
            entry = str(path)
            if entry not in sys.path:
                sys.path.insert(0, entry)
        os.environ.setdefault("APP_ENABLED", "1")
        os.environ["APP_MODEL_NAME"] = MODEL_NAME
        os.environ.setdefault("APP_TYPE", "infer.human_lrm_a4o")
        os.environ.setdefault("NUMBA_THREADING_LAYER", "omp")
        # LHM++ hardcodes ./pretrained_models relative paths; config and checkpoint
        # paths below are absolute, so only the pretrained_models tree needs a CWD.
        os.chdir(checkpoints)

        from core.utils.model_card import MODEL_CONFIG  # type: ignore[import-not-found]

        app_inference = _load_module_from_path(
            "_lhmpp_app_inference", root / "scripts" / "inference" / "app_inference.py"
        )
        model_cards = {
            MODEL_NAME: {
                "model_path": str(checkpoints / "lhmpp-700m-smplx-free") + "/",
                "model_config": str(root / MODEL_CONFIG[MODEL_NAME]),
            }
        }
        cfg, _cfg_train = app_inference.parse_app_configs(model_cards)
        model = app_inference.build_app_model(cfg)
        model.to("cuda")
        model.eval()

        birefnet = cls._load_birefnet(torch, checkpoints)
        return cls(torch, model, cfg, birefnet, app_inference)

    @staticmethod
    def _load_birefnet(torch: Any, checkpoints: Path) -> Any:
        # Loading path as in engine/BiRefNet/inference_img.py.
        from models.birefnet import BiRefNet  # type: ignore[import-not-found]
        from utils import check_state_dict  # type: ignore[import-not-found]

        net = BiRefNet(bb_pretrained=False)
        state = torch.load(
            checkpoints / "pretrained_models" / "BiRefNet-general-epoch_244.pth",
            map_location="cpu",
        )
        net.load_state_dict(check_state_dict(state))
        net.to("cuda")
        net.eval()
        return net

    # -- per-request work ----------------------------------------------------

    def reconstruct(self, image: Image.Image) -> LhmArtifacts:
        torch = self._torch
        try:
            with torch.no_grad():
                ref_tensor = self._preprocess(image)
                motion_seq = _synthetic_motion_seq(torch, int(self._cfg.get("render_size", 420)))
                ply_bytes = self._export_ply(ref_tensor, motion_seq)
                front_view = self._render_front_view(ref_tensor, motion_seq)
            return LhmArtifacts(
                ply_bytes=ply_bytes,
                front_view=front_view,
                detail=f"{MODEL_NAME} canonical T-pose 3DGS PLY, {len(ply_bytes)} bytes",
            )
        finally:
            # Intermediates (features, gaussian lists) must not accumulate in VRAM.
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    def _preprocess(self, image: Image.Image) -> Any:
        torch = self._torch
        from core.datasets.data_utils import (  # type: ignore[import-not-found]
            src_center_crop_according_to_mask,
        )
        from torchvision import transforms  # type: ignore[import-not-found]

        rgb = image.convert("RGB")
        transform = transforms.Compose(
            [
                transforms.Resize((1024, 1024)),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]
        )
        preds = self._birefnet(transform(rgb).unsqueeze(0).to(self._device))[-1].sigmoid().cpu()
        mask = transforms.ToPILImage()(preds[0].squeeze()).resize(rgb.size)

        # Same call shape as core.utils.app_utils.obtain_ref_imgs_from_videos.
        cropped, crop_mask, *_ = src_center_crop_according_to_mask(
            np.asarray(rgb),
            np.asarray(mask, dtype=np.float32) / 255.0,
            aspect_standard=5.0 / 3,
            enlarge_ratio=[1.0, 1.0],
            head_bbox=None,
        )
        if cropped.shape[-1] == 3:  # model input is RGBA (mask in the alpha channel)
            alpha = (np.clip(crop_mask, 0.0, 1.0) * 255).astype(np.uint8)
            if alpha.shape[:2] != cropped.shape[:2]:
                alpha = np.asarray(
                    Image.fromarray(alpha).resize((cropped.shape[1], cropped.shape[0]))
                )
            cropped = np.concatenate([cropped, alpha[..., None]], axis=-1)
        tensor = torch.from_numpy(np.ascontiguousarray(cropped)).float() / 255.0
        return tensor.permute(2, 0, 1).unsqueeze(0).to(self._device)  # (1, C, H, W)

    def _export_ply(self, ref_tensor: Any, motion_seq: dict[str, Any]) -> bytes:
        """infer_single_view -> inference_gs -> save_ply, as in to_gs_ply.py."""
        torch = self._torch
        model = self._model
        dev = torch.device(self._device)

        motion_one = _slice_motion_seq_to_single_frame(torch, motion_seq, frame_idx=0)
        render_c2ws = motion_one["render_c2ws"].to(dev)
        render_intrs = motion_one["render_intrs"].to(dev)
        render_bg_colors = motion_one["render_bg_colors"].to(dev)
        smplx_dev = {k: v.to(dev) for k, v in motion_one["smplx_params"].items()}

        ref_batch = ref_tensor.unsqueeze(0)
        ref_mask = torch.ones(ref_tensor.shape[0], dtype=torch.bool, device=dev).unsqueeze(0)
        use_pred_render = getattr(model, "use_pred_shape_for_render", False)

        model_outputs = model.infer_single_view(
            ref_batch,
            None,
            None,
            render_c2ws=render_c2ws,
            render_intrs=render_intrs,
            render_bg_colors=render_bg_colors,
            smplx_params=smplx_dev,
            ref_imgs_bool=ref_mask,
            return_pred_shape=use_pred_render,
        )
        pred_shape = None
        if len(model_outputs) == 8:
            (
                gs_model_list,
                query_points,
                transform_mat_neutral_pose,
                gs_hidden_features,
                _image_feats,
                _motion_emb,
                _pos_emb,
                pred_shape,
            ) = model_outputs
        elif len(model_outputs) == 7:
            (
                gs_model_list,
                query_points,
                transform_mat_neutral_pose,
                gs_hidden_features,
                _image_feats,
                _motion_emb,
                _pos_emb,
            ) = model_outputs
        else:
            raise RuntimeError(f"unexpected infer_single_view outputs: {len(model_outputs)}")

        merged = type(model).smplx_params_with_pred_shape_betas(smplx_dev, pred_shape)
        gs_smplx = _build_tpose_smplx_params(
            torch, motion_one, transform_mat_neutral_pose, merged["betas"], dev
        )
        cano_gs = model.inference_gs(
            gs_model_list,
            query_points,
            gs_smplx,
            render_c2ws,
            render_intrs,
            render_bg_colors,
            gs_hidden_features,
            pad_forward=False,
        )
        # LHM++'s own exporter is the source of truth; do not round-trip ply.py.
        with tempfile.NamedTemporaryFile(suffix=".ply", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            cano_gs.save_ply(tmp_path)
            return Path(tmp_path).read_bytes()
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def _render_front_view(self, ref_tensor: Any, motion_seq: dict[str, Any]) -> Image.Image | None:
        """One gs_render frame from the synthetic front camera, for identity scoring."""
        try:
            frames = self._app_inference.inference_results(
                self._model,
                ref_tensor,
                motion_seq["smplx_params"],
                motion_seq,
                video_size=1,
                device=self._device,
                infer_output_renderer="gs",
            )
            return Image.fromarray(frames[0])
        except Exception:
            return None  # identity score becomes "unavailable" instead of failing


# ---------------------------------------------------------------------------
# Synthetic T-pose motion sequence — minimal ports of the helpers in
# scripts/inference/to_gs_ply.py (aigc3d/LHM-plusplus), same tensor shapes.
# ---------------------------------------------------------------------------


def _synthetic_motion_seq(torch: Any, render_res: int) -> dict[str, Any]:
    tgt_w = render_res
    tgt_h = int(round(render_res * 5.0 / 3.0))
    wf, hf = float(tgt_w), float(tgt_h)
    focal = max(wf, hf)

    zf = torch.float32
    frame: dict[str, Any] = {
        "betas": torch.zeros(10, dtype=zf),
        "root_pose": torch.zeros(3, dtype=zf),
        "body_pose": torch.zeros(21, 3, dtype=zf),
        "jaw_pose": torch.zeros(3, dtype=zf),
        "leye_pose": torch.zeros(3, dtype=zf),
        "reye_pose": torch.zeros(3, dtype=zf),
        "lhand_pose": torch.zeros(15, 3, dtype=zf),
        "rhand_pose": torch.zeros(15, 3, dtype=zf),
        "trans": torch.zeros(3, dtype=zf),
        "expr": torch.zeros(100, dtype=zf),
        "focal": torch.tensor([focal, focal], dtype=zf),
        "princpt": torch.tensor([wf / 2.0, hf / 2.0], dtype=zf),
        "img_size_wh": torch.tensor([wf, hf], dtype=zf),
    }
    intrinsic = torch.eye(4)
    intrinsic[0, 0] = frame["focal"][0]
    intrinsic[1, 1] = frame["focal"][1]
    intrinsic[0, 2] = frame["princpt"][0]
    intrinsic[1, 2] = frame["princpt"][1]
    intrinsic = intrinsic.float()
    c2w = torch.eye(4).float()

    smplx_params = {k: torch.stack([v]) for k, v in frame.items()}
    smplx_params["betas"] = frame["betas"]
    for k in smplx_params:
        smplx_params[k] = smplx_params[k].unsqueeze(0)
    return {
        "render_c2ws": c2w.unsqueeze(0).unsqueeze(0),
        "render_intrs": intrinsic.unsqueeze(0).unsqueeze(0),
        "render_bg_colors": torch.tensor([1.0], dtype=zf).unsqueeze(-1).repeat(1, 3).unsqueeze(0),
        "smplx_params": smplx_params,
        "rgbs": [],
        "vis_motion_render": None,
        "offset_list": [[1.0, 1.0, 0.0, 0.0]],
        "ori_size": (tgt_h, tgt_w),
        "motion_seqs": [],
    }


def _slice_motion_seq_to_single_frame(
    torch: Any, motion_seq: dict[str, Any], frame_idx: int
) -> dict[str, Any]:
    del torch
    out = dict(motion_seq)
    sl = slice(frame_idx, frame_idx + 1)
    out["render_c2ws"] = motion_seq["render_c2ws"][:, sl]
    out["render_intrs"] = motion_seq["render_intrs"][:, sl]
    out["render_bg_colors"] = motion_seq["render_bg_colors"][:, sl]
    out["smplx_params"] = {k: v.clone() for k, v in motion_seq["smplx_params"].items()}
    return out


def _build_tpose_smplx_params(
    torch: Any,
    motion_one: dict[str, Any],
    transform_mat_neutral_pose: Any,
    merged_betas: Any,
    device: Any,
) -> dict[str, Any]:
    dtype = merged_betas.dtype
    sp = {k: v.to(device=device, dtype=dtype) for k, v in motion_one["smplx_params"].items()}
    sp["betas"] = merged_betas.to(device=device, dtype=dtype)
    sp["transform_mat_neutral_pose"] = transform_mat_neutral_pose.to(device=device, dtype=dtype)

    z31 = torch.zeros(1, 1, 3, device=device, dtype=dtype)
    z_hand = torch.zeros(1, 1, 15, 3, device=device, dtype=dtype)
    body_pose = torch.zeros(1, 1, 21, 3, device=device, dtype=dtype)
    # Canonical leg/hand tweaks, same as BaseGSRender._prepare_smplx_data.
    import math

    body_pose[0, 0, 0, -1] = math.pi / 12
    body_pose[0, 0, 1, -1] = -math.pi / 12
    body_pose[0, 0, 15, -1] = -math.pi / 6
    body_pose[0, 0, 16, -1] = math.pi / 6

    sp["root_pose"] = z31
    sp["body_pose"] = body_pose
    sp["jaw_pose"] = z31
    sp["leye_pose"] = z31
    sp["reye_pose"] = z31
    sp["lhand_pose"] = z_hand
    sp["rhand_pose"] = z_hand
    sp["trans"] = z31
    sp["expr"] = torch.zeros(1, 1, sp["expr"].shape[-1], device=device, dtype=dtype)
    return sp
