"""Create a local synthetic object library, history, and portable inspection report."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import numpy as np

from teach_and_find.config import Settings
from teach_and_find.inspection import InspectionService
from teach_and_find.library import build_library
from teach_and_find.sim.world3d import build_object_catalog, render_teaching_views
from teach_and_find.storage import EvidenceStore


def main() -> None:
    settings = Settings()
    # The demo always uses the deterministic offline backend, even if a model
    # backend has been selected in the operator's environment.
    settings = replace(
        settings,
        perception=replace(settings.perception, encoder_backend="spatial_appearance"),
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path(settings.assistant.demo_output_dir)
    )
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix="run-", dir=args.output)).resolve()
    settings = replace(
        settings, assistant=replace(settings.assistant, data_dir=str(run / "state"))
    )
    now = datetime.now(timezone.utc)
    rng = np.random.default_rng(args.seed)
    catalog = build_object_catalog()
    keys = ("secret_box_1", "blue_tool_case", "emerald_med_kit", "amber_sensor_cube")
    records, views = {}, {}
    with EvidenceStore(settings.assistant.data_dir) as store:
        library = build_library(store, settings)
        for key in keys:
            taught = render_teaching_views(catalog[key], settings.camera, rng=rng)
            views[key] = taught[len(taught) // 2][1]
            records[key] = library.teach(
                catalog[key].display_name,
                [crop for _, crop in taught],
                [angle for angle, _ in taught],
            )

        def observe(key, station, assertion, seconds_ago, *, visibility=1.0):
            crop = views[key].copy()
            if assertion == "absent":
                crop[:] = 235
            elif visibility < settings.assistant.minimum_visibility:
                crop[:, : int(crop.shape[1] * 0.8)] = 45
            library.observe(
                records[key]["id"],
                station,
                assertion,
                crop,
                (now - timedelta(seconds=seconds_ago)).isoformat(),
                visibility=visibility,
                source="synthetic",
                mode="synthetic",
            )

        observe(keys[0], "Station_A", "present", 600)
        observe(keys[0], "Station_B", "present", 10)
        observe(keys[1], "Station_C", "absent", 10)
        observe(keys[2], "Station_B", "absent", 10, visibility=0.2)
        observe(keys[3], "Station_A", "present", 10)
        checklist = InspectionService(library).create_checklist(
            "Synthetic workspace inspection",
            [
                (records[key]["id"], station)
                for key, station in zip(
                    keys, ("Station_A", "Station_C", "Station_B", "Station_A")
                )
            ],
        )

    # Reopen from disk; the report must use persisted state, not live Python objects.
    with EvidenceStore(settings.assistant.data_dir) as reopened:
        library = build_library(reopened, settings)
        service = InspectionService(library)
        report = service.run(checklist["id"], mode="synthetic", as_of=now.isoformat())
        exported = service.export(report["id"], run / "report")
        history = library.history(records[keys[0]]["id"])
        signature = library.signature
    if report["summary"] != {"pass": 1, "fail": 2, "unknown": 1}:
        raise RuntimeError(f"Unexpected synthetic demo outcome: {report['summary']}")
    root = Path(__file__).resolve().parents[1]

    def git(*arguments):
        result = subprocess.run(
            ["git", *arguments], cwd=root, text=True, capture_output=True, check=True
        )
        return result.stdout.strip()

    manifest = {
        "schema_version": 1,
        "evidence_mode": "synthetic",
        "seed": args.seed,
        "commit": git("rev-parse", "HEAD"),
        "dirty": bool(git("status", "--porcelain")),
        "lock_sha256": hashlib.sha256((root / "uv.lock").read_bytes()).hexdigest(),
        "settings": asdict(settings),
        "encoder_signature": signature,
        "summary": report["summary"],
        "report_id": report["id"],
        "checklist_id": checklist["id"],
        "objects": {key: row["id"] for key, row in records.items()},
        "report": "report/report.html",
        "database": "state/assistant.sqlite3",
        "limitation": "Scripted observation assertions on rendered crops; not perception accuracy or physical execution.",
    }
    (run / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    (run / "location-history.json").write_text(
        json.dumps(history, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "run": str(run),
                "report": exported["html"],
                "summary": report["summary"],
                "evidence_mode": "synthetic",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
