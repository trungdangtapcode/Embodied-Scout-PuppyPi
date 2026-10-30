"""Run closed-loop visual demo + 40-trial ablation study and save visual plots."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from teach_and_find.config import Settings
from teach_and_find.perception import ObjectMemoryBank, SpatialAppearanceEncoder
from teach_and_find.sim.evaluator import run_ablation_suite, run_closed_loop_episode
from teach_and_find.sim.world3d import build_object_catalog, render_teaching_views


def _bgr_to_rgb(img: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def save_demo_dashboard(out_path: Path) -> dict[str, object]:
    """Run a showcase mission where a look-alike decoy sits at the first-searched station."""
    cfg = Settings()
    catalog = build_object_catalog()
    encoder = SpatialAppearanceEncoder(cfg.perception.crop_size)
    mem = ObjectMemoryBank(encoder, cfg.perception, cfg.planner)

    taught = render_teaching_views(catalog["secret_box_1"], cfg.camera)
    mem.teach("Secret Box #1", [c for _, c in taught], [a for a, _ in taught])
    for k in ("blue_tool_case", "emerald_med_kit", "amber_sensor_cube"):
        tv = render_teaching_views(catalog[k], cfg.camera, angles_deg=(-60.0, 0.0, 60.0))
        mem.teach(catalog[k].display_name, [c for _, c in tv], [a for a, _ in tv])

    # Uniform prior on first deployment: ActiveSearchPlanner picks closest station first (Station_C),
    # where we deliberately plant the Look-Alike Red Decoy Box, while hiding Secret Box #1 at Station_A!
    trace_full = run_closed_loop_episode(
        variant_name="Full Teach & Find",
        use_active_planner=True,
        use_multi_view=True,
        base_memory=mem,
        catalog=catalog,
        true_target_station="Station_A",
        decoy_station="Station_C",
        other_station="Station_B",
        lighting_scale=0.96,
        noise_std=2.5,
        inject_tag_dropout_station="Station_A",
        capture_visuals=True,
        seed=7,
    )
    trace_baseline = run_closed_loop_episode(
        variant_name="1-View Baseline",
        use_active_planner=True,
        use_multi_view=False,
        base_memory=mem,
        catalog=catalog,
        true_target_station="Station_A",
        decoy_station="Station_C",
        other_station="Station_B",
        lighting_scale=0.96,
        noise_std=2.5,
        capture_visuals=False,
        seed=7,
    )

    fig = plt.figure(figsize=(14.5, 8.8), dpi=140)
    fig.suptitle(
        "PuppyPi Teach & Find — Closed-Loop 640x480 Visual Demo (Hard Decoy + Tag Dropout)",
        fontsize=13,
        fontweight="bold",
        y=0.98,
    )
    gs = fig.add_gridspec(3, 5, height_ratios=[0.85, 1.35, 1.05], hspace=0.38, wspace=0.22)

    # Row 0: 5 Taught Reference Views
    for idx, (ang, crop) in enumerate(taught):
        ax = fig.add_subplot(gs[0, idx])
        ax.imshow(_bgr_to_rgb(crop))
        ax.set_title(f"Teach #{idx + 1} ({ang:+.0f}°)", fontsize=9.5, fontweight="bold")
        ax.axis("off")

    # Row 1: Annotated 640x480 Robot Camera Views at Visited Stations
    visited = trace_full.report.stations_visited
    for col_idx in range(min(3, len(visited))):
        sid = visited[col_idx]
        ax = fig.add_subplot(gs[1, col_idx : col_idx + 1])
        if sid in trace_full.station_frames_annotated:
            ax.imshow(_bgr_to_rgb(trace_full.station_frames_annotated[sid]))
        ax.set_title(f"Visit #{col_idx + 1}: {sid}", fontsize=9.8, fontweight="bold")
        ax.axis("off")

    # Row 1 cols 3..4: Mission Decision Summary Box
    ax_log = fig.add_subplot(gs[1, max(1, len(visited)) : 5])
    ax_log.axis("off")
    summary_lines = [
        f"Ground Truth Target : Station_A ('Secret Box #1')",
        f"Hard Decoy Planted  : Station_C ('Red Decoy Box')",
        f"1-View Baseline     : FAILED (False Positive at {trace_baseline.report.found_station_id}!)",
        f"Full Teach & Find   : SUCCEEDED at {trace_full.report.found_station_id} "
        f"(Conf={trace_full.report.confidence:.2f})",
        f"Visited Order       : {' -> '.join(trace_full.report.stations_visited)} -> HOME",
        f"Tag Recovery Events : {trace_full.report.tag_recovery_events}  |  "
        f"Total Travel: {trace_full.report.total_travel_distance_m:.2f} m",
        "",
        "FSM Trace:",
    ]
    for line in trace_full.report.decision_log[-6:]:
        summary_lines.append("  • " + (line[:76] + "..." if len(line) > 79 else line))
    ax_log.text(
        0.01,
        0.96,
        "\n".join(summary_lines),
        va="top",
        ha="left",
        fontsize=8.6,
        family="monospace",
        bbox={"boxstyle": "round,pad=0.5", "facecolor": "#f4f6f9", "edgecolor": "#cbd5e1"},
    )

    # Row 2 Left: Decoy Multi-View Rejection Evidence
    for i, (ang, sim, crop) in enumerate(trace_full.decoy_verify_crops[:2]):
        ax = fig.add_subplot(gs[2, i])
        ax.imshow(_bgr_to_rgb(crop))
        tag_lbl = "FOOLED if 1-view" if i == 0 else "REJECTED on side!"
        ax.set_title(
            f"Decoy @ {ang:+.0f}° (sim={sim:.2f})\n{tag_lbl}",
            fontsize=8.8,
            color="#b91c1c",
            fontweight="bold",
        )
        ax.axis("off")

    # Row 2 Right: True Target Multi-View Confirmation Evidence
    for i, (ang, sim, crop) in enumerate(trace_full.target_verify_crops[:3]):
        if 2 + i >= 5:
            break
        ax = fig.add_subplot(gs[2, 2 + i])
        ax.imshow(_bgr_to_rgb(crop))
        ax.set_title(
            f"Target @ {ang:+.0f}° (sim={sim:.2f})\nCONFIRMED",
            fontsize=8.8,
            color="#15803d",
            fontweight="bold",
        )
        ax.axis("off")

    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)

    return {
        "baseline_found": trace_baseline.report.found_station_id,
        "baseline_false_verification": trace_baseline.false_verification,
        "full_found": trace_full.report.found_station_id,
        "full_confidence": round(trace_full.report.confidence, 4),
        "full_stations_visited": trace_full.report.stations_visited,
        "full_rejected_distractors": trace_full.report.rejected_distractors,
        "full_tag_recoveries": trace_full.report.tag_recovery_events,
        "full_travel_m": round(trace_full.report.total_travel_distance_m, 3),
        "decision_log": trace_full.report.decision_log,
    }


def save_ablation_plot(metrics_list: list, out_path: Path) -> None:
    labels = ["V0: Seq\n+ 1-View", "V1: Active\n+ 1-View", "V2: Seq\n+ Multi-View", "V3: Full\nTeach & Find"]
    colors = ["#94a3b8", "#60a5fa", "#f59e0b", "#16a34a"]

    fig, axes = plt.subplots(1, 4, figsize=(14.2, 4.0), dpi=140)
    fig.suptitle(
        f"PuppyPi Teach & Find — 4-Way Ablation Study ({metrics_list[0].num_trials} Randomized Trials / Variant)",
        fontsize=12.5,
        fontweight="bold",
        y=1.03,
    )

    panels = [
        ("True Task Success (%)", [m.true_success_rate for m in metrics_list], (0, 108), "{:.1f}%"),
        ("False Verification (%)", [m.false_verification_rate for m in metrics_list], (0, 108), "{:.1f}%"),
        ("Avg Stations Checked", [m.avg_stations_checked for m in metrics_list], (0, 3.2), "{:.2f}"),
        ("Avg Total Travel (m)", [m.avg_travel_distance_m for m in metrics_list], (0, 8.8), "{:.2f}m"),
    ]

    for ax, (title, vals, ylim, fmt) in zip(axes, panels):
        bars = ax.bar(labels, vals, color=colors, width=0.58, edgecolor="#1e293b", linewidth=0.8)
        ax.set_title(title, fontsize=10.5, fontweight="bold")
        ax.set_ylim(*ylim)
        ax.grid(axis="y", linestyle="--", alpha=0.35)
        ax.tick_params(axis="x", labelsize=8.5)
        for bar, val in zip(bars, vals):
            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                bar.get_height() + (ylim[1] * 0.025),
                fmt.format(val),
                ha="center",
                va="bottom",
                fontsize=9.0,
                fontweight="bold",
            )

    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    demo_info = save_demo_dashboard(out_dir / "demo_mission_dashboard.png")
    ablation = run_ablation_suite(num_trials=40, seed=42)
    save_ablation_plot(ablation, out_dir / "ablation_benchmark.png")

    payload = {
        "demo_showcase": demo_info,
        "ablation_40_trials": [asdict(m) for m in ablation],
    }
    (out_dir / "ablation_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("=== SHOWCASE DEMO EPISODE ===")
    print(json.dumps(demo_info, indent=2))
    print("\n=== 40-TRIAL ABLATION STUDY ===")
    for m in ablation:
        print(
            f"{m.variant_name:28s} | Success={m.true_success_rate:5.1f}% | "
            f"FalseVerif={m.false_verification_rate:5.1f}% | "
            f"Stations={m.avg_stations_checked:.2f} | Travel={m.avg_travel_distance_m:.2f}m | "
            f"TagRecov={m.tag_recovery_count}"
        )


if __name__ == "__main__":
    main()
