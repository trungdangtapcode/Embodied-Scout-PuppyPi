"""Summarize genuine full-app run artifacts; never execute models or paid calls."""

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def describe(values):
    values = np.asarray(values, dtype=float)
    if not len(values):
        return {"n": 0}
    return {
        "n": len(values),
        "mean": float(values.mean()),
        "p50": float(np.median(values)),
        "p95": float(np.percentile(values, 95)),
        "max": float(values.max()),
    }


def evaluate(directory):
    browser = json.loads((directory / "browser.json").read_text())
    clock = json.loads((directory / "clock.json").read_text())
    best = min(clock, key=lambda c: c["uncertainty_ms"])
    offset = best["offset_server_minus_client_ms"]
    db = sqlite3.connect(directory / "state/assistant.sqlite3")
    db.row_factory = sqlite3.Row
    sessions = []
    for row in db.execute("SELECT * FROM tracking_sessions ORDER BY created_at"):
        observations = [
            json.loads(x[0])
            for x in db.execute(
                "SELECT record_json FROM tracking_observations WHERE session_id=? ORDER BY sequence",
                (row["id"],),
            )
        ]
        events = [
            dict(x)
            for x in db.execute(
                "SELECT generation,at,kind,record_json FROM tracking_events WHERE session_id=? ORDER BY id",
                (row["id"],),
            )
        ]
        sessions.append(
            {
                **{
                    k: row[k]
                    for k in [
                        "id",
                        "status",
                        "error_code",
                        "created_at",
                        "started_at",
                        "generation",
                        "dropped_frames",
                        "evidence_bytes",
                    ]
                },
                "anchor": json.loads(row["anchor_json"]),
                "profile": json.loads(row["profile_json"]),
                "preview": json.loads(row["preview_json"])
                if row["preview_json"]
                else None,
                "observations": observations,
                "events": events,
                "step_ms": describe([o["step_s"] * 1000 for o in observations]),
                "capture_to_publication_precommit_ms": describe(
                    [
                        o["published_unix_ms"] - o["capture_unix_ms"]
                        for o in observations
                    ]
                ),
            }
        )
    phases = {}
    for phase in set(e["phase"] for e in browser["events"]):
        groups = {}
        for kind in ["puppypi-camera-painted", "puppypi-tracking-painted"]:
            events = [
                e
                for e in browser["events"]
                if e["phase"] == phase and e["type"] == kind
            ]
            # Deduplicate immutable source identities. Repeated paints are not extra FPS.
            events = list({e["frame_id"]: e for e in events}.values())
            latencies = [
                e["painted_client_unix_ms"]
                + offset
                - (
                    e.get("capture_unix_ms")
                    or datetime.fromisoformat(e["captured_at"]).timestamp() * 1000
                )
                for e in events
            ]
            paints = sorted(e["painted_client_unix_ms"] for e in events)
            groups[kind] = {
                "capture_to_browser_callback_ms": describe(latencies),
                "distinct_frames": len(events),
                "active_interval_fps": (len(paints) - 1)
                * 1000
                / (paints[-1] - paints[0])
                if len(paints) > 1
                else None,
            }
        phases[phase] = groups
    db.close()
    return {
        "directory": str(directory),
        "clock_best": best,
        "phases": phases,
        "sessions": sessions,
        "browser_errors": browser["errors"],
        "events": browser["events"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", type=Path, required=True)
    parser.add_argument("--diagnostic", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    full = evaluate(args.full)
    runs = [full]
    if args.diagnostic:
        runs.append(evaluate(args.diagnostic))
    jobs = json.loads((args.full / "jobs.json").read_text())
    budget = json.loads((args.full / "paid-attempts.json").read_text())
    job_summary = []
    for job in jobs:
        job_summary.append(
            {
                "kind": job["kind"],
                "status": job["status"],
                "error_code": job["error_code"],
                "queue_to_finish_s": (
                    datetime.fromisoformat(job["finished_at"])
                    - datetime.fromisoformat(job["created_at"])
                ).total_seconds(),
                "worker_duration_s": (
                    datetime.fromisoformat(job["finished_at"])
                    - datetime.fromisoformat(job["started_at"])
                ).total_seconds(),
                "result_outcome": job["result"].get("outcome"),
                "calls": len(job["result"].get("provenance", {}).get("calls", [])),
            }
        )
    write(
        out / "metrics.json",
        {
            "schema_version": 1,
            "measurement": "renderer capture to Chromium double-rAF callback; offscreen painting and physical display not verified",
            "paid_budget": budget,
            "jobs": job_summary,
            "runs": [{k: v for k, v in r.items() if k != "events"} for r in runs],
        },
    )
    for name in [
        "browser.json",
        "clock.json",
        "paid-attempts.json",
        "jobs.json",
        "cleanup.json",
        "phone-tracking.png",
        "desktop-monitor.png",
        "desktop-memory.png",
        "stop.json",
    ]:
        shutil.copy2(args.full / name, out / ("full-" + name))
    if args.diagnostic:
        for name in [
            "browser.json",
            "clock.json",
            "cleanup.json",
            "phone-tracking.png",
            "desktop-monitor.png",
            "stop.json",
        ]:
            shutil.copy2(args.diagnostic / name, out / ("diagnostic-" + name))
    # Selected paired evidence only; never copy complete camera streams.
    for i, r in enumerate(runs):
        if not r["sessions"] or not r["sessions"][-1]["observations"]:
            continue
        obs = r["sessions"][-1]["observations"][-1]
        root = Path(r["directory"]) / "state"
        for kind, folder, key in [
            ("source", "images", "image_sha"),
            ("mask", "tracking-masks", "mask_sha"),
        ]:
            shutil.copy2(
                root / folder / (obs[key] + ".png"), out / f"run-{i}-{kind}.png"
            )
    with PdfPages(out / "figures.pdf") as pdf:
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), layout="constrained")
        zero = min(e["painted_client_unix_ms"] for e in full["events"])
        for kind, label, color in [
            ("puppypi-camera-painted", "Camera decode/callback", "#21745b"),
            ("puppypi-tracking-painted", "Processed mask callback", "#b66116"),
        ]:
            events = [e for e in full["events"] if e["type"] == kind]
            ages = [
                (
                    e["painted_client_unix_ms"]
                    + full["clock_best"]["offset_server_minus_client_ms"]
                    - (
                        e.get("capture_unix_ms")
                        or datetime.fromisoformat(e["captured_at"]).timestamp() * 1000
                    )
                )
                / 1000
                for e in events
            ]
            axes[0].scatter(
                [(e["painted_client_unix_ms"] - zero) / 1000 for e in events],
                ages,
                s=9,
                label=label,
                color=color,
            )
        axes[0].axhline(1, color="red", ls="--", label="Tracking freshness limit 1 s")
        axes[0].set(
            xlabel="Elapsed browser time (s)",
            ylabel="Capture to callback (s)",
            title="5 Hz requested: latency accumulates",
        )
        axes[0].legend(fontsize=8)
        for r, label in zip(runs, ["5 Hz requested", "3 Hz requested diagnostic"]):
            obs = r["sessions"][-1]["observations"]
            axes[1].plot(
                [o["sequence"] for o in obs],
                [
                    (o["inference_started_unix_ms"] - o["capture_unix_ms"]) / 1000
                    for o in obs
                ],
                label=label,
            )
        axes[1].set(
            xlabel="Processed sequence",
            ylabel="Capture to inference start (s)",
            title="Backlog is separate from model step time",
        )
        axes[1].legend(fontsize=8)
        fig.suptitle(
            "Actual upstream CPU inference on an authored rendered camera · emulated network · no physical phone",
            fontsize=10,
        )
        for ext in ["png", "svg"]:
            fig.savefig(out / f"latency.{ext}", dpi=180)
        pdf.savefig(fig)
        plt.close(fig)
        fig, axes = plt.subplots(1, len(runs), figsize=(12, 5), layout="constrained")
        axes = np.atleast_1d(axes)
        for i, (axis, r) in enumerate(zip(axes, runs)):
            source = plt.imread(out / f"run-{i}-source.png")
            mask = plt.imread(out / f"run-{i}-mask.png") > 0
            axis.imshow(source)
            overlay = np.zeros((*mask.shape, 4))
            overlay[mask] = [0.5, 1, 0.1, 0.45]
            axis.imshow(overlay)
            axis.set_title(
                (
                    "Point prompt, 5 Hz request"
                    if i == 0
                    else "Box prompt, 3 Hz diagnostic"
                )
                + "\nActual model mask; identity unverified"
            )
            axis.axis("off")
        fig.suptitle(
            "Authored pinhole rendering, not real-room accuracy evidence", fontsize=11
        )
        for ext in ["png", "svg"]:
            fig.savefig(out / f"paired-evidence.{ext}", dpi=180)
        pdf.savefig(fig)
        plt.close(fig)
    for svg in out.glob("*.svg"):
        svg.write_text(
            "\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n"
        )
    hashes = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in out.iterdir()
        if p.is_file() and p.name != "sha256.json"
    }
    write(out / "sha256.json", hashes)
    print(
        json.dumps(
            {
                "paid_attempts": budget["attempts"],
                "jobs": job_summary,
                "phases": full["phases"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
