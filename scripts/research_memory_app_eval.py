"""Opt-in paired evaluation against an already populated synthetic acceptance app.

Uses genuine product jobs plus a clearly named direct-all-images model baseline.
Expected labels are never sent to either path. No automatic correctness score is
invented: save answers, source-linked citations, cost and latency for review.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import time
import urllib.request
from uuid import uuid4

from teach_and_find.config import Settings
from teach_and_find.mind_palace_adapter import (
    MindPalaceAdapter,
    ModelTransport,
    enum,
    object_schema,
    TEXT,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-paid-api", action="store_true", required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--token", default="synthetic-memory-acceptance")
    args = parser.parse_args()
    if not os.environ.get("OPENAI_API_KEY"):
        parser.error(
            "Export OPENAI_API_KEY in the evaluation environment; no fallback."
        )
    root = args.directory.resolve()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )

    def api(path, payload=None):
        request = urllib.request.Request(
            "http://127.0.0.1:18767/api/" + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={
                "Content-Type": "application/json",
                "Origin": "http://127.0.0.1:18767",
            },
        )
        with opener.open(request, timeout=10) as response:
            return json.load(response)

    api("session", {"token": args.token})
    overview = api("memory")
    if overview["mode"] != "synthetic" or not overview["worker"]["alive"]:
        parser.error(
            "This evaluation requires the disposable synthetic app and an active worker."
        )
    captures = overview["captures"]
    if (
        len(captures) != 6
        or len(overview["episodes"]) != 3
        or len(overview["views"]) != 2
    ):
        parser.error(
            "Expected exactly three episodes, two viewpoints and six captures."
        )
    cfg = Settings()
    cfg = replace(
        cfg, memory=replace(cfg.memory, enabled=True, model=overview["model"])
    )
    images = [
        MindPalaceAdapter.image(
            c, root / "state" / "images" / (c["image_sha"] + ".png")
        )
        for c in captures
    ]
    task_path = (
        Path(__file__).resolve().parents[1]
        / "docs/research/2026-11-01-mind-palace-app/tasks.json"
    )
    raw = task_path.read_bytes()
    tasks = json.loads(raw)
    records = []
    output = root / "paired-evaluation.json"
    for task in tasks["tasks"]:
        started = time.monotonic()
        job = api(
            "memory/questions",
            {
                "question": task["question"],
                "episode_ids": [e["id"] for e in overview["episodes"]],
                "request_key": str(uuid4()),
            },
        )
        while job["status"] in {"queued", "running"}:
            if (
                time.monotonic() - started
                > cfg.memory.job_timeout_s + cfg.memory.request_timeout_s + 30
            ):
                raise TimeoutError(
                    "The app evaluation exceeded its bounded wait; inspect the saved job."
                )
            time.sleep(0.5)
            job = api("memory/jobs/" + job["id"])
        steps = []
        transport = ModelTransport(
            cfg,
            lambda stage, record: steps.append({"stage": stage, **record}),
            lambda: None,
        )
        transport.prepare(
            "baseline",
            object_schema(
                {
                    "answerable": enum(["yes", "no"]),
                    "answer": TEXT,
                    "citations": {
                        "type": "array",
                        "items": enum([c["id"] for c in captures]),
                        "maxItems": 6,
                    },
                }
            ),
            images,
        )
        baseline_started = time.monotonic()
        # Same six raw PNGs, shared Luna descriptions and requested model. The
        # baseline has one direct reasoning call; it does not pretend to retrieve.
        transport.call(
            [
                {
                    "role": "user",
                    "content": task["question"]
                    + "\nShared model descriptions: "
                    + json.dumps(
                        [
                            {"id": c["id"], "description": c["description"]}
                            for c in captures
                        ]
                    )
                    + "\nUse only these images; cite capture IDs. Mark answerable=no if no visual witness supports the requested answer.",
                }
            ]
        )
        record = {
            "task_id": task["id"],
            "question": task["question"],
            "app": job,
            "app_wall_s": round(
                (
                    datetime.fromisoformat(job["finished_at"])
                    - datetime.fromisoformat(job["created_at"])
                ).total_seconds(),
                3,
            ),
            "baseline": {
                "name": "direct_all_images_same_model",
                "output": transport.last,
                "elapsed_s": round(time.monotonic() - baseline_started, 3),
                "steps": steps,
            },
            "correctness": "not automatically scored; source-image review required",
        }
        records.append(record)
        output.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "input_mode": "synthetic",
                    "model": overview["model"],
                    "tasks_sha256": hashlib.sha256(raw).hexdigest(),
                    "shared_capture_ids": [c["id"] for c in captures],
                    "budget_per_app_question": cfg.memory.max_calls,
                    "description_cost_shared": True,
                    "records": records,
                },
                indent=2,
            )
            + "\n"
        )
        print(
            json.dumps(
                {
                    "task": task["id"],
                    "app_status": job["status"],
                    "baseline_answerable": transport.last["answerable"],
                }
            ),
            flush=True,
        )

    checks = {}
    # Cooperative cancellation while a genuine upstream call is in flight.
    job = api(
        "memory/questions",
        {
            "question": tasks["tasks"][0]["question"],
            "episode_ids": [e["id"] for e in overview["episodes"]],
            "request_key": str(uuid4()),
        },
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        job = api("memory/jobs/" + job["id"])
        if any(step.get("event") == "started" for step in job["steps"]):
            break
        time.sleep(0.05)
    checks["before_cancel"] = job
    before_stop = time.monotonic()
    checks["stop_response"] = api("stop", {})
    checks["stop_elapsed_s"] = round(time.monotonic() - before_stop, 4)
    checks["cancel_response"] = api("memory/jobs/" + job["id"] + "/cancel", {})
    time.sleep(5)
    checks["after_cancel"] = api("memory/jobs/" + job["id"])
    # New, explicitly covered frame; no previous image or caption is substituted.
    episode = api("memory/episodes", {"name": "Occluded fixture"})
    (root / "current-scene.txt").write_text("6")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        state = api("state")
        if state["camera"]["provenance"].get("fixture_index") == 6:
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("Occlusion fixture did not reach the actual camera path.")
    view = next(v for v in overview["views"] if v["region_name"] == "Desk")
    capture = api(
        "memory/captures",
        {
            "episode_id": episode["id"],
            "view_id": view["id"],
            "frame_id": state["camera"]["frame_id"],
            "request_key": str(uuid4()),
        },
    )
    deadline = time.monotonic() + 400
    while capture["status"] in {"queued", "running"} and time.monotonic() < deadline:
        time.sleep(0.5)
        capture = api("memory/jobs/" + capture["id"])
    checks["occluded_description"] = capture
    if capture["status"] != "succeeded":
        raise RuntimeError("Occlusion description failed; no substitute is allowed.")
    job = api(
        "memory/questions",
        {
            "question": "Does this saved Desk capture visibly show a red target-marked object? Give a visual witness only if it is visible. Do not infer hidden or current state.",
            "episode_ids": [episode["id"]],
            "request_key": str(uuid4()),
        },
    )
    deadline = time.monotonic() + 400
    while job["status"] in {"queued", "running"} and time.monotonic() < deadline:
        time.sleep(0.5)
        job = api("memory/jobs/" + job["id"])
    checks["occluded_question"] = job
    source = root / "state" / "images" / (captures[0]["image_sha"] + ".png")
    hidden = source.with_suffix(".temporarily-hidden")
    source.rename(hidden)
    try:
        missing = api(
            "memory/questions",
            {
                "question": "What is visible in this saved episode?",
                "episode_ids": [captures[0]["episode_id"]],
                "request_key": str(uuid4()),
            },
        )
        deadline = time.monotonic() + 400
        while (
            missing["status"] in {"queued", "running"} and time.monotonic() < deadline
        ):
            time.sleep(0.5)
            missing = api("memory/jobs/" + missing["id"])
        if missing["status"] in {"queued", "running"}:
            api("memory/jobs/" + missing["id"] + "/cancel", {})
            raise TimeoutError("Missing-source check did not terminate.")
        checks["missing_image"] = missing
    finally:
        hidden.rename(source)
    (root / "failure-checks.json").write_text(json.dumps(checks, indent=2) + "\n")
    print(
        json.dumps(
            {
                "cancel": checks["after_cancel"]["status"],
                "occluded": job["status"],
                "stop_elapsed_s": checks["stop_elapsed_s"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
