"""Bind enrolled reference images to the pinned author YOLOE and ByteTrack code.

No simulator, handcrafted matcher, robot transport or model substitute is imported.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import importlib.metadata
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
from types import SimpleNamespace

import cv2
import numpy as np

from teach_and_find.config import VisionSettings
from teach_and_find.perception.proposals import CandidateProposal
from teach_and_find.storage import AssistantError, EvidenceStore


def verify_artifacts(cfg: VisionSettings) -> dict:
    source = Path(cfg.upstream_path).expanduser().resolve()
    weights = Path(cfg.checkpoint).expanduser().resolve()
    try:
        revision = subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        clean = (
            subprocess.run(
                ["git", "-C", str(source), "diff", "--exit-code", "HEAD"],
                capture_output=True,
                check=False,
            ).returncode
            == 0
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise AssistantError(
            "VISION_SOURCE_MISSING", "Pinned YOLOE source is unavailable."
        ) from error
    if revision != cfg.upstream_revision or not clean:
        raise AssistantError(
            "VISION_SOURCE_MISMATCH",
            "YOLOE must use the exact unmodified source revision.",
        )
    try:
        sha = hashlib.sha256(weights.read_bytes()).hexdigest()
    except OSError as error:
        raise AssistantError(
            "VISION_CHECKPOINT_MISSING", "The required YOLOE checkpoint is unavailable."
        ) from error
    if sha != cfg.checkpoint_sha256:
        raise AssistantError(
            "VISION_CHECKPOINT_MISMATCH",
            "YOLOE checkpoint integrity verification failed.",
        )
    files = [
        "ultralytics/models/yolo/yoloe/predict_vp.py",
        "ultralytics/nn/tasks.py",
        "ultralytics/data/augment.py",
        "ultralytics/nn/modules/head.py",
        "ultralytics/trackers/byte_tracker.py",
    ]
    return {
        "repository": "https://github.com/THU-MIG/yoloe",
        "revision": revision,
        "license": "AGPL-3.0",
        "checkpoint_sha256": sha,
        "checkpoint_revision": cfg.checkpoint_revision,
        "checkpoint_source": "https://huggingface.co/jameslahm/yoloe",
        "files_sha256": {
            p: hashlib.sha256((source / p).read_bytes()).hexdigest() for p in files
        },
    }


def reference_prompt(images: list[np.ndarray], cfg: VisionSettings):
    """Declared contact-sheet input transform; upstream computes visual embeddings."""
    columns = min(3, len(images))
    canvas = np.full(
        (
            cfg.tile_size * ((len(images) + columns - 1) // columns),
            cfg.tile_size * columns,
            3,
        ),
        128,
        np.uint8,
    )
    boxes = []
    for i, image in enumerate(images):
        h, w = image.shape[:2]
        scale = min(cfg.reference_size / w, cfg.reference_size / h)
        resized = cv2.resize(image, (max(1, int(w * scale)), max(1, int(h * scale))))
        h, w = resized.shape[:2]
        x = (i % columns) * cfg.tile_size + (cfg.tile_size - w) // 2
        y = (i // columns) * cfg.tile_size + (cfg.tile_size - h) // 2
        canvas[y : y + h, x : x + w] = resized
        boxes.append([x, y, x + w, y + h])
    return canvas, {
        "bboxes": np.asarray(boxes, np.float32),
        "cls": np.zeros(len(boxes), int),
    }


class YoloeAdapter:
    def __init__(self, cfg: VisionSettings, emit, check):
        self.cfg, self.emit, self.check = cfg, emit, check

    def run(self, store: EvidenceStore, payload: dict) -> dict:
        """Record executed author functions, separately from the method inventory."""
        source = str(Path(self.cfg.upstream_path).expanduser().resolve()) + os.sep
        targets = {
            "Model.predict",
            "YOLOEVPPredictorMixin.inference",
            "YOLOEModel.get_visual_pe",
            "SAVPE.forward",
            "YOLOE.set_classes",
            "BYTETracker.update",
        }
        names = {q.rsplit(".", 1)[1] for q in targets}
        calls = {}

        def trace(frame, event, arg):
            if event == "call" and frame.f_code.co_name in names:
                code = frame.f_code
                if code.co_qualname in targets and code.co_filename.startswith(source):
                    key = code.co_filename[len(source) :] + ":" + code.co_qualname
                    calls[key] = calls.get(key, 0) + 1

        previous = sys.getprofile()
        sys.setprofile(trace)
        try:
            result = self._run(store, payload)
        finally:
            sys.setprofile(previous)
        executed = {key.rsplit(":", 1)[1] for key in calls}
        if executed != targets:
            raise AssistantError(
                "VISION_TRACE_INCOMPLETE",
                "Required upstream methods were not observed executing.",
            )
        result["provenance"]["executed_upstream_calls"] = calls
        return result

    def _run(self, store: EvidenceStore, payload: dict) -> dict:
        cfg = self.cfg
        self.check()
        if cfg.model != "yoloe-v8s-seg":
            raise AssistantError(
                "VISION_MODEL_UNSUPPORTED",
                "Unknown vision model; no alternative is selected.",
            )
        if cfg.device != "cpu":
            raise AssistantError(
                "VISION_DEVICE_UNSUPPORTED",
                "This validated profile requires CPU execution.",
            )
        provenance = verify_artifacts(cfg)
        # Prevent upstream auto-install/download paths. Required files are verified
        # before loading the author's trusted serialized checkpoint.
        os.environ["YOLO_AUTOINSTALL"] = "false"
        os.environ["YOLO_CONFIG_DIR"] = str(store.root / "yoloe-config")
        os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
        sys.path.insert(0, str(Path(cfg.upstream_path).expanduser().resolve()))
        try:
            import torch
            import ultralytics
            from ultralytics import YOLOE
            from ultralytics.models.yolo.yoloe.predict_vp import YOLOEVPSegPredictor
            from ultralytics.trackers.byte_tracker import BYTETracker
        except ImportError as error:
            raise AssistantError(
                "VISION_DEPENDENCY_MISSING",
                f"Vision dependency unavailable: {error}. Prepare the isolated CPU environment.",
            ) from error
        source = Path(cfg.upstream_path).expanduser().resolve()
        if not Path(ultralytics.__file__).resolve().is_relative_to(source):
            raise AssistantError(
                "VISION_SOURCE_MISMATCH",
                "Another ultralytics package shadowed the pinned implementation.",
            )
        torch.set_num_threads(cfg.torch_threads)
        provenance.update(
            model=cfg.model,
            device=cfg.device,
            torch_version=torch.__version__,
            packages={
                name: importlib.metadata.version(name)
                for name in (
                    "torchvision",
                    "numpy",
                    "lap",
                    "ultralytics",
                    "opencv-python",
                    "huey",
                    "scipy",
                )
            },
            method="upstream_yoloe_savpe_segmentation_and_bytetrack",
            entry_points=[
                "YOLOEVPSegPredictor",
                "YOLOEModel.get_visual_pe",
                "SAVPE.forward",
                "YOLOE.set_classes",
                "Model.predict",
                "BYTETracker.update",
            ],
            preprocessing={
                "name": "project_reference_contact_sheet_v1",
                "tile_size": cfg.tile_size,
                "crop_fit": cfg.reference_size,
                "fill": 128,
                "image_size": cfg.image_size,
            },
            score_semantics="uncalibrated_model_score_not_identity_probability",
            identity_semantics="visual_prompt_class_candidate_not_verified_exact_instance",
            tracking_semantics="upstream_kalman_and_association_ids_local_to_this_window",
            score_threshold=cfg.score_threshold,
        )
        started = time.monotonic()
        model = YOLOE(str(Path(cfg.checkpoint).expanduser().resolve()))
        self.emit("model_loaded", {"provenance": provenance})
        embeddings = []
        references = payload["references"]
        for ref in references:
            self.check()
            images = [store.load_image(sha) for sha in ref["image_shas"]]
            canvas, prompts = reference_prompt(images, cfg)
            model.predictor = None
            model.predict(
                canvas,
                prompts=prompts,
                predictor=YOLOEVPSegPredictor,
                return_vpe=True,
                device=cfg.device,
                imgsz=cfg.image_size,
                conf=cfg.score_threshold,
                verbose=False,
                save=False,
            )
            embeddings.append(model.predictor.vpe.detach().clone())
            self.emit(
                "visual_prompt_encoded",
                {
                    "object_id": ref["object_id"],
                    "reference_shas": ref["image_shas"],
                    "prompt_image_sha": store.save_image(canvas),
                    "embedding_shape": list(embeddings[-1].shape),
                },
            )
        model.set_classes([r["name"] for r in references], torch.cat(embeddings, dim=1))
        model.predictor = None
        stamps = [datetime.fromisoformat(f["captured_at"]) for f in payload["frames"]]
        intervals = [(b - a).total_seconds() for a, b in zip(stamps, stamps[1:])]
        # ByteTrack models discrete frames, not variable capture-time dynamics.
        rate = 1 / statistics.median(intervals) if intervals else 1
        tracker = BYTETracker(
            SimpleNamespace(
                **{
                    k: getattr(cfg, k)
                    for k in (
                        "track_high_thresh",
                        "track_low_thresh",
                        "new_track_thresh",
                        "track_buffer",
                        "match_thresh",
                        "fuse_score",
                    )
                }
            ),
            frame_rate=max(1, round(rate)),
        )
        provenance["tracking_capture_intervals_s"] = intervals
        provenance["tracking_assumed_fps"] = max(1, round(rate))
        frames = []
        for source_frame in payload["frames"]:
            self.check()
            image = store.load_image(source_frame["image_sha"])
            begin = time.monotonic()
            result = model.predict(
                image,
                device=cfg.device,
                imgsz=cfg.image_size,
                conf=cfg.score_threshold,
                verbose=False,
                save=False,
            )[0]
            boxes = result.boxes.cpu().numpy()
            detections = []
            polygons = result.masks.xy if result.masks is not None else []
            for i, row in enumerate(boxes.data):
                x1, y1, x2, y2, score, cls = [float(v) for v in row]
                category = int(cls)
                if not 0 <= category < len(references):
                    raise AssistantError(
                        "VISION_OUTPUT_INVALID",
                        "YOLOE returned an unknown prompt class.",
                    )
                # Reuse the core proposal representation. Clipping/rounding binds
                # an existing model box to pixels; it does not propose or classify.
                lo = np.floor([x1, y1]).astype(int)
                hi = np.ceil([x2, y2]).astype(int)
                ax, ay = np.maximum(lo, [0, 0])
                bx, by = np.minimum(hi, [image.shape[1], image.shape[0]])
                if bx <= ax or by <= ay:
                    raise AssistantError(
                        "VISION_OUTPUT_INVALID",
                        "Model box has no image intersection; no substitute crop.",
                    )
                proposal = CandidateProposal(
                    (int(ax), int(ay), int(bx - ax), int(by - ay)),
                    score,
                    ((ax + bx) / 2, (ay + by) / 2),
                    int((bx - ax) * (by - ay)),
                    image[ay:by, ax:bx].copy(),
                )
                detections.append(
                    {
                        "detection_index": i,
                        "xyxy": [x1, y1, x2, y2],
                        "model_score": score,
                        "bbox_xywh": proposal.bbox_xywh,
                        "crop_image_sha": store.save_image(proposal.crop_bgr),
                        "prompt_object_id": references[category]["object_id"],
                        "prompt_name": references[category]["name"],
                        "mask_polygon_xy": polygons[i].tolist()
                        if i < len(polygons)
                        else [],
                    }
                )
            tracks = []
            for row in tracker.update(boxes):
                x1, y1, x2, y2, tid, score, cls, index = [float(v) for v in row]
                tracks.append(
                    {
                        "xyxy": [x1, y1, x2, y2],
                        "track_id": int(tid),
                        "model_score": score,
                        "detection_index": int(index),
                        "prompt_object_id": references[int(cls)]["object_id"],
                    }
                )
            frame = {
                **source_frame,
                "width": image.shape[1],
                "height": image.shape[0],
                "detections": detections,
                "tracks": tracks,
                "elapsed_s": time.monotonic() - begin,
            }
            frames.append(frame)
            self.emit(
                "frame_inferred",
                {
                    "frame_id": frame["frame_id"],
                    "detections": len(detections),
                    "tracks": len(tracks),
                    "elapsed_s": frame["elapsed_s"],
                },
            )
        self.check()
        return {
            "schema_version": 1,
            "outcome": "execution_completed_quality_not_certified",
            "frames": frames,
            "references": references,
            "provenance": provenance,
            "elapsed_s": time.monotonic() - started,
        }
