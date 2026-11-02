"""Opt-in pinned search sources and CPU dependencies; no default-test downloads."""

from pathlib import Path

from setup_vision import prepare_checkpoint, prepare_source, run
from teach_and_find.config import Settings
from teach_and_find.lightglue_adapter import WEIGHTS
from teach_and_find.search_navigation import LIGHTGLUE_REVISION, ROBOTICS_REVISION


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
    print(
        "Pinned search sources/checkpoints installed. Execution and quality need separate evidence."
    )


if __name__ == "__main__":
    main()
