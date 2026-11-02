"""Native geometry regressions on authored 3D projections; no learned-model claim."""

from dataclasses import replace

import cv2
import numpy as np
import pytest

from teach_and_find.config import Settings
from teach_and_find.errors import AssistantError
from teach_and_find.lightglue_adapter import geometric_support


def test_nonplanar_correspondences_survive_without_relaxing_support_thresholds():
    rng = np.random.default_rng(20261102)
    points = rng.uniform([-1.4, -1.1, 3.0], [1.4, 1.1, 6.5], (120, 3))
    camera = np.array([[400.0, 0, 320], [0, 400.0, 240], [0, 0, 1]])
    a = cv2.projectPoints(points, np.zeros(3), np.zeros(3), camera, None)[0][:, 0]
    b = cv2.projectPoints(
        points, np.array([0.1, 0.15, 0.03]), np.array([0.6, 0.04, 0.1]), camera, None
    )[0][:, 0]
    a += rng.normal(0, 0.2, a.shape)
    b += rng.normal(0, 0.2, b.shape)
    b[-15:] = rng.uniform([0, 0], [640, 480], (15, 2))
    cfg = Settings().search
    revised = geometric_support(a, b, [640, 480], cfg)
    legacy = geometric_support(a, b, [640, 480], replace(cfg, profile_version=3))
    assert revised["supported"] and revised["inliers"] >= 95
    assert not legacy["supported"]
    assert revised["geometry_model"] == "fundamental_usac_magsac"
    assert revised["fundamental_matrix"] is not None
    assert "homography" not in revised


def test_insufficient_and_collinear_evidence_cannot_retry_planar_geometry():
    points = np.column_stack([np.arange(20), np.arange(20)]).astype(np.float32)
    for a in (points[:7], points):
        result = geometric_support(a, a + 5, [100, 100], Settings().search)
        assert not result["supported"]
        assert result["reference_coverage"] == 0
        assert "homography" not in result
    with pytest.raises(AssistantError, match="Unknown geometry"):
        geometric_support(
            points, points, [100, 100], replace(Settings().search, profile_version=999)
        )


def test_native_empty_model_is_preserved_as_unsupported_evidence():
    """Actual eight-pair framework regression, not a model-output substitute."""
    import json
    from pathlib import Path

    record = json.loads(
        (Path(__file__).parent / "fixtures/search_native_empty_model.json").read_text()
    )
    pairs = record["input"]
    result = geometric_support(pairs["a"], pairs["b"], [200, 200], Settings().search)
    assert not result["supported"]
    assert result["fundamental_matrix"] is None
    assert result["native_error"] and result["inliers"] == 0
    assert "homography" not in result
