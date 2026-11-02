"""Paired original-model replay: same app capture/gallery, explicit v2 versus v3 roles.

This is recorded-input research evidence, not a new navigation run or a fallback.
"""

import argparse
from dataclasses import replace
import json
from pathlib import Path

from teach_and_find.config import Settings
from teach_and_find.lightglue_adapter import LocalCorrespondence
from teach_and_find.storage import EvidenceStore
from teach_and_find.yoloe_adapter import YoloeAdapter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    directory = Path(args.run).resolve()
    output = Path(args.output).resolve()
    if output.exists():
        raise SystemExit("Use a new output file; preserve earlier evidence.")
    job = json.loads((directory / "app-result.json").read_text())["overview"]["runs"][0]
    cfg = Settings()
    records = []
    with EvidenceStore(directory / "store") as store:
        frames = [job["views"][0]["frame"]]
        refs = job["payload"]["references"]
        target = next(ref for ref in refs if ref["object_id"] == job["object_id"])
        for version in (2, 3):
            result = YoloeAdapter(
                replace(cfg.vision, enabled=True, profile_version=version),
                lambda *_: None,
                lambda: None,
            ).run(store, {"frames": frames, "references": refs})
            records.append(result)
        local = LocalCorrespondence(cfg.search)
        features = [
            local.extract(store.load_image(sha)) for sha in target["image_shas"]
        ]
        evidence = []
        for detection in records[1]["frames"][0]["detections"]:
            comparison = detection["reference_comparison"]
            if comparison["best_object_id"] == target["object_id"]:
                query = local.extract(store.load_image(detection["crop_image_sha"]))
                evidence.append(
                    {
                        "detection": detection,
                        "matches": [local.compare(ref, query) for ref in features],
                    }
                )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                {
                    "evidence_mode": "paired_replay_of_actual_app_capture",
                    "frame": frames[0],
                    "references": refs,
                    "target_id": target["object_id"],
                    "profiles": records,
                    "local_correspondences": evidence,
                    "local_provenance": {
                        **local.provenance,
                        "executed_calls": local.calls,
                    },
                },
                indent=2,
            )
        )
    print(
        {
            "profiles": [r["provenance"]["profile_version"] for r in records],
            "same_capture": frames[0]["frame_id"],
            "learned_match_candidates": len(evidence),
        }
    )


if __name__ == "__main__":
    main()
