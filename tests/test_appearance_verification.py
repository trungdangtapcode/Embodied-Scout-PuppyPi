"""Explicit unit fixtures for decision invariants; not model quality evidence."""

import copy
from dataclasses import replace

import pytest

from teach_and_find.config import Settings
from teach_and_find.errors import AssistantError
from teach_and_find.search_verification import assess_views, ANOMALY_FUNCTION_SHA
from teach_and_find.sim.search_device import fixture_calibration


def fixture_view(x, rejected=False):
    cfg = Settings().search
    return {
        "pose": {"x": x, "y": 1.2},
        "candidates": [
            {
                "object_id": "target",
                "detection_index": 0,
                "descriptor_supported": True,
                "floor_xy": [-0.3, 2.0],
                "crop_image_sha": "unit-test-crop",
                "matches": [
                    {"reference_index": 0, "supported": True},
                    {"reference_index": 1, "supported": True},
                ],
                "appearance": {
                    "crop_image_sha": "unit-test-crop",
                    "appearance_rejected": rejected,
                    "score": 0.7 if rejected else 0.2,
                    "provenance": {
                        "function_sha256": ANOMALY_FUNCTION_SHA,
                        "calibration_sha256": cfg.anomaly_calibration_sha256,
                    },
                },
            }
        ],
    }


def assess(views):
    return assess_views(views, "target", 2, fixture_calibration(), Settings().search)


def test_contradictory_linked_view_vetoes_even_multiple_matching_views():
    views = [fixture_view(-0.6), fixture_view(-0.3), fixture_view(0.1)]
    assert assess(views)["verdict"] == "confirmed"
    views[-1]["candidates"][0]["appearance"]["appearance_rejected"] = True
    result = assess(views)
    assert result["verdict"] == "inconclusive"
    assert result["reason"] == "appearance_not_supported_by_references"


@pytest.mark.parametrize(
    "change", ["missing", "wrong_crop", "wrong_model", "wrong_calibration", "nan"]
)
def test_no_geometric_fallback_for_missing_or_invalid_appearance(change):
    views = [fixture_view(-0.3), fixture_view(0.3)]
    candidate = views[0]["candidates"][0]
    if change == "missing":
        del candidate["appearance"]
    elif change == "wrong_crop":
        candidate["appearance"]["crop_image_sha"] = "another-capture"
    elif change == "wrong_model":
        candidate["appearance"]["provenance"]["function_sha256"] = "unknown"
    elif change == "wrong_calibration":
        candidate["appearance"]["provenance"]["calibration_sha256"] = "stale"
    else:
        candidate["appearance"]["score"] = float("nan")
    with pytest.raises(AssistantError) as error:
        assess(views)
    assert error.value.code == "SEARCH_APPEARANCE_EVIDENCE_REQUIRED"


def test_missing_isolated_environment_fails_before_any_substitute(tmp_path):
    from teach_and_find.anomaly_adapter import AppearanceVerifier
    from teach_and_find.storage import EvidenceStore

    settings = Settings()
    cfg = replace(settings.search, anomaly_python=str(tmp_path / "missing-python"))
    with EvidenceStore(tmp_path / "store") as store:
        with pytest.raises(AssistantError) as error:
            AppearanceVerifier(store, cfg, settings.vision, [], lambda: None)
        assert error.value.code == "ANOMALY_ENVIRONMENT_MISSING"


def test_unit_certificate_cannot_qualify_an_unevaluated_gallery(tmp_path):
    """Explicit fake certificate tests a gate; it is never app quality evidence."""
    from dataclasses import asdict
    import json
    from teach_and_find.search_qualification import (
        profile_signature,
        reference_scope,
        qualification_state,
    )

    cfg = Settings()
    path = tmp_path / "unit-fixture-only.json"
    cfg = replace(
        cfg,
        search=replace(
            cfg.search, quality_qualified=True, qualification_file=str(path)
        ),
    )
    payload = {
        "search_profile": asdict(cfg.search),
        "vision_profile": {**asdict(cfg.vision), "profile_version": 3},
        "camera_profile": asdict(cfg.camera),
        "control_profile": {},
        "references": [{"image_shas": ["unit-reference"]}],
        "target_reference_shas": ["unit-reference"],
    }
    calibration = fixture_calibration()
    record = {
        "schema_version": 1,
        "profile_signature": profile_signature(cfg, calibration, payload)[0],
        "all_required_cases_passed": True,
        "required_case_count": 1,
        "cases": [{"id": "unit-fixture", "passed": True}],
        "environment": {"unit_fixture": True},
        "evaluated_reference_scopes": [reference_scope(payload)],
    }
    path.write_text(json.dumps(record))
    assert qualification_state(cfg, calibration, payload)["qualified"]
    changed = copy.deepcopy(payload)
    changed["target_reference_shas"] = ["unevaluated-reference"]
    state = qualification_state(cfg, calibration, changed)
    assert not state["qualified"]
    assert state["reason"] == "REFERENCE_SET_NOT_QUALIFIED"
