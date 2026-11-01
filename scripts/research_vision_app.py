"""Opt-in genuine CPU model execution on rendered input through the app UI.

Requires `make vision-setup`, `make app-build`, the host app environment and
Chromium. Owns and stops both children. Never contacts a robot or a paid API.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    base = args.directory.resolve()
    if base.exists():
        parser.error("Select a NEW disposable directory; existing state is preserved.")
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 18768)) == 0:
            parser.error(
                "Port 18768 is occupied; refusing to attach to another service."
            )
    base.mkdir(parents=True)
    files = [
        "teach_and_find/config.py",
        "teach_and_find/storage.py",
        "teach_and_find/yoloe_adapter.py",
        "teach_and_find/dinov2_adapter.py",
        "teach_and_find/model_artifacts.py",
        "teach_and_find/vision_service.py",
        "teach_and_find/vision_worker.py",
        "teach_and_find/memory_queue.py",
        "teach_and_find/mobile/api.py",
        "teach_and_find/mobile/runtime.py",
        "teach_and_find/sim/world3d.py",
        "web/src/VisionConsole.tsx",
        "scripts/research_vision_server.py",
        "scripts/research_vision_capture.mjs",
        "scripts/research_vision_eval.py",
        "scripts/research_vision_failures.py",
        "requirements/vision-cpu.txt",
    ]
    manifest = {
        "mode": "synthetic",
        "device": "cpu",
        "paid_api_calls": 0,
        "root_revision_before_run": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
        "uncommitted_source": bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=root, text=True
            ).strip()
        ),
        "source_sha256": {
            p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in files
        },
        "method": "actual_yoloe_and_dinov2_with_declared_custom_reference_policy_and_bytetrack_on_rendered_images",
        "claim_boundary": "model_execution_not_identity_quality_navigation_RL_or_physical_verification",
    }
    (base / "run-manifest.json").write_text(json.dumps(manifest, indent=2))
    env = {
        **os.environ,
        "PYTHONPATH": str(root),
        "CUDA_VISIBLE_DEVICES": "-1",
        "MPLBACKEND": "Agg",
        "YOLO_AUTOINSTALL": "false",
        "PUPPYPI_VISION_ENABLED": "1",
        "PUPPYPI_MEMORY_ENABLED": "0",
        "TEACH_FIND_DATA_DIR": str(base / "state"),
        "PUPPYPI_VISION_ACCEPTANCE_DIR": str(base),
    }
    env.pop("OPENAI_API_KEY", None)
    children, logs = [], []
    try:
        for name, command in [
            (
                "worker",
                [
                    str(root / ".venv-vision/bin/python"),
                    "-m",
                    "teach_and_find.vision_worker",
                ],
            ),
            (
                "app",
                [
                    str(root / ".venv-dev/bin/python"),
                    "scripts/research_vision_server.py",
                ],
            ),
        ]:
            log = (base / f"{name}.log").open("w")
            logs.append(log)
            children.append(
                subprocess.Popen(command, cwd=root, env=env, stdout=log, stderr=log)
            )
        for _ in range(300):
            if any(p.poll() is not None for p in children):
                raise RuntimeError(
                    "Acceptance child exited; inspect app.log/worker.log."
                )
            try:
                urllib.request.urlopen(
                    "http://127.0.0.1:18768/api/health", timeout=1
                ).close()
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise TimeoutError("Rendered acceptance server did not start.")
        subprocess.run(
            ["node", "scripts/research_vision_capture.mjs"],
            cwd=root,
            env=env,
            check=True,
            timeout=600,
        )
        subprocess.run(
            [
                str(root / ".venv-dev/bin/python"),
                "scripts/research_vision_eval.py",
                "--directory",
                str(base),
            ],
            cwd=root,
            env=env,
            check=True,
            timeout=60,
        )
        subprocess.run(
            [
                str(root / ".venv-dev/bin/python"),
                "scripts/research_vision_failures.py",
                "--directory",
                str(base),
            ],
            cwd=root,
            env=env,
            check=True,
            timeout=90,
        )
        print(
            f"Actual CPU model/app artifacts: {base}. Review quality.json; execution alone does not certify accuracy."
        )
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        for log in logs:
            log.close()


if __name__ == "__main__":
    main()
