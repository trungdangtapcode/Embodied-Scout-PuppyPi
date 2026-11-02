"""Bind automatic-memory publication to actual frozen-profile evaluation evidence.

This gate is not an inference backend. Missing, stale or invalid qualification
blocks publication with an explicit failure; it never changes the model method.
"""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from teach_and_find.config import Settings
from teach_and_find.errors import AssistantError

IDENTITY_SOURCES = (
    "dinov2_adapter.py",
    "yoloe_adapter.py",
    "lightglue_adapter.py",
    "search_navigation.py",
    "search_transport.py",
    "mobile/runtime.py",
    "mobile/api.py",
    "search_verification.py",
    "search_worker.py",
    "search_service.py",
    "search_qualification.py",
)


def identity_source_hashes():
    package = Path(__file__).resolve().parent
    return {
        name: hashlib.sha256((package / name).read_bytes()).hexdigest()
        for name in IDENTITY_SOURCES
    }


def execution_environment(views):
    records = [
        {
            "vision": {
                "torch": view["vision"]["provenance"]["torch_version"],
                **view["vision"]["provenance"]["packages"],
            },
            "local": view["local_model"]["packages"],
        }
        for view in views
    ]
    if not records or any(record != records[0] for record in records):
        raise AssistantError(
            "SEARCH_ENVIRONMENT_INCONSISTENT",
            "Per-view executed model environments differ or are missing.",
        )
    return records[0]


def control_snapshot(settings):
    mobile = settings.mobile
    return {
        "linear_speed_m_s": mobile.manual_speed_cm_s / 100,
        "yaw_rate_rad_s": mobile.manual_yaw_rate_rad_s,
        "command_lease_s": mobile.command_lease_s,
        "control_challenge_s": mobile.control_challenge_s,
        "control_tick_s": mobile.control_tick_s,
        "max_frame_age_s": mobile.max_frame_age_s,
        "frame_poll_s": mobile.frame_poll_s,
        "jpeg_quality": mobile.jpeg_quality,
    }


def profile_signature(settings: Settings, calibration: dict, payload=None):
    vision = (
        dict(payload["vision_profile"])
        if payload
        else {**asdict(settings.vision), "profile_version": 3}
    )
    search = dict(payload["search_profile"]) if payload else asdict(settings.search)
    for key in (
        "enabled",
        "upstream_path",
        "checkpoint",
        "descriptor_source",
        "descriptor_checkpoint",
        "job_timeout_s",
        "heartbeat_s",
        "worker_stale_s",
        "polling_s",
        "history_limit",
    ):
        vision.pop(key, None)
    for key in (
        "enabled",
        "robotics_source",
        "lightglue_source",
        "weights",
        "host_url",
        "quality_qualified",
        "qualification_file",
    ):
        search.pop(key, None)
    record = {
        "schema_version": 1,
        "vision": vision,
        "search": search,
        "camera": payload["camera_profile"] if payload else asdict(settings.camera),
        "control": payload["control_profile"]
        if payload
        else control_snapshot(settings),
        "calibration": calibration,
        "source_sha256": identity_source_hashes(),
    }
    digest = hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return digest, record


def qualification_state(settings, calibration, payload=None):
    if not settings.search.quality_qualified:
        return {
            "qualified": False,
            "reason": "QUALITY_GATE_NOT_ENABLED",
            "scope": "synthetic_known_map_box_fixtures_only",
        }
    expected, _ = profile_signature(settings, calibration, payload)
    try:
        record = json.loads(Path(settings.search.qualification_file).read_text())
    except (OSError, ValueError) as error:
        return {
            "qualified": False,
            "reason": "QUALIFICATION_EVIDENCE_UNAVAILABLE",
            "detail": str(error)[:300],
        }
    valid = (
        record.get("schema_version") == 1
        and record.get("profile_signature") == expected
        and record.get("all_required_cases_passed") is True
        and bool(record.get("cases"))
        and bool(record.get("environment"))
        and len(record["cases"]) == record.get("required_case_count")
        and len({case["id"] for case in record["cases"]}) == len(record["cases"])
        and all(case.get("passed") is True for case in record["cases"])
    )
    return {
        "qualified": valid,
        "reason": "QUALIFIED_SYNTHETIC_PROFILE"
        if valid
        else "QUALIFICATION_PROFILE_MISMATCH",
        "scope": "synthetic_known_map_box_fixtures_only",
        "profile_signature": expected,
        "environment": record.get("environment"),
    }
