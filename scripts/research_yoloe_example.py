"""Execute the author's unmodified visual-prompt example with its v8-L weights."""

import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import runpy

from teach_and_find.config import Settings
from teach_and_find.yoloe_adapter import verify_artifacts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    cfg = replace(
        Settings().vision,
        checkpoint=str(args.checkpoint.resolve()),
        checkpoint_sha256="14e9c146f7f7efa0bfea8c5f82952c9f95fb1f9c3bf0f18b3727b76624f9d746",
    )
    manifest = verify_artifacts(cfg)
    base = args.directory.resolve()
    base.mkdir(parents=True, exist_ok=False)
    source = Path(cfg.upstream_path).resolve()
    (base / "pretrain").mkdir()
    (base / "pretrain/yoloe-v8l-seg.pt").symlink_to(Path(cfg.checkpoint))
    (base / "ultralytics").symlink_to(source / "ultralytics", target_is_directory=True)
    os.environ.update(
        CUDA_VISIBLE_DEVICES="-1",
        YOLO_AUTOINSTALL="false",
        MPLBACKEND="Agg",
        YOLO_CONFIG_DIR=str(base / "config"),
    )
    import torch
    from ultralytics import settings

    torch.set_num_threads(cfg.torch_threads)
    settings.update({"runs_dir": str(base / "outputs")})
    os.chdir(base)
    namespace = runpy.run_path(
        str(source / "predict_visual_prompt.py"), run_name="__main__"
    )
    manifest.update(
        example="predict_visual_prompt.py",
        model="yoloe-v8l-seg",
        device="cpu",
        outcome="upstream_example_executed_not_application_quality_evidence",
        final_image_detections=namespace["model"]
        .predictor.results[0]
        .boxes.data.tolist(),
    )
    (base / "manifest.json").write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
