"""Export reproducible queue/latency evidence from actual tracking execution."""

import argparse
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


def stats(values):
    x = np.asarray(values, dtype=float)
    return (
        {
            "n": len(x),
            "p50": float(np.median(x)),
            "p95": float(np.percentile(x, 95)),
            "max": float(x.max()),
        }
        if len(x)
        else {"n": 0}
    )


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def export_browser(source, destination):
    """Retain actual timing/events; omit duplicated per-poll model configuration."""
    raw = json.loads(source.read_text())
    write(
        destination,
        {
            **{
                key: raw[key]
                for key in (
                    "schema_version",
                    "input",
                    "duration_requested_s",
                    "errors",
                    "events",
                )
            },
            "export_note": "Selected original poll fields; full raw run remains in ignored runs/. Model provenance is exported once in metrics.json.",
            "samples": [
                {
                    key: sample[key]
                    for key in (
                        "sampled_client_unix_ms",
                        "id",
                        "status",
                        "generation",
                        "error_code",
                        "stream",
                    )
                }
                for sample in raw["samples"]
            ],
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--sampling", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stop-check", type=Path)
    args = parser.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    browser = json.loads((args.run / "browser.json").read_text())
    clock = json.loads((args.run / "clock.json").read_text())
    best = min(clock, key=lambda c: c["uncertainty_ms"])
    offset = best["offset_server_minus_client_ms"]
    db = sqlite3.connect(args.run / "state/assistant.sqlite3")
    db.row_factory = sqlite3.Row
    session = dict(
        db.execute(
            "SELECT * FROM tracking_sessions ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    )
    stream = dict(
        db.execute(
            "SELECT * FROM tracking_streams WHERE session_id=?", (session["id"],)
        ).fetchone()
    )
    obs = [
        json.loads(r[0])
        for r in db.execute(
            "SELECT record_json FROM tracking_observations WHERE session_id=? ORDER BY sequence",
            (session["id"],),
        )
    ]
    lifecycle = [
        dict(r)
        for r in db.execute(
            "SELECT generation,at,kind,record_json FROM tracking_events WHERE session_id=? ORDER BY id",
            (session["id"],),
        )
    ]
    live = [o for o in obs if o["stream_phase_at_claim"] == "live"]
    zero = obs[0]["capture_unix_ms"]
    first = live[0]["capture_unix_ms"]
    last = live[-1]["capture_unix_ms"]
    early = [o for o in live if o["capture_unix_ms"] < first + 20000]
    late = [o for o in live if o["capture_unix_ms"] > last - 20000]
    eventgroups = {}
    for kind in ["puppypi-camera-painted", "puppypi-tracking-painted"]:
        events = list(
            {e["frame_id"]: e for e in browser["events"] if e["type"] == kind}.values()
        )
        painted = sorted(e["painted_client_unix_ms"] for e in events)
        eventgroups[kind] = {
            "distinct_source_frames": len(events),
            "callback_fps": (len(painted) - 1) * 1000 / (painted[-1] - painted[0]),
            "capture_to_callback_ms": stats(
                [
                    e["painted_client_unix_ms"]
                    + offset
                    - (
                        e.get("capture_unix_ms")
                        or datetime.fromisoformat(e["captured_at"]).timestamp() * 1000
                    )
                    for e in events
                ]
            ),
        }
    phases = {}
    for name, items in [
        ("all", obs),
        ("live", live),
        ("early_live_20s", early),
        ("late_live_20s", late),
    ]:
        phases[name] = {
            "count": len(items),
            "capture_to_inference_start_ms": stats(
                [o["inference_started_unix_ms"] - o["capture_unix_ms"] for o in items]
            ),
            "capture_to_precommit_ms": stats(
                [o["published_unix_ms"] - o["capture_unix_ms"] for o in items]
            ),
            "original_model_step_ms": stats([o["step_s"] * 1000 for o in items]),
        }
    paint_live = {o["frame_id"] for o in live}
    phases["live"]["capture_to_callback_ms"] = stats(
        [
            e["painted_client_unix_ms"] + offset - e["capture_unix_ms"]
            for e in browser["events"]
            if e["type"] == "puppypi-tracking-painted" and e["frame_id"] in paint_live
        ]
    )
    pending = [
        s["stream"]["pending"]
        for s in browser["samples"]
        if s["stream"]["phase"] == "live"
    ]
    result = {
        "schema_version": 1,
        "input": "authored renderer; Chromium mobile/network/CPU emulation; no physical phone",
        "session_status": session["status"],
        "error_code": session["error_code"],
        "profile": json.loads(session["profile_json"]),
        "stream": stream,
        "max_sampled_live_pending": max(pending),
        "phases": phases,
        "browser": eventgroups,
        "clock": best,
        "events": lifecycle,
        "model_provenance": json.loads(session["preview_json"])["provenance"],
        "release_gate": "5 FPS for 5 minutes: NOT PASSED; scheduler run only 120 seconds and delivered rate below 5",
        "paid_api_calls": 0,
        "physical_evidence": "NOT TESTED",
        "identity_quality": "NOT EVALUATED",
    }
    write(out / "metrics.json", result)
    write(out / "observations.json", obs)
    write(
        out / "resources.json",
        {
            "retained_source_png_bytes": sum(
                p.stat().st_size for p in (args.run / "state/images").glob("*.png")
            ),
            "retained_mask_png_bytes": sum(
                p.stat().st_size
                for p in (args.run / "state/tracking-masks").glob("*.png")
            ),
            "session_accounted_evidence_bytes": session["evidence_bytes"],
            "frame_records_after_stop": db.execute(
                "SELECT COUNT(*) FROM tracking_frames"
            ).fetchone()[0],
            "rss_timeseries": "NOT_MEASURED",
            "scope": "end-of-run accounting; includes library references in source-file total",
        },
    )
    if args.stop_check:
        for name in [
            "browser.json",
            "stop.json",
            "cleanup.json",
            "desktop-tracking.png",
        ]:
            if name == "browser.json":
                export_browser(args.stop_check / name, out / ("stop-check-" + name))
            else:
                shutil.copy2(args.stop_check / name, out / ("stop-check-" + name))
    for name in [
        "browser.json",
        "clock.json",
        "before-stop.json",
        "stop.json",
        "vision.json",
        "cleanup.json",
        "phone-tracking.png",
        "desktop-tracking.png",
    ]:
        if name == "browser.json":
            export_browser(args.run / name, out / name)
        else:
            shutil.copy2(args.run / name, out / name)
    sampling = json.loads((args.sampling / "result.json").read_text())
    write(out / "sampling.json", sampling)
    for name in ["sam-seed.png", "first-source.png", "last-source.png"]:
        shutil.copy2(args.sampling / name, out / ("sampling-" + name))
    for arm in ["ordered", "sampled"]:
        shutil.copy2(
            args.sampling / arm / "mask-11.png", out / f"sampling-{arm}-last-mask.png"
        )
    chosen = live[-1]
    root = args.run / "state"
    shutil.copy2(
        root / "images" / (chosen["image_sha"] + ".png"), out / "processed-source.png"
    )
    shutil.copy2(
        root / "tracking-masks" / (chosen["mask_sha"] + ".png"),
        out / "processed-mask.png",
    )
    with PdfPages(out / "figures.pdf") as pdf:
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.7), layout="constrained")
        x = [(o["capture_unix_ms"] - zero) / 1000 for o in obs]
        axes[0].plot(
            x,
            [
                (o["inference_started_unix_ms"] - o["capture_unix_ms"]) / 1000
                for o in obs
            ],
            label="Capture → inference start",
        )
        axes[0].plot(
            x,
            [(o["published_unix_ms"] - o["capture_unix_ms"]) / 1000 for o in obs],
            label="Capture → publication precommit",
        )
        axes[0].axhline(1, color="red", ls="--", label="Unchanged freshness limit")
        axes[0].set(
            xlabel="Elapsed capture time (s)",
            ylabel="Age (s)",
            title="Bounded bootstrap, then live latest-frame scheduling",
        )
        axes[0].legend(fontsize=8)
        samples = browser["samples"]
        t0 = samples[0]["sampled_client_unix_ms"]
        live_samples = [s for s in samples if s["stream"]["phase"] == "live"]
        axes[1].step(
            [(s["sampled_client_unix_ms"] - t0) / 1000 for s in live_samples],
            [s["stream"]["pending"] for s in live_samples],
            where="post",
            label="Live pending frames",
        )
        axes[1].set(
            xlabel="Elapsed observation time (s)",
            ylabel="Pending count",
            ylim=(-0.1, 1.5),
            title="One pending inference frame under overload",
        )
        axes[1].legend(fontsize=8)
        fig.suptitle(
            "Actual original SAM/Cutie on CPU · 120 s app run · authored input, no real-phone timing",
            fontsize=10,
        )
        for ext in ["png", "svg"]:
            fig.savefig(out / f"freshness.{ext}", dpi=180)
        pdf.savefig(fig)
        plt.close(fig)
        fig, axes = plt.subplots(1, 3, figsize=(12, 4), layout="constrained")
        for axis, name in zip(
            axes, ["processed", "sampling-ordered-last", "sampling-sampled-last"]
        ):
            source = plt.imread(
                out
                / (
                    "processed-source.png"
                    if name == "processed"
                    else "sampling-last-source.png"
                )
            )
            mask = plt.imread(out / (name + "-mask.png")) > 0
            axis.imshow(source)
            overlay = np.zeros((*mask.shape, 4))
            overlay[mask] = [0.6, 1, 0.1, 0.45]
            axis.imshow(overlay)
            axis.axis("off")
        axes[0].set_title("Actual final live mask\nIdentity unverified")
        axes[1].set_title("Ordered original Cutie replay")
        axes[2].set_title("Sampled original Cutie replay\nAgreement is not accuracy")
        fig.suptitle(
            "Authored renderer source; genuine upstream model masks", fontsize=10
        )
        for ext in ["png", "svg"]:
            fig.savefig(out / f"paired-masks.{ext}", dpi=180)
        pdf.savefig(fig)
        plt.close(fig)
    for svg in out.glob("*.svg"):
        svg.write_text(
            "\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n"
        )
    write(
        out / "sha256.json",
        {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in out.iterdir()
            if p.is_file() and p.name != "sha256.json"
        },
    )
    print(
        json.dumps(
            {
                k: result[k]
                for k in ["session_status", "stream", "phases", "browser", "clock"]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
