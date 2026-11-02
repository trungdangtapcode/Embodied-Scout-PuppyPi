"""Opt-in actual qualified publication on an already evaluated gallery, no bypass."""

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import time

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--qualification", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--port", type=int, default=18950)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source, output = Path(args.run).resolve(), Path(args.output).resolve()
    certificate = Path(args.qualification).resolve()
    record = json.loads(certificate.read_text())
    if record.get("all_required_cases_passed") is not True:
        raise ValueError("Actual all-case qualification is mandatory; no substitute.")
    output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((source / "manifest.json").read_text())
    job = json.loads((source / "app-result.json").read_text())["overview"]["runs"][0]
    store = output / "store"
    store.mkdir()
    # Preserve exact enrolled bytes/order without modifying the historical run.
    with (
        sqlite3.connect(
            (source / "store/assistant.sqlite3").as_uri() + "?mode=ro", uri=True
        ) as old,
        sqlite3.connect(store / "assistant.sqlite3") as new,
    ):
        old.backup(new)
    shutil.copytree(source / "store/images", store / "images")
    env = {
        **os.environ,
        "PYTHONPATH": str(root),
        "CUDA_VISIBLE_DEVICES": "-1",
        "PUPPYPI_OPERATOR_TOKEN": "qualified-search-disposable",
        "TEACH_FIND_DATA_DIR": str(store),
        "PUPPYPI_SEARCH_ENABLED": "1",
        "PUPPYPI_VISION_ENABLED": "1",
        "PUPPYPI_SEARCH_QUALITY_QUALIFIED": "1",
        "PUPPYPI_SEARCH_QUALIFICATION": str(certificate),
        "PUPPYPI_SEARCH_HOST": f"http://127.0.0.1:{args.port}",
        "PUPPYPI_SEARCH_SCENARIO": manifest["scenario"],
        "PUPPYPI_SEARCH_SIM_SEED": str(manifest["seed"]),
        "PUPPYPI_SEARCH_APPEARANCE_SEED": str(manifest["appearance_seed"]),
        "PUPPYPI_SEARCH_VIEW_BUDGET": str(manifest["view_budget"]),
    }
    (output / "provenance.json").write_text(
        json.dumps(
            {
                "source_run": str(source),
                "qualification": str(certificate),
                "gallery": "exact copied enrolled images and library, no new identity assertion",
                "new_execution": "fresh bounded simulator motion and genuine model inference",
                "paid_api_calls": 0,
                "hardware": False,
            },
            indent=2,
        )
    )
    processes, logs = [], []
    try:
        for name, command in [
            (
                "server",
                [
                    str(root / ".venv-dev/bin/python"),
                    "scripts/search_sim_server.py",
                    "--port",
                    str(args.port),
                    "--output",
                    str(output / "evaluation-truth.json"),
                ],
            ),
            (
                "worker",
                [
                    str(root / ".venv-vision/bin/python"),
                    "-m",
                    "teach_and_find.search_worker",
                ],
            ),
        ]:
            child = dict(env)
            if name == "worker":
                for key in (
                    "PUPPYPI_SEARCH_SCENARIO",
                    "PUPPYPI_SEARCH_SIM_SEED",
                    "PUPPYPI_SEARCH_APPEARANCE_SEED",
                ):
                    child.pop(key)
            logs.append((output / (name + ".log")).open("w"))
            processes.append(
                subprocess.Popen(
                    command,
                    cwd=root,
                    env=child,
                    stdout=logs[-1],
                    stderr=subprocess.STDOUT,
                )
            )
        deadline = time.monotonic() + 20
        while True:
            if any(p.poll() is not None for p in processes):
                raise RuntimeError("Required process exited; inspect logs.")
            try:
                if (
                    httpx.get(
                        env["PUPPYPI_SEARCH_HOST"] + "/api/health", timeout=0.5
                    ).status_code
                    == 200
                ):
                    break
            except httpx.HTTPError:
                pass
            if time.monotonic() > deadline:
                raise RuntimeError("Host startup deadline exceeded.")
            time.sleep(0.2)
        subprocess.run(
            [
                "node",
                "web/scripts/research-qualified-search.mjs",
                env["PUPPYPI_SEARCH_HOST"],
                str(output),
                job["object_id"],
            ],
            cwd=root,
            env=env,
            check=True,
            timeout=960,
        )
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                try:
                    process.wait(15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        for log in logs:
            log.close()


if __name__ == "__main__":
    main()
