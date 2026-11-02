"""Opt-in pinned search sources and CPU dependencies; no default-test downloads."""

from pathlib import Path

from setup_vision import prepare_checkpoint, prepare_source, run
from teach_and_find.config import Settings
from teach_and_find.lightglue_adapter import WEIGHTS
from teach_and_find.search_navigation import LIGHTGLUE_REVISION, ROBOTICS_REVISION
from teach_and_find.anomaly_model import REVISION as ANOMALY_REVISION


def main():
    cfg = Settings().search
    root = Path(__file__).resolve().parents[1]
    python = root / ".venv-vision/bin/python"
    if not python.exists():
        raise SystemExit("Run make vision-setup first.")
    source = prepare_source(
        "https://github.com/cvg/LightGlue", cfg.lightglue_source, LIGHTGLUE_REVISION
    )
    prepare_source(
        "https://github.com/AtsushiSakai/PythonRobotics",
        cfg.robotics_source,
        ROBOTICS_REVISION,
    )
    prepare_source(
        "https://github.com/dammsi/AnomalyDINO", cfg.anomaly_source, ANOMALY_REVISION
    )
    for name, url in {
        "depth-save.pth": "https://raw.githubusercontent.com/cvlab-epfl/disk/master/depth-save.pth",
        "disk_lightglue_v0-1_arxiv.pth": "https://github.com/cvg/LightGlue/releases/download/v0.1_arxiv/disk_lightglue.pth",
    }.items():
        prepare_checkpoint(url, str(Path(cfg.weights) / name), WEIGHTS[name])
    run(
        "uv",
        "pip",
        "install",
        "--python",
        str(python),
        "--no-deps",
        "kornia==0.8.2",
        "kornia-rs==0.1.9",
        "websocket-client==1.9.0",
        "-e",
        str(source),
    )
    anomaly_python = root / cfg.anomaly_python
    if not anomaly_python.exists():
        run("uv", "venv", "--python", "3.12", str(anomaly_python.parent.parent))
    run(
        "uv",
        "pip",
        "install",
        "--python",
        str(anomaly_python),
        "torch==2.6.0",
        "torchvision==0.21.0",
        "--index-url",
        "https://download.pytorch.org/whl/cpu",
    )
    run(
        "uv",
        "pip",
        "install",
        "--python",
        str(anomaly_python),
        "numpy==1.26.4",
        "opencv-python==4.11.0.86",
        "scipy==1.15.3",
        "scikit-learn==1.7.2",
        "faiss-cpu==1.12.0",
        "matplotlib==3.10.1",
        "pandas==2.2.3",
        "tifffile==2025.6.11",
        "tqdm==4.67.1",
        "PyYAML==6.0.2",
    )
    print(
        "Pinned search sources/checkpoints installed. Execution and quality need separate evidence."
    )


if __name__ == "__main__":
    main()
