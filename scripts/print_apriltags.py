"""Generate printable high-resolution tag36h11 markers for HOME and Stations A/B/C."""

from __future__ import annotations

from pathlib import Path

import cv2

from teach_and_find.apriltag_pose import AprilTagPoseEstimator


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "outputs" / "apriltags_36h11"
    out_dir.mkdir(parents=True, exist_ok=True)

    est = AprilTagPoseEstimator()
    stations = [(0, "HOME"), (1, "Station_A"), (2, "Station_B"), (3, "Station_C")]
    for tag_id, label in stations:
        img = est.generate_tag_image(tag_id, side_px=800, border_px=100)
        framed = cv2.copyMakeBorder(img, 20, 90, 20, 20, cv2.BORDER_CONSTANT, value=(255, 255, 255))
        cv2.rectangle(framed, (18, 18), (framed.shape[1] - 19, framed.shape[0] - 88), (180, 180, 180), 2)
        cv2.putText(
            framed,
            f"tag36h11 ID={tag_id} ({label}) - Print inner black square = 10.0 cm",
            (40, framed.shape[0] - 32),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.78,
            (20, 20, 20),
            2,
        )
        cv2.imwrite(str(out_dir / f"tag36h11_id{tag_id}_{label}.png"), framed)
    print(f"Saved 4 printable AprilTag sheets to {out_dir}")


if __name__ == "__main__":
    main()
