"""Freeze and audit actual held-out synthetic app cases; never fabricate a pass.

The evaluation uses renderer truth only after the separate worker has finished.
A qualification artifact is emitted only when every predeclared case passes.
"""

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

import numpy as np

from teach_and_find.config import Settings
from teach_and_find.search_qualification import (
    profile_signature,
    execution_environment,
    reference_scope,
)
from teach_and_find.sim.search_device import fixture_calibration

CASES = [
    {
        "id": "target-101",
        "scenario": "target",
        "seed": 101,
        "expected": "confirmed",
        "station": "Station_A",
    },
    {
        "id": "hidden-202",
        "scenario": "hidden",
        "seed": 202,
        "expected": "confirmed",
        "station": "Station_A",
    },
    {
        "id": "relocated-303",
        "scenario": "relocated",
        "seed": 303,
        "expected": "confirmed",
        "station": "Station_B",
    },
    {
        "id": "single-target-404",
        "scenario": "target",
        "seed": 404,
        "target_only": True,
        "expected": "confirmed",
        "station": "Station_A",
    },
    {"id": "decoy-505", "scenario": "decoy", "seed": 505, "expected": "inconclusive"},
    {"id": "absent-606", "scenario": "absent", "seed": 606, "expected": "inconclusive"},
    {"id": "empty-707", "scenario": "empty", "seed": 707, "expected": "inconclusive"},
    {
        "id": "unknown-hidden-808",
        "scenario": "hidden_absent",
        "seed": 808,
        "target_only": True,
        "expected": "inconclusive",
    },
    {
        "id": "hidden-front-909",
        "scenario": "hidden",
        "seed": 909,
        "ambiguous_gallery": True,
        "expected": "inconclusive",
    },
    {
        "id": "one-view-1001",
        "scenario": "target",
        "seed": 1001,
        "view_budget": 1,
        "expected": "inconclusive",
        "require_supported_candidate": True,
    },
    {
        "id": "duplicates-1101",
        "scenario": "duplicates",
        "seed": 1101,
        "expected": "inconclusive",
        "reason": "multiple_supported_instances",
    },
    {
        "id": "single-absent-1201",
        "scenario": "absent",
        "seed": 1201,
        "target_only": True,
        "expected": "inconclusive",
    },
    {
        "id": "single-decoy-1301",
        "scenario": "decoy",
        "seed": 1301,
        "target_only": True,
        "expected": "inconclusive",
    },
]


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)


def original_payload(directory, job):
    """Audit the immutable DB snapshot, preserving JSON numeric representation.

    Browser JSON.stringify normalizes 2.0 to 2. The exported values must still
    agree, but their reserialized bytes cannot replace the original signed input.
    """
    uri = (Path(directory) / "store/assistant.sqlite3").resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as database:
        row = database.execute(
            "SELECT payload_json FROM searches WHERE id=?", (job["id"],)
        ).fetchone()
    if row is None:
        raise ValueError("Original immutable search snapshot is unavailable.")
    payload = json.loads(row[0])
    if payload != job["payload"]:
        raise ValueError("Browser export disagrees with the original job snapshot.")
    return payload


def audit_case(root, case, protocol):
    directory = root / case["id"]
    raw = (directory / "app-result.json").read_bytes()
    app = json.loads(raw)
    overview, errors = app["overview"], []
    job = overview["runs"][0]
    payload = original_payload(directory, job)
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest.get("seed") != case["seed"] or manifest.get(
        "appearance_seed", 0
    ) != case.get("appearance_seed", 0):
        errors.append("fixture_seed_differs_from_frozen_case")
    actual_signature, _ = profile_signature(Settings(), payload["calibration"], payload)
    if (
        actual_signature != case["profile_signature"]
        or payload.get("profile_signature") != actual_signature
    ):
        errors.append("frozen_profile_or_source_mismatch")
    source_manifest = json.loads((directory / "source-manifest.json").read_text())
    for file, digest in protocol["profile"]["source_sha256"].items():
        if source_manifest.get("teach_and_find/" + file) != digest:
            errors.append("executed_source_snapshot_mismatch:" + file)
    forbidden = {
        "sim_scenario",
        "sim_seed",
        "search_sim",
        "is_target",
        "true_pose",
        "ground_truth",
        "placed_objects",
        "appearance_seed",
    }

    def check_keys(value):
        if isinstance(value, dict):
            if forbidden.intersection(value):
                errors.append("evaluator_truth_in_worker_payload")
            for child in value.values():
                check_keys(child)
        elif isinstance(value, list):
            for child in value:
                check_keys(child)

    check_keys(payload)
    if (
        payload.get("schema_version")
        != protocol["profile"]["search"]["profile_version"]
        or payload["vision_profile"].get("profile_version") != 3
    ):
        errors.append("wrong_role_version")
    events = [
        json.loads(event["record_json"])["result"]
        for event in job["events"]
        if event["kind"] == "verification_evaluated"
    ]
    readout = events[-1] if events else None
    if readout is None or readout.get("verdict") != case["expected"]:
        errors.append("wrong_or_missing_model_verdict")
    if case.get("station") and (readout or {}).get("station") != case["station"]:
        errors.append("wrong_recorded_region")
    if case.get("reason") and (readout or {}).get("reason") != case["reason"]:
        errors.append("wrong_abstention_mechanism")
    if (
        case.get("require_supported_candidate")
        and (readout or {}).get("candidate_count", 0) < 1
    ):
        errors.append("insufficient_view_case_has_no_actual_positive_candidate")
    if (
        case.get("require_supported_candidate")
        and payload["search_profile"]["profile_version"] == 3
        and not any(
            c["descriptor_supported"]
            and c.get("appearance", {}).get("appearance_rejected") is False
            and any(m["supported"] for m in c["matches"])
            for v in job["views"]
            for c in v["candidates"]
        )
    ):
        errors.append(
            "insufficient_view_case_has_no_appearance_and_geometry_supported_candidate"
        )
    expected_error = (
        "SEARCH_QUALITY_NOT_QUALIFIED" if case["expected"] == "confirmed" else None
    )
    if (job.get("error") or {}).get("code") != expected_error:
        errors.append("unexpected_execution_failure")
    if overview["sightings"]:
        errors.append("published_before_qualification")
    if app["browserErrors"]:
        errors.append("browser_error")
    if len(job["views"]) != case.get("view_budget", 4):
        errors.append("missing_inspection_views")
    for view in job["views"]:
        calls = view["vision"]["provenance"]["executed_upstream_calls"]
        if len(calls) != 8 or any(count < 1 for count in calls.values()):
            errors.append("missing_required_upstream_execution")
        if payload["search_profile"]["profile_version"] == 3:
            model = view.get("appearance_model", {})
            if (
                model.get("entry_point")
                != "verbatim demo_AnomalyDINO.ipynb:score_single_image"
                or model.get("calibration_sha256")
                != payload["search_profile"]["anomaly_calibration_sha256"]
            ):
                errors.append("missing_original_anomaly_model_provenance")
            for candidate in view["candidates"]:
                if not candidate["descriptor_supported"]:
                    continue
                assessment = candidate.get("appearance", {})
                if assessment.get("crop_image_sha") != candidate[
                    "crop_image_sha"
                ] or not assessment.get("provenance", {}).get("executed_scoring_calls"):
                    errors.append("missing_real_candidate_appearance_inference")
                data = (directory / "store" / assessment["map_file"]).read_bytes()
                if hashlib.sha256(data).hexdigest() != assessment["map_sha256"]:
                    errors.append("raw_patch_map_digest_mismatch")
    if execution_environment(job["views"]) != protocol["environment"]:
        errors.append("executed_environment_mismatch")
    for file, digest in protocol["fixture_source_sha256"].items():
        if source_manifest.get(file) != digest:
            errors.append("fixture_changed_after_freeze:" + file)
    truth = json.loads((directory / "evaluation-truth.json").read_text())
    if not truth.get("collision_measurement") or truth["collisions"] != 0:
        errors.append("collision_or_missing_collision_measurement")
    gt = {frame["frame_id"]: frame["pose"] for frame in truth["frames"]}
    paired_errors = []
    for event in job["events"]:
        if event["kind"] == "pose_observed":
            observed = json.loads(event["record_json"])
            if observed["frame_id"] not in gt:
                errors.append("missing_paired_pose_capture")
                continue
            p = observed["pose"]
            paired_errors.append(
                float(
                    np.linalg.norm(
                        np.array([p["x"], p["y"]])
                        - np.array(gt[observed["frame_id"]][:2])
                    )
                )
            )
    p95 = float(np.percentile(paired_errors, 95)) if paired_errors else None
    if p95 is None or p95 > protocol["limits"]["pose_p95_m"]:
        errors.append("visual_pose_quality_gate")
    if not any(abs(command["command"][0]) > 0 for command in truth["trajectory"]):
        errors.append("no_actual_command_integrated_translation")
    return {
        "id": case["id"],
        "passed": not errors,
        "errors": errors,
        "expected": case["expected"],
        "actual": (readout or {}).get("verdict"),
        "station": (readout or {}).get("station"),
        "job_id": job["id"],
        "views": len(job["views"]),
        "pose_p95_m": p95,
        "result_sha256": hashlib.sha256(raw).hexdigest(),
        "profile_signature": actual_signature,
        "reference_scope": reference_scope(payload),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["freeze", "audit"])
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--runs")
    parser.add_argument("--output")
    parser.add_argument("--environment-evidence")
    parser.add_argument("--appearance-seed-offset", type=int, default=0)
    parser.add_argument(
        "--evaluation-kind", default="fresh_heldout_appearances_and_seeds"
    )
    parser.add_argument(
        "--seed-offset",
        type=int,
        default=0,
        help="Freeze fresh fixture seeds before execution; never reuse held-out failures as unseen cases.",
    )
    args = parser.parse_args()
    cfg = Settings()
    if args.mode == "freeze":
        if not args.environment_evidence:
            parser.error(
                "--environment-evidence must identify an actual development app-result.json."
            )
        environment_job = json.loads(Path(args.environment_evidence).read_text())[
            "overview"
        ]["runs"][0]
        signature, profile = profile_signature(cfg, fixture_calibration())
        cases = []
        for index, case in enumerate(CASES):
            case = {**case, "seed": case["seed"] + args.seed_offset}
            case["id"] = case["id"].rsplit("-", 1)[0] + "-" + str(case["seed"])
            case["appearance_seed"] = (
                args.appearance_seed_offset + index
                if args.appearance_seed_offset
                else 0
            )
            variant = replace(
                cfg,
                search=replace(
                    cfg.search, max_inspection_views=case.get("view_budget", 4)
                ),
            )
            cases.append(
                {
                    **case,
                    "profile_signature": profile_signature(
                        variant, fixture_calibration()
                    )[0],
                }
            )
        write_new(
            args.protocol,
            {
                "schema_version": 1,
                "frozen_at": datetime.now(timezone.utc).isoformat(),
                "evaluation_kind": args.evaluation_kind,
                "profile_signature": signature,
                "profile": profile,
                "limits": {
                    "pose_p95_m": 0.05,
                    "false_confirmations": 0,
                    "required_case_passes": len(cases),
                },
                "cases": cases,
                "scope": "synthetic_known_map_box_fixtures_only_no_real_room_or_hardware_claim",
                "environment": execution_environment(environment_job["views"]),
                "fixture_source_sha256": {
                    file: hashlib.sha256(Path(file).read_bytes()).hexdigest()
                    for file in (
                        "teach_and_find/sim/world3d.py",
                        "teach_and_find/sim/search_device.py",
                        "scripts/research_search_app.py",
                        "web/scripts/research-search.mjs",
                    )
                },
            },
        )
        print(f"Frozen {len(cases)} cases ({args.evaluation_kind}): {signature}")
        return
    protocol = json.loads(Path(args.protocol).read_text())
    results = []
    for case in protocol["cases"]:
        try:
            results.append(audit_case(Path(args.runs), case, protocol))
        except (OSError, ValueError, KeyError, IndexError) as error:
            results.append(
                {
                    "id": case["id"],
                    "passed": False,
                    "errors": [type(error).__name__ + ": " + str(error)],
                }
            )
    passed = all(result["passed"] for result in results)
    report = {
        "schema_version": 1,
        "profile_signature": protocol["profile_signature"],
        "protocol_sha256": hashlib.sha256(Path(args.protocol).read_bytes()).hexdigest(),
        "all_required_cases_passed": passed,
        "scope": protocol["scope"],
        "cases": results,
        "required_case_count": len(protocol["cases"]),
        "environment": protocol["environment"],
        "evaluated_reference_scopes": sorted(
            {r["reference_scope"] for r in results if "reference_scope" in r}
        ),
    }
    write_new(args.output, report)
    for result in results:
        print(
            result["id"],
            "PASS" if result["passed"] else "FAIL",
            result.get("errors", []),
        )
    if not passed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
