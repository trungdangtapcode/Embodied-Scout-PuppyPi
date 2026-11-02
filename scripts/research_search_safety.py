"""Opt-in genuine-model safety probes on owned synthetic host/worker processes."""

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from uuid import uuid4

import cv2
import httpx
import numpy as np

from teach_and_find.config import Settings
from teach_and_find.sim.world3d import build_object_catalog, render_teaching_views


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--port", type=int, default=18789)
    parser.add_argument(
        "--fault",
        choices=(
            "missing-source",
            "missing-env",
            "corrupt-fit",
            "corrupt-cache",
            "stop-inference",
        ),
        required=True,
    )
    args = parser.parse_args()
    root, output = Path(__file__).resolve().parents[1], Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    env = {
        **os.environ,
        "PUPPYPI_OPERATOR_TOKEN": "search-safety-disposable",
        "TEACH_FIND_DATA_DIR": str(output / "store"),
        "PUPPYPI_SEARCH_ENABLED": "1",
        "PUPPYPI_VISION_ENABLED": "1",
        "PUPPYPI_SEARCH_HOST": f"http://127.0.0.1:{args.port}",
        "PUPPYPI_SEARCH_SCENARIO": "target",
        "PUPPYPI_SEARCH_SIM_SEED": "42",
        "PUPPYPI_SEARCH_APPEARANCE_SEED": "0",
        "CUDA_VISIBLE_DEVICES": "-1",
        "PYTHONPATH": str(root),
    }
    codes = {
        "missing-source": "ANOMALYDINO_SOURCE_MISSING",
        "missing-env": "ANOMALY_ENVIRONMENT_MISSING",
        "corrupt-fit": "ANOMALY_CALIBRATION_CHECKPOINT_MISMATCH",
        "corrupt-cache": "ANOMALY_LOADED_CHECKPOINT_MISMATCH",
    }
    if args.fault == "missing-source":
        env["PUPPYPI_ANOMALY_SOURCE"] = str(output / "missing-source")
    if args.fault == "missing-env":
        env["PUPPYPI_ANOMALY_PYTHON"] = str(output / "missing-python")
    if args.fault == "corrupt-fit":
        (output / "corrupt.json").write_text("{}")
        env["PUPPYPI_ANOMALY_CALIBRATION"] = str(output / "corrupt.json")
    if args.fault == "corrupt-cache":
        env["TORCH_HOME"] = str(output / "isolated-torch-cache")
        cache_file = (
            Path(env["TORCH_HOME"]) / "hub/checkpoints/dinov2_vits14_pretrain.pth"
        )
        cache_file.parent.mkdir(parents=True)
        script = "import torch,sys; state=torch.load(sys.argv[1],map_location='cpu',weights_only=True); key=next(k for k,v in state.items() if v.is_floating_point()); state[key]=state[key]+.01; torch.save(state,sys.argv[2])"
        subprocess.run(
            [
                str(root / Settings().search.anomaly_python),
                "-c",
                script,
                Settings().vision.descriptor_checkpoint,
                str(cache_file),
            ],
            cwd=root,
            check=True,
        )
    processes, logs = [], []
    report = {
        "fault": args.fault,
        "mode": "synthetic_genuine_required_models",
        "paid_api_calls": 0,
        "hardware": False,
    }
    try:
        for name, command in [
            (
                "server",
                [
                    str(root / ".venv-dev/bin/python"),
                    "scripts/search_sim_server.py",
                    "--output",
                    str(output / "evaluation-truth.json"),
                    "--port",
                    str(args.port),
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
            logs.append((output / (name + ".log")).open("w"))
            child_env = dict(env)
            if name == "worker":
                for key in (
                    "PUPPYPI_SEARCH_SCENARIO",
                    "PUPPYPI_SEARCH_SIM_SEED",
                    "PUPPYPI_SEARCH_APPEARANCE_SEED",
                ):
                    child_env.pop(key)
            processes.append(
                subprocess.Popen(
                    command,
                    cwd=root,
                    env=child_env,
                    stdout=logs[-1],
                    stderr=subprocess.STDOUT,
                )
            )
        with httpx.Client(base_url=env["PUPPYPI_SEARCH_HOST"], timeout=3) as client:
            deadline = time.monotonic() + 20
            while True:
                try:
                    client.post(
                        "/api/session", json={"token": env["PUPPYPI_OPERATOR_TOKEN"]}
                    ).raise_for_status()
                    if client.get("/api/search").json().get("worker", {}).get("alive"):
                        break
                except (httpx.HTTPError, AttributeError):
                    pass
                if time.monotonic() > deadline:
                    raise RuntimeError("Required host/worker did not start.")
                time.sleep(0.1)
            views = render_teaching_views(
                build_object_catalog()["secret_box_1"],
                Settings().camera,
                rng=np.random.default_rng(7),
            )[1:4]
            files = [
                (
                    "files",
                    (
                        f"reference-{i}.png",
                        cv2.imencode(".png", image)[1].tobytes(),
                        "image/png",
                    ),
                )
                for i, (_, image) in enumerate(views)
            ]
            response = client.post(
                "/api/objects", data={"name": "Safety probe target"}, files=files
            )
            response.raise_for_status()
            target = response.json()
            response = client.post(
                "/api/search",
                json={"object_id": target["id"], "request_key": str(uuid4())},
            )
            response.raise_for_status()
            identifier = response.json()["id"]
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                task = client.get("/api/search").json()["runs"][0]
                state = client.get("/api/state").json()
                if (
                    args.fault == "stop-inference"
                    and task["stage"] == "frame_inferred"
                    and not state["control"]["armed"]
                ):
                    report["before_stop"] = {"task": task, "state": state}
                    started = time.monotonic()
                    client.post("/api/stop").raise_for_status()
                    report["stop_request_ms"] = (time.monotonic() - started) * 1000
                    break
                if task["status"] not in ("queued", "running"):
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("Safety probe deadline exceeded.")
            response = client.get(f"/api/search/{identifier}?export=true")
            response.raise_for_status()
            observed = response.json()
            count = len(observed["views"])
            time.sleep(1.5)
            later = client.get(f"/api/search/{identifier}?export=true").json()
            overview, state = (
                client.get("/api/search").json(),
                client.get("/api/state").json(),
            )
            assert not state["control"]["armed"]
            assert not any(
                state["control"]["command"][key]
                for key in ("vx_cm_s", "vy_cm_s", "yaw_rate_rad_s")
            )
            assert not overview["sightings"]
            if args.fault == "stop-inference":
                assert (
                    "before_stop" in report
                    and observed["status"] == later["status"] == "cancelled"
                )
                assert len(later["views"]) == count
            else:
                assert (
                    later["status"] == "failed"
                    and later["error"]["code"] == codes[args.fault]
                )
                assert not later["views"]
                assert not any(e["kind"] == "route_planned" for e in later["events"])
            report.update(
                {"passed": True, "final_task": later, "final_control": state["control"]}
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
        (output / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({"fault": args.fault, "passed": report.get("passed", False)}))


if __name__ == "__main__":
    main()
