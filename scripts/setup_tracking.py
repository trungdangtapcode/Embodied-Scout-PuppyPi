"""Opt-in provisioning of the verified SAM/Cutie environment; never a default test."""

import os
from pathlib import Path
import subprocess

from setup_vision import prepare_checkpoint, prepare_source, run
from teach_and_find.config import Settings
from teach_and_find.tracking_models import REVISIONS, WEIGHTS, verify_tracking


def main():
    cfg = Settings().tracking
    root = Path(__file__).resolve().parents[1]
    source = Path(cfg.sources).resolve()
    for name, url in [
        ("sam2", "https://github.com/facebookresearch/sam2"),
        ("cutie", "https://github.com/hkchengrex/Cutie"),
    ]:
        prepare_source(url, source / name, REVISIONS[name])
    urls = {
        "sam2.1_hiera_tiny.pt": "https://huggingface.co/facebook/sam2.1-hiera-tiny/resolve/de431c4043854a71d8101e17995dfe596bf101a5/sam2.1_hiera_tiny.pt",
        "cutie-base-mega.pth": "https://github.com/hkchengrex/Cutie/releases/download/v1.0/cutie-base-mega.pth",
        "backbones/resnet18-5c106cde.pth": "https://download.pytorch.org/models/resnet18-5c106cde.pth",
        "backbones/resnet50-19c8e357.pth": "https://download.pytorch.org/models/resnet50-19c8e357.pth",
    }
    for name, url in urls.items():
        prepare_checkpoint(url, Path(cfg.weights) / name, WEIGHTS[name])
    python = root / ".venv-tracking/bin/python"
    if not python.exists():
        run("uv", "venv", "--python", "3.12", str(python.parent.parent))
    run(
        "uv",
        "pip",
        "sync",
        "--python",
        str(python),
        str(root / "requirements/tracking.txt"),
    )
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            "--no-deps",
            "--no-build-isolation",
            "-e",
            str(source / "sam2"),
        ],
        env=dict(os.environ, SAM2_BUILD_CUDA="0", SAM2_BUILD_ALLOW_ERRORS="0"),
        check=True,
    )
    verify_tracking(cfg)
    print(
        "Original sources/checkpoints verified. Start tracking-worker separately; setup is not inference evidence."
    )


if __name__ == "__main__":
    main()
