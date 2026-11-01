"""Opt-in source, CPU environment and checkpoint installation; never run by tests."""

import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request

from teach_and_find.config import Settings


def run(*args):
    subprocess.run(list(args), check=True)


def main():
    root = Path(__file__).resolve().parents[1]
    cfg = Settings().vision
    source = Path(cfg.upstream_path).expanduser().resolve()
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        run(
            "git",
            "clone",
            "--no-checkout",
            "https://github.com/THU-MIG/yoloe",
            str(source),
        )
        run("git", "-C", str(source), "checkout", cfg.upstream_revision)
    revision = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != cfg.upstream_revision:
        raise SystemExit(
            "Preserve the existing source checkout; select another PUPPYPI_YOLOE_PATH."
        )
    run("git", "-C", str(source), "diff", "--exit-code", "HEAD")
    checkpoint = Path(cfg.checkpoint).expanduser().resolve()
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    if not checkpoint.exists():
        url = f"https://huggingface.co/jameslahm/yoloe/resolve/{cfg.checkpoint_revision}/yoloe-v8s-seg.pt"
        with tempfile.NamedTemporaryFile(dir=checkpoint.parent, delete=False) as tmp:
            name = Path(tmp.name)
        try:
            with (
                urllib.request.urlopen(url, timeout=60) as response,
                name.open("wb") as target,
            ):
                shutil.copyfileobj(response, target)
            if hashlib.sha256(name.read_bytes()).hexdigest() != cfg.checkpoint_sha256:
                raise SystemExit("Downloaded checkpoint digest mismatch.")
            name.replace(checkpoint)
        finally:
            name.unlink(missing_ok=True)
    if hashlib.sha256(checkpoint.read_bytes()).hexdigest() != cfg.checkpoint_sha256:
        raise SystemExit(
            "Existing checkpoint digest mismatch; preserve it and select another path."
        )
    python = root / ".venv-vision/bin/python"
    if not python.exists():
        run("uv", "venv", "--python", "3.12", str(root / ".venv-vision"))
    run(
        "uv",
        "pip",
        "sync",
        "--python",
        str(python),
        "--index",
        "https://download.pytorch.org/whl/cpu",
        "--index-strategy",
        "unsafe-best-match",
        str(root / "requirements/vision-cpu.txt"),
    )
    run("uv", "pip", "install", "--python", str(python), "--no-deps", "-e", str(source))
    print(
        f"Vision source/checkpoint/environment prepared: {revision}. Inference is not yet established."
    )


if __name__ == "__main__":
    main()
