"""Plot actual captured inputs, visual localization and learned correspondences."""

import argparse
import json
import math
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    args = parser.parse_args()
    root = Path(args.directory).resolve()
    run = json.loads((root / "app-result.json").read_text())["overview"]["runs"][0]
    truth = json.loads((root / "evaluation-truth.json").read_text())
    poses = []
    for event in run["events"]:
        if event["kind"] == "pose_observed":
            record = json.loads(event["record_json"])
            poses.append(record)
    gt = {f["frame_id"]: f["pose"] for f in truth["frames"]}
    errors = []
    for record in poses:
        if record["frame_id"] not in gt:
            continue
        real, observed = gt[record["frame_id"]], record["pose"]
        position = math.dist(real[:2], [observed["x"], observed["y"]])
        yaw_error = math.degrees(
            math.atan2(
                math.sin(math.radians(real[2]) - observed["yaw"]),
                math.cos(math.radians(real[2]) - observed["yaw"]),
            )
        )
        errors.append([position, abs(yaw_error)])
    actual = np.array([r["pose"] for r in truth["trajectory"]])
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    axes[0].plot(actual[:, 0], actual[:, 1], label="Renderer truth (evaluation only)")
    axes[0].plot(
        [r["pose"]["x"] for r in poses],
        [r["pose"]["y"] for r in poses],
        ".",
        markersize=2,
        label="AprilTag pixel localization",
    )
    for station in run["payload"]["calibration"]["stations"]:
        goals = np.array(station["goals"])
        axes[0].scatter(
            goals[:, 0],
            goals[:, 1],
            marker="x",
            label=station["id"] + " supplied goals",
        )
    axes[0].set(
        xlabel="x (m)",
        ylabel="y (m)",
        title="Measured command-integrated motion and visual estimates",
    )
    axes[0].axis("equal")
    axes[0].legend(fontsize=7)
    if errors:
        axes[1].plot(np.array(errors)[:, 0] * 100)
    axes[1].set(
        xlabel="Matched observed capture",
        ylabel="Position error (cm)",
        title="Capture-ID paired pose error",
    )
    fig.suptitle(
        "SYNTHETIC KINEMATIC INPUT · actual navigation execution · "
        + run["status"].upper()
        + " / "
        + ((run.get("result") or {}).get("verdict") or "no verdict").upper(),
        fontsize=11,
    )
    fig.tight_layout()
    fig.savefig(root / "navigation.png", dpi=160)
    plt.close(fig)
    columns = max(1, len(run["views"]))
    fig, axes = plt.subplots(1, columns, figsize=(5 * columns, 4), squeeze=False)
    for index, view in enumerate(run["views"]):
        image = cv2.imread(
            str(root / "store/images" / (view["frame"]["image_sha"] + ".png"))
        )
        axes[0, index].imshow(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        axes[0, index].axis("off")
        axes[0, index].set_title(
            f"Actual capture {index + 1}\n{len(view['candidates'])} target-prompt candidates",
            fontsize=10,
        )
    fig.suptitle(
        "Rendered camera pixels captured AFTER executed motion · no authored inference labels"
    )
    fig.tight_layout()
    fig.savefig(root / "captured-views.png", dpi=140)
    plt.close(fig)
    summary = {
        "run_status": run["status"],
        "verdict": run["result"],
        "error": run["error"],
        "matched_pose_captures": len(errors),
        "reached_inferred_views": len(run["views"]),
        "evaluation_boundary_collision_events": truth["collisions"]
        if truth.get("collision_measurement")
        else None,
        "position_error_m": {
            "p50": float(np.percentile(np.array(errors)[:, 0], 50)),
            "p95": float(np.percentile(np.array(errors)[:, 0], 95)),
            "max": float(np.max(np.array(errors)[:, 0])),
        }
        if errors
        else None,
    }
    (root / "metrics.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k != "verdict"}))


if __name__ == "__main__":
    main()
