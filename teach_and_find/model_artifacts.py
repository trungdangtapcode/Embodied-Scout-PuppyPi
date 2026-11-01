"""Verify pinned research source and weights before importing/loading models."""

import hashlib
from pathlib import Path
import subprocess

from teach_and_find.storage import AssistantError


def verified_checkout(path: str, revision: str, prefix: str) -> Path:
    source = Path(path).expanduser().resolve()
    try:
        current = subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        clean = (
            subprocess.run(
                ["git", "-C", str(source), "diff", "--exit-code", "HEAD"],
                capture_output=True,
            ).returncode
            == 0
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise AssistantError(
            prefix + "_SOURCE_MISSING", f"Required source is unavailable: {source}"
        ) from error
    if current != revision or not clean:
        raise AssistantError(
            prefix + "_SOURCE_MISMATCH",
            f"Required source must match the unmodified pinned revision: {source}",
        )
    return source


def verified_weights(path: str, digest: str, prefix: str) -> Path:
    weights = Path(path).expanduser().resolve()
    try:
        actual = hashlib.sha256(weights.read_bytes()).hexdigest()
    except OSError as error:
        raise AssistantError(
            prefix + "_CHECKPOINT_MISSING",
            f"Required checkpoint is unavailable: {weights}",
        ) from error
    if actual != digest:
        raise AssistantError(
            prefix + "_CHECKPOINT_MISMATCH", f"Checkpoint digest mismatch: {weights}"
        )
    return weights
