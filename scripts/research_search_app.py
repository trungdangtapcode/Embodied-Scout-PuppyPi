"""Opt-in actual learned CPU app experiment; synthetic inputs, no paid API/GPU/robot.

Owns and stops only its disposable server/worker/browser. Truth is saved separately
by the simulator host at shutdown and never passed to navigation/perception.
"""

import argparse
import json
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import time

import cv2
import httpx
import numpy as np

from teach_and_find.config import Settings
from teach_and_find.sim.world3d import build_object_catalog, render_teaching_views
from teach_and_find.sim.search_device import hidden_side_decoy, fixture_catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--scenario",
        choices=[
            "target",
            "hidden",
            "hidden_absent",
            "duplicates",
            "relocated",
            "decoy",
            "absent",
            "empty",
        ],
        default="target",
    )
    parser.add_argument("--port", type=int, default=18784)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--appearance-seed", type=int, default=0)
    parser.add_argument(
        "--qualified", action="store_true",
        help="Request publication using a real matching qualification artifact; never bypass its validation.",
    )
    parser.add_argument("--view-budget", type=int, default=4)
    parser.add_argument(
        "--target-only",
        action="store_true",
        help="Enroll only the target; query distractors remain unknown to the gallery.",
    )
    parser.add_argument(
        "--ambiguous-gallery",
        action="store_true",
        help="Explicit identical-reference enrollment ambiguity fixture.",
    )
    parser.add_argument(
        "--readout-only",
        action="store_true",
        help="Evaluate recorded model verdicts with automatic memory blocked; not complete-feature acceptance.",
    )
    parser.add_argument(
        "--expect-error",
        help="Explicit required-component failure case; not a successful search.",
    )
    args = parser.parse_args()
    if args.qualified and args.readout_only:
        parser.error("Qualified publication and readout-only evaluation are distinct.")
    if args.ambiguous_gallery and args.scenario != "hidden":
        parser.error("The frontal-only ambiguity fixture requires --scenario hidden.")
    root = Path(__file__).resolve().parents[1]
    output = Path(args.output).resolve()
    if output.exists():
        raise SystemExit(
            "Use a new output directory; never overwrite historical evidence."
        )
    output.mkdir(parents=True)
    refs = output / "references"
    refs.mkdir()
    cfg = Settings()
    catalog = fixture_catalog(args.appearance_seed)
    enrollment = []
    for name in (
        ("secret_box_1",) if args.target_only else ("secret_box_1", "lookalike_red_box")
    ):
        spec = (
            hidden_side_decoy(catalog)
            if args.scenario == "hidden" and name == "lookalike_red_box"
            else catalog[name]
        )
        views = render_teaching_views(
            spec,
            cfg.camera,
            rng=np.random.default_rng(7),
        )
        selected = views[1:4]
        if args.ambiguous_gallery:
            # Only frontal appearance is supplied: the side distinction is hidden
            # from enrollment. These authored references are not inference output.
            front = views[2][1]
            selected = [
                (0.0, cv2.convertScaleAbs(front, alpha=alpha))
                for alpha in (0.95, 1.0, 1.05)
            ]
        for i, (_, image) in enumerate(selected):
            cv2.imwrite(str(refs / f"{name}-{i}.png"), image)
        enrollment.append(
            {"name": name, "files": [f"{name}-{i}.png" for i in range(len(selected))]}
        )
    (refs / "enrollment.json").write_text(json.dumps(enrollment, indent=2))
    env = dict(
        os.environ,
        PUPPYPI_OPERATOR_TOKEN="search-disposable-evaluation",
        PUPPYPI_SEARCH_ENABLED="1",
        PUPPYPI_VISION_ENABLED="1",
        PUPPYPI_SEARCH_HOST=f"http://127.0.0.1:{args.port}",
        PUPPYPI_SEARCH_SCENARIO=args.scenario,
        PUPPYPI_SEARCH_SIM_SEED=str(args.seed),
        PUPPYPI_SEARCH_APPEARANCE_SEED=str(args.appearance_seed),
        PUPPYPI_SEARCH_VIEW_BUDGET=str(args.view_budget),
        PUPPYPI_SEARCH_QUALITY_QUALIFIED="1" if args.qualified else "0",
        TEACH_FIND_DATA_DIR=str(output / "store"),
        PYTHONPATH=str(root),
        CUDA_VISIBLE_DEVICES="-1",
    )
    sources = {}
    for folder in ("teach_and_find", "scripts", "web/src", "web/scripts"):
        for file in (root / folder).rglob("*"):
            if file.is_file() and file.suffix in {".py", ".ts", ".tsx", ".css", ".mjs"}:
                relative = file.relative_to(root)
                data = file.read_bytes()
                sources[str(relative)] = hashlib.sha256(data).hexdigest()
                snapshot = output / "source-snapshot" / relative
                snapshot.parent.mkdir(parents=True, exist_ok=True)
                snapshot.write_bytes(data)
    (output / "source-manifest.json").write_text(json.dumps(sources, indent=2))
    processes, logs = [], []
    passed = False
    try:
        for name, command in [
            (
                "server",
                [
                    str(root / ".venv-dev/bin/python"),
                    "scripts/search_sim_server.py",
                    "--output",
                    str(output / "evaluation-truth.json"),
                    "--port",
                    str(args.port),
                ],
            ),
            (
                "worker",
                [
                    str(root / ".venv-vision/bin/python"),
                    "-m",
                    "teach_and_find.search_worker",
                ],
            ),
        ]:
            log = (output / f"{name}.log").open("w")
            logs.append(log)
            process_env = dict(env)
            if name == "worker":
                # Fixture presence/placement/seed are not inference inputs.
                process_env.pop("PUPPYPI_SEARCH_SCENARIO", None)
                process_env.pop("PUPPYPI_SEARCH_SIM_SEED", None)
                process_env.pop("PUPPYPI_SEARCH_APPEARANCE_SEED", None)
            processes.append(
                subprocess.Popen(
                    command,
                    cwd=root,
                    env=process_env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
            )
        deadline = time.monotonic() + 15
        while True:
            if any(p.poll() is not None for p in processes):
                raise RuntimeError(
                    "Required process exited; inspect server/worker logs."
                )
            try:
                if (
                    httpx.get(
                        env["PUPPYPI_SEARCH_HOST"] + "/api/health", timeout=0.5
                    ).status_code
                    == 200
                ):
                    break
            except httpx.HTTPError:
                pass
            if time.monotonic() > deadline:
                raise RuntimeError("Host startup timed out.")
            time.sleep(0.2)
        subprocess.run(
            [
                "node",
                "web/scripts/research-search.mjs",
                env["PUPPYPI_SEARCH_HOST"],
                str(output),
            ],
            cwd=root,
            env=env,
            check=True,
            timeout=960,
        )
        (output / "manifest.json").write_text(
            json.dumps(
                {
                    "scenario": args.scenario,
                    "seed": args.seed,
                    "appearance_seed": args.appearance_seed,
                    "ambiguous_gallery": args.ambiguous_gallery,
                    "view_budget": args.view_budget,
                    "target_only_gallery": args.target_only,
                    "evidence_mode": "synthetic_kinematic_rendered",
                    "reference_source": "authored_rendered_enrollment_images",
                    "paid_api_calls": 0,
                    "local_http_api": True,
                    "hardware": False,
                    "git_head": subprocess.check_output(
                        ["git", "rev-parse", "HEAD"], cwd=root, text=True
                    ).strip(),
                    "working_changes": subprocess.check_output(
                        ["git", "status", "--short"], cwd=root, text=True
                    ),
                },
                indent=2,
            )
        )
        evidence = json.loads((output / "app-result.json").read_text())["overview"]
        run = evidence["runs"][0]
        expected_station = "Station_B" if args.scenario == "relocated" else "Station_A"
        if args.expect_error:
            passed = (
                run["status"] == "failed"
                and (run.get("error") or {}).get("code") == args.expect_error
                and not evidence["sightings"]
            )
            expectation = "explicit_required_component_failure:" + args.expect_error
        elif env.get("PUPPYPI_SEARCH_EVAL_ACTION"):
            passed = run["status"] == "cancelled" and not evidence["sightings"]
            expectation = "operator_cancel_or_stop"
        elif args.readout_only:
            events = [
                json.loads(event["record_json"])["result"]
                for event in run["events"]
                if event["kind"] == "verification_evaluated"
            ]
            readout = events[-1] if events else None
            positive = (
                args.scenario in {"target", "hidden", "relocated"}
                and not args.ambiguous_gallery
                and args.view_budget >= 2
            )
            expected_station = (
                "Station_B" if args.scenario == "relocated" else "Station_A"
            )
            passed = bool(readout) and (
                readout["verdict"] == "confirmed"
                and readout["station"] == expected_station
                if positive
                else readout["verdict"] == "inconclusive"
            )
            passed = (
                passed
                and not evidence["sightings"]
                and (
                    run["status"] == "completed"
                    or (run.get("error") or {}).get("code")
                    == "SEARCH_QUALITY_NOT_QUALIFIED"
                )
            )
            expectation = "model_readout_only_publication_not_qualified"
        elif (
            args.scenario in {"target", "hidden", "relocated"}
            and not args.ambiguous_gallery
            and args.view_budget >= 2
        ):
            passed = (
                run["status"] == "completed"
                and (run.get("result") or {}).get("verdict") == "confirmed"
                and run["result"].get("station") == expected_station
                and bool(evidence["sightings"])
                and all(
                    s["station"] == expected_station and len(s["evidence_views"]) >= 2
                    for s in evidence["sightings"]
                )
            )
            expectation = "verified_target_and_persisted_automatic_sighting"
        else:
            passed = (
                run["status"] == "completed"
                and (run.get("result") or {}).get("verdict") == "inconclusive"
                and not evidence["sightings"]
            )
            expectation = "no_false_confirmation_in_explicit_negative_fixture"
        (output / "acceptance.json").write_text(
            json.dumps(
                {
                    "experiment_completed": True,
                    "case_expectation": expectation,
                    "case_pass": passed,
                    "not_a_general_quality_or_hardware_claim": True,
                },
                indent=2,
            )
        )
        print("CASE ACCEPTANCE: " + ("PASS" if passed else "FAIL"), flush=True)
    finally:
        # Stop worker first; disconnect triggers independent server-side zero motion.
        for process in reversed(processes):
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
        for log in logs:
            log.close()
    if not passed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
