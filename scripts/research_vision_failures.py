"""Send explicit bad-artifact snapshots through the real vision queue/worker."""

import argparse
from dataclasses import replace
import json
from pathlib import Path
import time

from teach_and_find.camera import CameraFrame
from teach_and_find.config import Settings
from teach_and_find.memory_queue import dispatch
from teach_and_find.storage import EvidenceStore
from teach_and_find.vision_service import VisionService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    base = parser.parse_args().directory.resolve()
    cfg = Settings()
    cfg = replace(
        cfg,
        assistant=replace(cfg.assistant, data_dir=str(base / "state")),
        vision=replace(cfg.vision, enabled=True),
    )
    original = json.loads((base / "app-runs.json").read_text())[0]["job"]
    corrupt = base / "explicit-corrupt-checkpoint.pt"
    corrupt.write_bytes(
        b"This is an explicitly invalid acceptance artifact, not a model."
    )
    cases = [
        (
            "missing-source",
            replace(cfg.vision, upstream_path=str(base / "missing-source")),
            "VISION_SOURCE_MISSING",
        ),
        (
            "missing-checkpoint",
            replace(cfg.vision, checkpoint=str(base / "missing-checkpoint.pt")),
            "VISION_CHECKPOINT_MISSING",
        ),
        (
            "corrupt-checkpoint",
            replace(cfg.vision, checkpoint=str(corrupt)),
            "VISION_CHECKPOINT_MISMATCH",
        ),
    ]
    reports = []
    for name, profile, expected in cases:
        bad_cfg = replace(cfg, vision=profile)
        with EvidenceStore(cfg.assistant.data_dir) as store:
            service = VisionService(store, bad_cfg)
            internal = service.job(original["id"], "synthetic", internal=True)
            source = internal["payload"]["frames"]
            frames = [
                CameraFrame(
                    store.load_image(f["image_sha"]),
                    f["frame_id"],
                    f["captured_at"],
                    time.monotonic(),
                    0.0,
                    True,
                    f["provenance"],
                )
                for f in source
            ]
            ids = [r["object_id"] for r in internal["payload"]["references"]]
            job = service.enqueue(frames, ids, "artifact-failure-" + name, "synthetic")
        dispatch(cfg, job["id"], "vision")
        for _ in range(200):
            with EvidenceStore(cfg.assistant.data_dir) as store:
                record = VisionService(store, cfg).job(job["id"], "synthetic")
            if record["status"] not in {"running", "queued"}:
                break
            time.sleep(0.1)
        assert record["status"] == "failed" and record["error_code"] == expected, record
        assert record["result"] is None
        reports.append({"case": name, "job": record})
    (base / "artifact-failures.json").write_text(json.dumps(reports, indent=2))
    print(
        "Three genuine worker artifact failures persisted with no substitute results."
    )


if __name__ == "__main__":
    main()
