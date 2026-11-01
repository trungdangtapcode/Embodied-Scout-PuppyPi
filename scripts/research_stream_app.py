"""Opt-in full-app CPU benchmark. Paid attempts share a durable explicit cap."""

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--allow-paid-api", action="store_true", required=True)
    parser.add_argument(
        "--max-api-calls", type=int, choices=range(1, 16), required=True
    )
    parser.add_argument("--budget-file", type=Path)
    parser.add_argument(
        "--scenario", choices=["full", "tracking-diagnostic"], default="full"
    )
    args = parser.parse_args()
    if not os.getenv("OPENAI_API_KEY"):
        parser.error("Export OPENAI_API_KEY in the worker environment; no substitute.")
    root = Path(__file__).resolve().parents[1]
    base = args.directory.resolve()
    if base.exists():
        parser.error(
            "Choose a new run directory; preserve existing attempts and evidence."
        )
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 18770)) == 0:
            parser.error("Port 18770 is occupied; refuse to use another service.")
    base.mkdir(parents=True)
    env = dict(
        os.environ,
        PYTHONPATH=str(root),
        CUDA_VISIBLE_DEVICES="-1",
        PUPPYPI_STREAM_RUN=str(base),
        TEACH_FIND_DATA_DIR=str(base / "state"),
        PUPPYPI_TRACKING_ENABLED="1",
        PUPPYPI_VISION_ENABLED="1",
        PUPPYPI_MEMORY_ENABLED="1",
        PUPPYPI_TRACKING_SOURCES=str(
            root / "runs/interactive-tracking-research-2026-11-02"
        ),
        PUPPYPI_MEMORY_BUDGET_FILE=str(
            args.budget_file.resolve()
            if args.budget_file
            else base / "paid-attempts.json"
        ),
        PUPPYPI_STREAM_SCENARIO=args.scenario,
        PUPPYPI_MEMORY_GLOBAL_CALL_BUDGET=str(args.max_api_calls),
        PUPPYPI_ALLOW_PAID_API="1",
    )
    processes = []
    logs = []
    try:
        for name, command in [
            ("server", [".venv-dev/bin/python", "scripts/research_stream_server.py"]),
            (
                "tracking-worker",
                [".venv-tracking/bin/python", "-m", "teach_and_find.tracking_worker"],
            ),
            (
                "vision-worker",
                [".venv-vision/bin/python", "-m", "teach_and_find.vision_worker"],
            ),
            (
                "memory-worker",
                [".venv-memory/bin/python", "-m", "teach_and_find.memory_worker"],
            ),
        ]:
            log = (base / f"{name}.log").open("w")
            logs.append(log)
            child_env = env.copy()
            if name != "memory-worker":
                child_env.pop("OPENAI_API_KEY", None)
            processes.append(
                subprocess.Popen(
                    command, cwd=root, env=child_env, stdout=log, stderr=log
                )
            )
        (base / "processes.json").write_text(json.dumps([p.pid for p in processes]))
        for _ in range(120):
            if any(p.poll() is not None for p in processes):
                raise RuntimeError("Task process exited: inspect logs; no fallback.")
            try:
                urllib.request.urlopen(
                    "http://127.0.0.1:18770/api/health", timeout=1
                ).close()
                break
            except OSError:
                time.sleep(0.25)
        else:
            raise TimeoutError("App unavailable.")
        result = subprocess.run(
            ["node", "scripts/research_stream_app.mjs"], cwd=root, env=env, timeout=900
        )
        if result.returncode:
            raise RuntimeError("Browser benchmark failed; evidence retained.")
    finally:
        for p in processes:
            if p.poll() is None:
                p.terminate()
        for p in processes:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        for log in logs:
            log.close()
        (base / "cleanup.json").write_text(
            json.dumps(
                {"task_processes_stopped": all(p.poll() is not None for p in processes)}
            )
        )


if __name__ == "__main__":
    main()
