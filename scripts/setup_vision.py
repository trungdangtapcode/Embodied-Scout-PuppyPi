"""Opt-in source, CPU environment and checkpoint installation; never run by tests."""

from pathlib import Path
import subprocess
import tempfile

from teach_and_find.config import Settings


def run(*args):
    subprocess.run(list(args), check=True)


def prepare_source(url, path, revision):
    from teach_and_find.model_artifacts import verified_checkout

    source = Path(path).expanduser().resolve()
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        run("git", "clone", "--no-checkout", url, str(source))
        run("git", "-C", str(source), "checkout", revision)
    return verified_checkout(str(source), revision, "VISION_SETUP")


def prepare_checkpoint(url, path, digest):
    from teach_and_find.model_artifacts import verified_weights

    checkpoint = Path(path).expanduser().resolve()
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    if not checkpoint.exists():
        with tempfile.NamedTemporaryFile(dir=checkpoint.parent, delete=False) as tmp:
            name = Path(tmp.name)
        try:
            # Bounded transfer of the selected asset; no alternative checkpoint.
            run(
                "curl",
                "--fail",
                "--location",
                "--max-time",
                "180",
                "--connect-timeout",
                "10",
                "--output",
                str(name),
                url,
            )
            verified_weights(str(name), digest, "VISION_SETUP")
            name.replace(checkpoint)
        finally:
            name.unlink(missing_ok=True)
    verified_weights(str(checkpoint), digest, "VISION_SETUP")


def main():
    root = Path(__file__).resolve().parents[1]
    cfg = Settings().vision
    source = prepare_source(
        "https://github.com/THU-MIG/yoloe", cfg.upstream_path, cfg.upstream_revision
    )
    prepare_source(
        "https://github.com/facebookresearch/dinov2",
        cfg.descriptor_source,
        cfg.descriptor_revision,
    )
    prepare_checkpoint(
        f"https://huggingface.co/jameslahm/yoloe/resolve/{cfg.checkpoint_revision}/yoloe-v8s-seg.pt",
        cfg.checkpoint,
        cfg.checkpoint_sha256,
    )
    prepare_checkpoint(
        "https://dl.fbaipublicfiles.com/dinov2/dinov2_vits14/dinov2_vits14_pretrain.pth",
        cfg.descriptor_checkpoint,
        cfg.descriptor_sha256,
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
        f"Both vision sources/checkpoints prepared: {cfg.upstream_revision}, {cfg.descriptor_revision}. Inference is not yet established."
    )


if __name__ == "__main__":
    main()
