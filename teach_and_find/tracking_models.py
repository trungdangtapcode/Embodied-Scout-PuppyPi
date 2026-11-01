"""Verified original SAM 2.1 and Cutie adapters, imported only by the worker."""

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

from teach_and_find.storage import AssistantError

REVISIONS = {
    "sam2": "2b90b9f5ceec907a1c18123530e92e794ad901a4",
    "cutie": "ec5cdd4cf16f75c73ad785a2f96fb97dbad4125a",
}
WEIGHTS = {
    "sam2.1_hiera_tiny.pt": "7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69",
    "cutie-base-mega.pth": "9c05402ee36d3a356fb72715d263ba7e1ea06ad3bada48c1306491792da43023",
    "backbones/resnet18-5c106cde.pth": "5c106cde386e87d4033832f2996f5493238eda96ccf559d1d62760c4de0613f8",
    "backbones/resnet50-19c8e357.pth": "19c8e3572231adff6824a2da93fd67b5986919a2e65f8b6007eab4edee220097",
}


def verify_tracking(cfg):
    for name, revision in REVISIONS.items():
        source = Path(cfg.sources).resolve() / name
        if not source.is_dir():
            raise AssistantError(
                "TRACKING_SOURCE_MISSING",
                f"Required original {name} source is missing.",
            )
        actual = subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
        ).strip()
        if (
            actual != revision
            or subprocess.run(
                ["git", "-C", str(source), "diff", "--quiet", "HEAD"]
            ).returncode
        ):
            raise AssistantError(
                "TRACKING_SOURCE_MISMATCH",
                f"Required {name} source revision/clean state differs.",
            )
    for name, expected in WEIGHTS.items():
        path = Path(cfg.weights) / name
        if not path.is_file():
            raise AssistantError(
                "TRACKING_WEIGHTS_MISSING", f"Required checkpoint is missing: {name}"
            )
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise AssistantError(
                "TRACKING_WEIGHTS_MISMATCH", f"Checkpoint digest mismatch: {name}"
            )
    return {
        "sources": REVISIONS,
        "weights": WEIGHTS,
        "method": "original_sam21_tiny_and_original_cutie_base_mega",
        "postprocessing": "explicitly_disabled_cuda_extension_and_dynamic_postprocessing",
        "device": cfg.device,
        "precision": "float32",
        "torch_threads": cfg.threads,
    }


class TrackingModels:
    def __init__(self, cfg):
        self.provenance = verify_tracking(cfg)
        if cfg.device.split(":")[0] == "cpu":
            os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
        import torch

        self.torch = torch
        self.device = torch.device(cfg.device)
        if self.device.type not in ("cpu", "cuda"):
            raise AssistantError(
                "TRACKING_DEVICE_INVALID", "Unsupported device; no substitute."
            )
        if self.device.type == "cuda":
            if not torch.cuda.is_available():
                raise AssistantError(
                    "TRACKING_CUDA_UNAVAILABLE", "Required CUDA device unavailable."
                )
            torch.cuda.set_device(self.device)
            torch.cuda.set_per_process_memory_fraction(
                cfg.cuda_budget_mib
                * 1024**2
                / torch.cuda.get_device_properties(self.device).total_memory,
                self.device,
            )
        torch.set_num_threads(cfg.threads)
        torch.set_num_interop_threads(1)
        torch.manual_seed(0)
        source = Path(cfg.sources).resolve()
        weights = Path(cfg.weights).resolve()
        sys.path.insert(0, str(source / "cutie"))
        from hydra import compose, initialize_config_dir
        from omegaconf import open_dict, OmegaConf
        from cutie.model.cutie import CUTIE
        from cutie.inference.inference_core import InferenceCore
        from cutie.inference.utils.args_utils import get_dataset_cfg

        self.core_type = InferenceCore
        with initialize_config_dir(
            version_base="1.3.2", config_dir=str(source / "cutie/cutie/config")
        ):
            self.cfg = compose(config_name="eval_config", overrides=["dataset=generic"])
        get_dataset_cfg(self.cfg)
        self.cfg.max_internal_size = 480
        with open_dict(self.cfg.model):
            self.cfg.model.resnet_model_path = str(weights / "backbones")
        self.model = CUTIE(self.cfg).eval()
        state = torch.load(
            weights / "cutie-base-mega.pth", map_location="cpu", weights_only=True
        )
        if {k: tuple(v.shape) for k, v in self.model.state_dict().items()} != {
            k: tuple(v.shape) for k, v in state.items()
        }:
            raise AssistantError(
                "TRACKING_STATE_MISMATCH",
                "No partial/randomly initialized checkpoint accepted.",
            )
        self.model.load_weights(state)
        if not all(
            torch.equal(v, state[k]) for k, v in self.model.state_dict().items()
        ):
            raise AssistantError(
                "TRACKING_STATE_MISMATCH",
                "Checkpoint loading disagrees with original tensors.",
            )
        self.model = self.model.to(self.device)
        del state
        sys.path.insert(0, str(source / "sam2"))
        from sam2.build_sam import build_sam2
        from sam2.sam2_image_predictor import SAM2ImagePredictor

        sam = build_sam2(
            "configs/sam2.1/sam2.1_hiera_t.yaml",
            str(weights / "sam2.1_hiera_tiny.pt"),
            device=str(self.device),
            apply_postprocessing=False,
        )
        self.predictor = SAM2ImagePredictor(sam, max_hole_area=0, max_sprinkle_area=0)
        self.provenance["cutie_configuration"] = OmegaConf.to_container(
            self.cfg, resolve=True
        )
        self.provenance["torch_version"] = torch.__version__
        self.processor = None

    def sync(self):
        if self.device.type == "cuda":
            self.torch.cuda.synchronize(self.device)

    def preview(self, image_bgr, prompt):
        start = time.perf_counter()
        rgb = image_bgr[:, :, ::-1].copy()
        points = (
            np.asarray(prompt["points"], dtype=np.float32) if prompt["points"] else None
        )
        labels = (
            np.asarray(prompt["labels"], dtype=np.int32) if prompt["points"] else None
        )
        box = (
            np.asarray(prompt["box"], dtype=np.float32)
            if prompt["box"] is not None
            else None
        )
        with self.torch.inference_mode():
            self.predictor.set_image(rgb)
            masks, scores, _ = self.predictor.predict(
                point_coords=points, point_labels=labels, box=box, multimask_output=True
            )
        self.sync()
        return [
            (mask.astype(np.uint8), float(score)) for mask, score in zip(masks, scores)
        ], time.perf_counter() - start

    def reset(self):
        self.processor = self.core_type(self.model, cfg=self.cfg)

    def step(self, image_bgr, seed=None):
        if self.processor is None:
            raise AssistantError(
                "TRACKING_NOT_INITIALIZED", "No target processor exists."
            )
        started = time.perf_counter()
        torch = self.torch
        tensor = (
            torch.from_numpy(image_bgr[:, :, ::-1].copy())
            .permute(2, 0, 1)
            .to(device=self.device, dtype=torch.float32)
            / 255
        )
        with torch.inference_mode():
            prob = (
                self.processor.step(
                    tensor,
                    torch.from_numpy(seed.astype(np.int64)).to(self.device),
                    objects=[1],
                )
                if seed is not None
                else self.processor.step(tensor)
            )
            mask = self.processor.output_prob_to_mask(prob)
        self.sync()
        result = mask.cpu().numpy().astype(np.uint8)
        return result, time.perf_counter() - started
