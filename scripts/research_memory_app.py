"""Launch task-owned synthetic app/worker, capture via browser, evaluate, then stop.

This opt-in experiment calls paid APIs. It never connects to a live robot and
requires environments, pinned source, frontend and Chromium to be prepared.
"""

import argparse
import os
from pathlib import Path
import subprocess
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-paid-api", action="store_true", required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not os.environ.get("OPENAI_API_KEY"):
        parser.error("Export OPENAI_API_KEY; no fallback.")
    base = args.directory.resolve()
    if base.exists():
        parser.error(
            "Choose a NEW disposable output directory; existing state is never deleted."
        )
    # Refuse a conflicting listener instead of connecting acceptance to a service
    # this command did not create.
    import socket

    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 18767)) == 0:
            parser.error(
                "Port 18767 is already in use. Stop only its task-owned server first."
            )
    base.mkdir(parents=True)
    env = {
        **os.environ,
        "PYTHONPATH": str(root),
        "CUDA_VISIBLE_DEVICES": "-1",
        "MPLBACKEND": "Agg",
        "PUPPYPI_MEMORY_ENABLED": "1",
        "TEACH_FIND_DATA_DIR": str(base / "state"),
        "PUPPYPI_MEMORY_ACCEPTANCE_DIR": str(base),
        "PUPPYPI_ALLOW_PAID_API": "1",
        "PUPPYPI_MIND_PALACE_PATH": str(root / ".upstream/mind-palace"),
    }
    children = []
    logs = []
    try:
        for name, command in [
            (
                "worker",
                [
                    str(root / ".venv-memory/bin/python"),
                    "-m",
                    "teach_and_find.memory_worker",
                ],
            ),
            (
                "app",
                [
                    str(root / ".venv-dev/bin/python"),
                    str(root / "scripts/research_memory_app_server.py"),
                ],
            ),
        ]:
            log = (base / (name + ".log")).open("w")
            logs.append(log)
            child_env = env.copy()
            if name == "app":
                child_env.pop("OPENAI_API_KEY", None)
            children.append(
                subprocess.Popen(
                    command, cwd=root, env=child_env, stdout=log, stderr=log
                )
            )
        for _ in range(100):
            if any(child.poll() is not None for child in children):
                raise RuntimeError(
                    "Acceptance process exited; inspect app.log / worker.log."
                )
            try:
                urllib.request.urlopen("http://127.0.0.1:18767/", timeout=1).close()
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise TimeoutError("Acceptance app did not start.")
        subprocess.run(
            ["node", "scripts/research_memory_app_capture.mjs"],
            cwd=root,
            env=env,
            check=True,
            timeout=900,
        )
        subprocess.run(
            [
                str(root / ".venv-memory/bin/python"),
                "scripts/research_memory_app_eval.py",
                "--allow-paid-api",
                "--directory",
                str(base),
            ],
            cwd=root,
            env=env,
            check=True,
            timeout=1500,
        )
        subprocess.run(
            ["node", "scripts/research_memory_app_capture.mjs", "--screenshots-only"],
            cwd=root,
            env=env,
            check=True,
            timeout=120,
        )
        print(
            f"Artifacts: {base}. Correctness requires source-image review, not exit code alone."
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
