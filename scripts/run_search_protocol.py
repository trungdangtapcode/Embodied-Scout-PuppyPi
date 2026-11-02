"""Run frozen cases with bounded admission, deadlines and owned-process cleanup."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time


def execute_owned(command, root, log, cancelled, budget_s=1000):
    """Cancel only our new process group, including its server/worker/browser."""
    process = subprocess.Popen(
        command, cwd=root, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
    )
    deadline = time.monotonic() + budget_s
    reason = None
    try:
        while process.poll() is None:
            if cancelled.wait(0.1):
                reason = "batch_cancelled"
                break
            if time.monotonic() >= deadline:
                reason = "case_deadline_exceeded"
                break
    finally:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGINT)
            except ProcessLookupError:
                pass
            try:
                process.wait(15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
    return {"exit_code": process.returncode, "intervention": reason}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--workers", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--base-port", type=int, default=18810)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    directory = Path(args.output).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    cases = json.loads(Path(args.protocol).read_text())["cases"]
    cancelled = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: cancelled.set())

    def run(index, case):
        if cancelled.is_set():
            return {
                "case": case["id"],
                "exit_code": None,
                "intervention": "not_started_batch_cancelled",
            }
        command = [
            str(root / ".venv-dev/bin/python"),
            "scripts/research_search_app.py",
            "--output",
            str(directory / case["id"]),
            "--scenario",
            case["scenario"],
            "--seed",
            str(case["seed"]),
            "--appearance-seed",
            str(case.get("appearance_seed", 0)),
            "--view-budget",
            str(case.get("view_budget", 4)),
            "--readout-only",
            "--port",
            str(args.base_port + index),
        ]
        for key, flag in [
            ("target_only", "--target-only"),
            ("ambiguous_gallery", "--ambiguous-gallery"),
        ]:
            if case.get(key):
                command.append(flag)
        with (directory / (case["id"] + ".log")).open("w") as log:
            result = execute_owned(command, root, log, cancelled)
        return {"case": case["id"], **result}

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending = [pool.submit(run, index, case) for index, case in enumerate(cases)]
        for future in as_completed(pending):
            result = future.result()
            results.append(result)
            print(json.dumps(result), flush=True)
    (directory / "process-results.json").write_text(json.dumps(results, indent=2))
    if any(result["exit_code"] != 0 or result["intervention"] for result in results):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
