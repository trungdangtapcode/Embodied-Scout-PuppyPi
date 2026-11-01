"""Custom OpenCV descriptors and an optional, separately configured Torch Hub adapter.

The default descriptor is project-owned heuristic code, not a paper implementation
or pretrained model. Merely configuring Torch Hub does not verify its weights.
"""

from __future__ import annotations

from typing import Protocol

import cv2
import numpy as np

from teach_and_find.config import PerceptionSettings


class VisualEncoder(Protocol):
    """Protocol for embedding an object crop into an L2-normalized feature vector."""

    @property
    def embedding_dim(self) -> int: ...

    def embed(self, crop_bgr: np.ndarray) -> np.ndarray: ...


def _l2_normalize(vec: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vec))
    if norm < 1e-8:
        return np.zeros_like(vec, dtype=np.float32)
    return (vec / norm).astype(np.float32)


def _signed_sqrt(vec: np.ndarray) -> np.ndarray:
    """RootSIFT-style power normalization for histogram comparison stability."""
    return np.sign(vec) * np.sqrt(np.abs(vec) + 1e-10)


class SpatialAppearanceEncoder:
    """Fast multi-cue spatial appearance & shape descriptor (offline/CPU deterministic).

    Combines three complementary cues over spatial grids so objects that share
    base color but differ in surface markings/geometry remain separable when
    viewed from informative angles:
      1. 3x3 spatial HSV hue-saturation-value histograms
      2. 4x4 spatial LAB opponent-color & contrast moments (mean + std)
      3. 4x4 spatial gradient orientation histograms (8 signed/unsigned bins)
    """

    def __init__(self, crop_size: int = 96) -> None:
        self.crop_size = crop_size
        # 9*(12+6+4) + 16*6 + 16*8 = 198 + 96 + 128 = 422 dims
        self._dim = 9 * (12 + 6 + 4) + 16 * 6 + 16 * 8

    @property
    def embedding_dim(self) -> int:
        return self._dim

    def embed(self, crop_bgr: np.ndarray) -> np.ndarray:
        if crop_bgr is None or crop_bgr.size == 0:
            raise ValueError(
                "A nonempty crop is required; no synthetic embedding is produced."
            )

        img = cv2.resize(
            crop_bgr,
            (self.crop_size, self.crop_size),
            interpolation=cv2.INTER_AREA,
        )
        # Center-elliptical foreground mask suppresses background floor/wall corners in tight bbox crops
        yy, xx = np.mgrid[0 : self.crop_size, 0 : self.crop_size].astype(np.float32)
        ny = (yy - 0.5 * (self.crop_size - 1)) / (0.5 * self.crop_size)
        nx = (xx - 0.5 * (self.crop_size - 1)) / (0.5 * self.crop_size)
        fg_mask = ((nx * nx + ny * ny) <= 0.82).astype(np.uint8) * 255
        spatial_weight = np.exp(-1.15 * (nx * nx + ny * ny)).astype(np.float32)

        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0

        # 1) 3x3 HSV spatial histograms (foreground-masked, zero-mean centered)
        hsv_feats: list[np.ndarray] = []
        step3 = self.crop_size // 3
        for gy in range(3):
            for gx in range(3):
                patch = hsv[
                    gy * step3 : (gy + 1) * step3, gx * step3 : (gx + 1) * step3
                ]
                pmask = fg_mask[
                    gy * step3 : (gy + 1) * step3, gx * step3 : (gx + 1) * step3
                ]
                h_hist = cv2.calcHist([patch], [0], pmask, [12], [0, 180]).flatten()
                s_hist = cv2.calcHist([patch], [1], pmask, [6], [0, 256]).flatten()
                v_hist = cv2.calcHist([patch], [2], pmask, [4], [0, 256]).flatten()
                cell = np.concatenate([h_hist, s_hist, v_hist]).astype(np.float32)
                cell /= float(np.sum(pmask > 0)) + 1.0
                hsv_feats.append(np.sqrt(np.maximum(cell, 0.0)))
        hsv_raw = np.concatenate(hsv_feats)
        hsv_vec = _l2_normalize(hsv_raw - np.mean(hsv_raw))

        # 2) 4x4 LAB spatial moments (illumination-normalized L contrast + opponent a, b)
        l_chan = lab[:, :, 0]
        l_norm = (l_chan - np.mean(l_chan)) / (np.std(l_chan) + 5.0)
        ab_norm = (lab[:, :, 1:] - 128.0) / 38.0
        lab_stack = np.dstack([l_norm, ab_norm]) * spatial_weight[:, :, None]
        lab_feats: list[np.ndarray] = []
        step4 = self.crop_size // 4
        for gy in range(4):
            for gx in range(4):
                cell = lab_stack[
                    gy * step4 : (gy + 1) * step4, gx * step4 : (gx + 1) * step4
                ]
                means = np.mean(cell, axis=(0, 1))
                stds = np.std(cell, axis=(0, 1))
                lab_feats.append(np.concatenate([means, stds]).astype(np.float32))
        lab_vec = _l2_normalize(np.concatenate(lab_feats))

        # 3) 4x4 spatial oriented gradient histograms (captures symbols/stripes/edges)
        dx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        dy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        mag = np.hypot(dx, dy) * spatial_weight
        ang = (np.rad2deg(np.arctan2(dy, dx)) + 180.0) % 180.0  # unsigned [0, 180)
        hog_feats: list[np.ndarray] = []
        bins = np.linspace(0.0, 180.0, 9)
        for gy in range(4):
            for gx in range(4):
                m_cell = mag[
                    gy * step4 : (gy + 1) * step4, gx * step4 : (gx + 1) * step4
                ].ravel()
                a_cell = ang[
                    gy * step4 : (gy + 1) * step4, gx * step4 : (gx + 1) * step4
                ].ravel()
                hist, _ = np.histogram(a_cell, bins=bins, weights=m_cell)
                hog_feats.append(np.sqrt(np.maximum(hist.astype(np.float32), 0.0)))
        hog_raw = np.concatenate(hog_feats)
        hog_vec = _l2_normalize(hog_raw - np.mean(hog_raw))

        combined = np.concatenate([0.50 * hsv_vec, 0.35 * lab_vec, 0.40 * hog_vec])
        return _l2_normalize(combined)


class TorchHubBackboneEncoder:
    """Optional torch.hub feature-loader prototype, not verified model execution.

    Model repository and entry point are supplied strictly through Settings /
    environment configuration (`TEACH_FIND_TORCH_HUB_REPO`, `TEACH_FIND_TORCH_HUB_MODEL`).
    The caller must separately audit the source, preprocessing and actual weights;
    this generic adapter does not verify a checkpoint digest or prove paper reuse.
    """

    def __init__(self, repo: str, model_name: str, device: str = "cpu") -> None:
        if not repo or not model_name:
            raise ValueError(
                "TorchHubBackboneEncoder requires non-empty repo and model_name in Settings."
            )
        import torch

        self._torch = torch
        self.device = torch.device(device)
        self.model = torch.hub.load(repo, model_name)
        self.model.eval().to(self.device)
        self.input_size = 224  # divisible by patch size 14 and 16
        self._mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        self._std = np.array([0.229, 0.224, 0.225], dtype=np.float32)

        with torch.no_grad():
            dummy = torch.zeros(
                1, 3, self.input_size, self.input_size, device=self.device
            )
            out = self.model(dummy)
            self._dim = int(out.shape[-1])

    @property
    def embedding_dim(self) -> int:
        return self._dim

    def embed(self, crop_bgr: np.ndarray) -> np.ndarray:
        if crop_bgr is None or crop_bgr.size == 0:
            raise ValueError(
                "A nonempty crop is required; no synthetic embedding is produced."
            )

        rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(
            rgb, (self.input_size, self.input_size), interpolation=cv2.INTER_CUBIC
        )
        norm = (resized.astype(np.float32) / 255.0 - self._mean) / self._std
        chw = np.transpose(norm, (2, 0, 1))[None, ...]
        tensor = self._torch.from_numpy(chw).to(self.device)
        with self._torch.no_grad():
            feat = self.model(tensor).detach().cpu().numpy().reshape(-1)
        return _l2_normalize(feat)


def build_encoder(settings: PerceptionSettings | None = None) -> VisualEncoder:
    """Instantiate the configured visual encoder backend."""
    cfg = settings or PerceptionSettings()
    if cfg.encoder_backend == "torch_hub":
        return TorchHubBackboneEncoder(
            repo=cfg.torch_hub_repo,
            model_name=cfg.torch_hub_model,
            device=cfg.device,
        )
    if cfg.encoder_backend == "spatial_appearance":
        return SpatialAppearanceEncoder(crop_size=cfg.crop_size)
    raise ValueError(
        f"Unsupported encoder backend: {cfg.encoder_backend!r}; no fallback."
    )
