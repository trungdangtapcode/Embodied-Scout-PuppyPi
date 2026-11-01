"""Execute original SAM 2.1/Cutie components; no app, robot or fallback."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import socket
import subprocess
import sys
import time
import traceback

import numpy as np
from PIL import Image
import torch

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


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def no_connect(*args, **kwargs):
    raise RuntimeError("NETWORK_FORBIDDEN_DURING_INFERENCE")


def save_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sources", type=Path, required=True)
    p.add_argument("--weights", type=Path, required=True)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--device", required=True)
    p.add_argument("--threads", type=int, required=True)
    p.add_argument("--cuda-budget-mib", type=int, default=768)
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {
        "scope": "genuine_component_execution_not_app_integration_or_identity_acceptance",
        "requested_device": args.device,
        "status": "running",
        "stage": "preflight",
        "frames": [],
        "cpu_threads": args.threads,
        "precision": "float32",
        "source_revisions": REVISIONS,
        "checkpoint_sha256": WEIGHTS,
        "probe_source_sha256": sha(Path(__file__)),
    }
    started = time.perf_counter()
    try:
        for name, expected in REVISIONS.items():
            src = (args.sources / name).resolve()
            rev = subprocess.check_output(
                ["git", "-C", str(src), "rev-parse", "HEAD"], text=True
            ).strip()
            if rev != expected:
                raise RuntimeError(f"SOURCE_REVISION_MISMATCH: {name}")
            subprocess.run(
                ["git", "-C", str(src), "diff", "--quiet", "HEAD"], check=True
            )
        for filename, expected in WEIGHTS.items():
            if sha(args.weights / filename) != expected:
                raise RuntimeError(f"CHECKPOINT_DIGEST_MISMATCH: {filename}")
        spec = json.loads(args.input.read_text())
        report["input_spec"] = spec
        report["input_spec_sha256"] = sha(args.input)
        report["torch"] = torch.__version__
        report["cuda_build"] = torch.version.cuda
        device = torch.device(args.device)
        if device.type == "cpu":
            if args.device.startswith("cuda") and torch.cuda.is_initialized():
                raise RuntimeError("CPU_PROFILE_HAS_EXISTING_CUDA_CONTEXT")
            os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
            report["cpu_device_isolation"] = (
                "Explicit CPU profile hides CUDA to prevent original SAM constructor cache warmup on a GPU."
            )
        torch.set_num_threads(args.threads)
        torch.set_num_interop_threads(1)
        torch.manual_seed(0)
        if device.type == "cuda":
            report["stage"] = "cuda_preflight"
            if not torch.cuda.is_available():
                raise RuntimeError("CUDA_UNAVAILABLE_NO_SUBSTITUTION")
            torch.cuda.set_device(device)
            torch.cuda.set_per_process_memory_fraction(
                args.cuda_budget_mib
                * 1024**2
                / torch.cuda.get_device_properties(device).total_memory,
                device,
            )
            free, total = torch.cuda.mem_get_info(device)
            report["cuda_free_before_bytes"] = free
            report["cuda_total_bytes"] = total
            report["cuda_allocator_budget_mib"] = args.cuda_budget_mib
            torch.cuda.reset_peak_memory_stats(device)
        elif device.type != "cpu":
            raise RuntimeError("UNSUPPORTED_DEVICE_NO_SUBSTITUTION")
        report["cuda_visible_devices"] = os.environ.get("CUDA_VISIBLE_DEVICES")

        def sync():
            if device.type == "cuda":
                torch.cuda.synchronize(device)

        socket.socket.connect = no_connect
        os.environ["HF_HUB_OFFLINE"] = "1"
        sys.path.insert(0, str((args.sources / "cutie").resolve()))
        from hydra import compose, initialize_config_dir
        from omegaconf import open_dict, OmegaConf
        from cutie.model.cutie import CUTIE
        from cutie.inference.inference_core import InferenceCore
        from cutie.inference.utils.args_utils import get_dataset_cfg

        report["stage"] = "cutie_load"
        begin = time.perf_counter()
        with initialize_config_dir(
            version_base="1.3.2",
            config_dir=str((args.sources / "cutie/cutie/config").resolve()),
        ):
            cfg = compose(config_name="eval_config", overrides=["dataset=generic"])
        get_dataset_cfg(cfg)
        cfg.max_internal_size = 480
        with open_dict(cfg.model):
            cfg.model.resnet_model_path = str((args.weights / "backbones").resolve())
        model = CUTIE(cfg).eval()
        state = torch.load(
            args.weights / "cutie-base-mega.pth", map_location="cpu", weights_only=True
        )
        expected = {k: tuple(v.shape) for k, v in model.state_dict().items()}
        actual = {k: tuple(v.shape) for k, v in state.items()}
        if expected != actual:
            raise RuntimeError("CUTIE_STATE_KEYS_OR_SHAPES_MISMATCH_NO_PARTIAL_LOAD")
        model.load_weights(state)
        if not all(torch.equal(v, state[k]) for k, v in model.state_dict().items()):
            raise RuntimeError("CUTIE_WEIGHT_LOAD_DISAGREEMENT")
        del state
        model = model.to(device)
        sync()
        report["cutie_load_s"] = time.perf_counter() - begin
        report["cutie_config"] = OmegaConf.to_container(cfg, resolve=True)
        print(
            json.dumps(
                {
                    "stage": "cutie_loaded",
                    "device": args.device,
                    "seconds": report["cutie_load_s"],
                }
            ),
            flush=True,
        )
        first_path = Path(spec["frames"][0])
        rgb = np.asarray(Image.open(first_path).convert("RGB")).copy()
        if spec["seed_kind"] == "sam2_authored_box":
            report["stage"] = "sam_load"
            begin = time.perf_counter()
            sys.path.insert(0, str((args.sources / "sam2").resolve()))
            from sam2.build_sam import build_sam2
            from sam2.sam2_image_predictor import SAM2ImagePredictor

            sam = build_sam2(
                "configs/sam2.1/sam2.1_hiera_t.yaml",
                str(args.weights / "sam2.1_hiera_tiny.pt"),
                device=str(device),
                apply_postprocessing=False,
            )
            predictor = SAM2ImagePredictor(sam, max_hole_area=0, max_sprinkle_area=0)
            sync()
            report["sam_load_s"] = time.perf_counter() - begin
            report["stage"] = "sam_predict"
            begin = time.perf_counter()
            with torch.inference_mode():
                predictor.set_image(rgb)
                masks, scores, logits = predictor.predict(
                    box=np.asarray(spec["box_xyxy"], dtype=np.float32),
                    multimask_output=True,
                )
            sync()
            report["sam_predict_s"] = time.perf_counter() - begin
            selected = int(np.argmax(scores))
            seed = masks[selected].astype(np.uint8)
            report["sam_mask_scores"] = scores.tolist()
            report["sam_selected_mask"] = selected
            for i, mask in enumerate(masks):
                Image.fromarray(mask.astype(np.uint8) * 255).save(
                    out / f"sam-candidate-{i}.png"
                )
            np.savez_compressed(
                out / "sam-raw-output.npz",
                masks=masks,
                scores=scores,
                low_resolution_logits=logits,
            )
            report["sam_postprocessing"] = (
                "explicitly disabled; original learned mask logits and original zero threshold; no extension fallback"
            )
            print(
                json.dumps(
                    {
                        "stage": "sam_predicted",
                        "seconds": report["sam_predict_s"],
                        "scores": scores.tolist(),
                        "seed_pixels": int(seed.sum()),
                    }
                ),
                flush=True,
            )
        elif spec["seed_kind"] == "upstream_example_supplied_mask":
            seed = np.asarray(Image.open(spec["mask_path"]))
            report["upstream_example_note"] = (
                "Supplied reference mask; semi-supervised component replay, not interactive model initialization."
            )
        else:
            raise RuntimeError("UNKNOWN_SEED_KIND_NO_SUBSTITUTION")
        if not seed.any() or seed.shape != rgb.shape[:2]:
            raise RuntimeError("INVALID_OR_EMPTY_SEED_MASK")
        Image.fromarray(seed.astype(np.uint8)).save(out / "seed-label-mask.png")
        report["seed_mask_sha256"] = sha(out / "seed-label-mask.png")
        objects = [int(v) for v in np.unique(seed) if v != 0]
        processor = InferenceCore(model, cfg=cfg)
        report["stage"] = "cutie_steps"
        for i, path_text in enumerate(spec["frames"]):
            path = Path(path_text)
            rgb = np.asarray(Image.open(path).convert("RGB")).copy()
            begin = time.perf_counter()
            tensor = (
                torch.from_numpy(rgb.copy())
                .permute(2, 0, 1)
                .to(device=device, dtype=torch.float32)
                / 255.0
            )
            mask_tensor = (
                torch.from_numpy(seed.astype(np.int64)).to(device) if i == 0 else None
            )
            with torch.inference_mode():
                prob = (
                    processor.step(tensor, mask_tensor, objects=objects)
                    if i == 0
                    else processor.step(tensor)
                )
                mask = processor.output_prob_to_mask(prob)
            sync()
            infer_s = time.perf_counter() - begin
            output = mask.cpu().numpy().astype(np.uint8)
            if output.shape != rgb.shape[:2]:
                raise RuntimeError("OUTPUT_MASK_DIMENSION_MISMATCH")
            filename = f"frame-{i:03d}-mask.png"
            Image.fromarray(output).save(out / filename)
            visual = rgb.copy()
            fg = output != 0
            visual[fg] = (0.60 * visual[fg] + 0.40 * np.array([216, 238, 149])).astype(
                np.uint8
            )
            Image.fromarray(visual).save(out / f"frame-{i:03d}-overlay.png")
            record = {
                "ordinal": i,
                "source": str(path),
                "source_sha256": sha(path),
                "mask": filename,
                "mask_sha256": sha(out / filename),
                "labels": np.unique(output).tolist(),
                "foreground_pixels": int(fg.sum()),
                "step_s": infer_s,
            }
            report["frames"].append(record)
            print(
                json.dumps({"stage": "frame", "device": args.device, **record}),
                flush=True,
            )
        report["status"] = "completed"
        report["stage"] = "completed"
    except Exception as e:
        report["status"] = "failed"
        report["error_type"] = type(e).__name__
        report["error"] = str(e)
        (out / "traceback.txt").write_text(traceback.format_exc())
        print(
            json.dumps(
                {
                    "status": "failed",
                    "stage": report["stage"],
                    "error_type": type(e).__name__,
                    "error": str(e),
                }
            ),
            flush=True,
        )
    finally:
        report["total_s"] = time.perf_counter() - started
        report["max_rss_mib"] = (
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        )
        if args.device.startswith("cuda") and torch.cuda.is_initialized():
            report["cuda_peak_allocated_bytes"] = torch.cuda.max_memory_allocated()
            report["cuda_peak_reserved_bytes"] = torch.cuda.max_memory_reserved()
        times = [r["step_s"] for r in report["frames"]]
        if times:
            report["mean_step_s"] = float(np.mean(times))
            report["p95_step_s"] = float(np.quantile(times, 0.95))
            report["throughput_fps_compute_only"] = len(times) / sum(times)
        save_json(out / "result.json", report)
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
