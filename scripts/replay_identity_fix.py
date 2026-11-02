"""Genuine original anomaly inference on preserved real app model outputs.

Historical records remain unchanged. No evaluator identity/placement enters
inference or the decision. This is replay, not fresh navigation acceptance.
"""

import argparse
import copy
from dataclasses import replace
import json
from pathlib import Path
import shutil

from teach_and_find.anomaly_adapter import AppearanceVerifier
from teach_and_find.config import Settings, VisionSettings
from teach_and_find.search_verification import assess_views
from teach_and_find.storage import EvidenceStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    source, output = Path(args.run), Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    job = json.loads((source / "app-result.json").read_text())["overview"]["runs"][0]
    target = next(
        r for r in job["payload"]["references"] if r["object_id"] == job["object_id"]
    )
    views = copy.deepcopy(job["views"])
    # This reproducer specifically preserves the historical v3 appearance repair.
    # Supported v4 native geometry is evaluated separately, never inferred here.
    cfg = replace(Settings().search, profile_version=3)
    with EvidenceStore(output / "store") as store:
        needed = set(target["image_shas"])
        needed.update(
            c["crop_image_sha"]
            for v in views
            for c in v["candidates"]
            if c["descriptor_supported"]
        )
        for sha in needed:
            shutil.copyfile(
                source / "store/images" / (sha + ".png"),
                store.root / "images" / (sha + ".png"),
            )
        verifier = AppearanceVerifier(
            store,
            cfg,
            VisionSettings(**job["payload"]["vision_profile"]),
            target["image_shas"],
            lambda: None,
        )
        try:
            for view in views:
                selected = [c for c in view["candidates"] if c["descriptor_supported"]]
                for candidate, assessment in zip(selected, verifier.assess(selected)):
                    candidate["appearance"] = assessment
            result = assess_views(
                views,
                job["object_id"],
                len(target["image_shas"]),
                job["payload"]["calibration"],
                cfg,
            )
            prior = assess_views(
                job["views"],
                job["object_id"],
                len(target["image_shas"]),
                job["payload"]["calibration"],
                replace(cfg, profile_version=2),
            )
            (output / "result.json").write_text(
                json.dumps(
                    {
                        "evidence_mode": "recorded_synthetic_app_replay_actual_original_anomaly_inference",
                        "source_run": str(source),
                        "old_readout": prior,
                        "new_readout": result,
                        "provenance": verifier.provenance,
                        "views": views,
                    },
                    indent=2,
                )
            )
            print(
                json.dumps(
                    {
                        "old": prior["verdict"],
                        "new": result["verdict"],
                        "reason": result.get("reason"),
                    }
                )
            )
        finally:
            verifier.close()


if __name__ == "__main__":
    main()
