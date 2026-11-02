"""Fit the declared original sklearn scalar classifier on disclosed development data."""

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

from teach_and_find.anomaly_model import fit_decision, FUNCTION_SHA


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    probe = json.loads(Path(args.probe).read_text())
    samples = []
    for row in probe["comparisons"]:
        if row["masking"]:
            continue
        # Explicit evaluation labels for the two preserved authored development
        # fixtures. These labels never enter original inference or app requests.
        name = Path(row["run"]).name
        if name not in {"search-segment-fixed-2026-11-02", "unknown-hidden-808"}:
            raise ValueError(
                "Undeclared development fixture; inspect and register its labels first."
            )
        samples.append(
            {
                "score": row["original_top1percent_score"],
                "appearance_rejected": int(name == "unknown-hidden-808"),
                "run": row["run"],
                "view": row["view"],
                "crop_image_sha": row["crop_image_sha"],
                "reference_shas": row["reference_shas"],
            }
        )
    record = {
        "schema_version": 1,
        "scope": "authored_box_development_only_not_quality_qualification",
        "scoring": {
            "function_sha256": FUNCTION_SHA,
            "resolution": 672,
            "masking": False,
            "rotation": False,
        },
        "samples": samples,
        "sklearn_version": importlib.metadata.version("scikit-learn"),
        "fit": {
            "entry_point": "sklearn.tree.DecisionTreeClassifier.fit",
            "params": {"max_depth": 1, "random_state": 0},
            "data_source_sha256": hashlib.sha256(
                Path(args.probe).read_bytes()
            ).hexdigest(),
        },
    }
    tree = fit_decision(record)
    record["fitted_tree"] = {
        "threshold": tree.tree_.threshold.tolist(),
        "feature": tree.tree_.feature.tolist(),
        "values": tree.tree_.value.tolist(),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")
    print(
        json.dumps(
            {
                "samples": len(samples),
                "threshold": tree.tree_.threshold.tolist(),
                "artifact_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            }
        )
    )


if __name__ == "__main__":
    main()
