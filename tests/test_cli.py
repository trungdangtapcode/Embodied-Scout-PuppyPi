"""Operator workflows across independent CLI processes."""

import json
import os
import subprocess
import sys

import cv2
import numpy as np


def test_operator_workflow_and_stable_errors(tmp_path):
    image_path = tmp_path / "crop.png"
    cv2.imwrite(
        str(image_path),
        np.random.default_rng(1).integers(0, 256, (80, 80, 3), dtype=np.uint8),
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("TEACH_FIND_")
    }
    environment["TEACH_FIND_ENCODER_BACKEND"] = "spatial_appearance"

    def call(*arguments, succeeds=True):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "teach_and_find",
                "--data-dir",
                str(tmp_path / "state"),
                *arguments,
            ],
            env=environment,
            text=True,
            capture_output=True,
        )
        assert result.returncode == (0 if succeeds else 2), result.stderr
        return json.loads(result.stdout if succeeds else result.stderr)

    obj = call("objects", "teach", "--name", "Pouch", "--images", str(image_path))
    object_id = obj["id"]
    assert call("objects", "list")[0]["id"] == object_id
    assert call("objects", "match", str(image_path))[0]["decision"] == "candidate_only"
    call(
        "observe",
        "--object-id",
        object_id,
        "--station",
        "A",
        "--assertion",
        "present",
        "--image",
        str(image_path),
        "--captured-at",
        "2026-01-01T12:03:00Z",
    )
    assert call("last-seen", object_id)["last_seen"]["station"] == "A"
    assert len(call("history", object_id)) == 1
    checklist = call(
        "checklists", "create", "--name", "Lab", "--item", f"{object_id}@A"
    )
    report = call("inspect", checklist["id"], "--as-of", "2026-01-01T12:05:00Z")
    assert report["summary"]["pass"] == 1
    call("export", report["id"], "--output", str(tmp_path / "export"))
    assert (tmp_path / "export/report.html").exists()
    call("objects", "rename", object_id, "Renamed")
    call("objects", "archive", object_id)
    assert call("objects", "list") == []
    error = call("objects", "rename", object_id, "Missing", succeeds=False)
    assert error["error"]["code"] == "OBJECT_NOT_FOUND"
