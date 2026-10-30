"""Unit tests for multi-view decoy rejection, Bayesian search updates, and tag recovery."""

from __future__ import annotations

from teach_and_find.config import Settings
from teach_and_find.perception import ObjectMemoryBank, SpatialAppearanceEncoder
from teach_and_find.planner import ActiveSearchPlanner, build_default_lab_graph
from teach_and_find.sim.evaluator import run_closed_loop_episode
from teach_and_find.sim.world3d import build_object_catalog, render_teaching_views


def test_multi_view_rejects_frontal_lookalike_decoy() -> None:
    cfg = Settings()
    catalog = build_object_catalog()
    encoder = SpatialAppearanceEncoder(cfg.perception.crop_size)
    mem = ObjectMemoryBank(encoder, cfg.perception, cfg.planner)

    taught = render_teaching_views(catalog["secret_box_1"], cfg.camera)
    mem.teach("Secret Box #1", [c for _, c in taught], [a for a, _ in taught])
    for k in ("blue_tool_case", "emerald_med_kit"):
        tv = render_teaching_views(catalog[k], cfg.camera, angles_deg=(-60.0, 0.0, 60.0))
        mem.teach(catalog[k].display_name, [c for _, c in tv], [a for a, _ in tv])

    # Single-view gets tricked by lookalike_red_box at Station_C
    single_trace = run_closed_loop_episode(
        variant_name="1-view",
        use_active_planner=True,
        use_multi_view=False,
        base_memory=mem,
        catalog=catalog,
        true_target_station="Station_A",
        decoy_station="Station_C",
        other_station="Station_B",
        seed=11,
    )
    assert single_trace.false_verification is True
    assert single_trace.ground_truth_success is False

    # Multi-view rejects decoy at Station_C, recovers from tag dropout at Station_A, and finds target
    multi_trace = run_closed_loop_episode(
        variant_name="multi-view",
        use_active_planner=True,
        use_multi_view=True,
        base_memory=mem,
        catalog=catalog,
        true_target_station="Station_A",
        decoy_station="Station_C",
        other_station="Station_B",
        inject_tag_dropout_station="Station_A",
        seed=11,
    )
    assert multi_trace.ground_truth_success is True
    assert multi_trace.false_verification is False
    assert multi_trace.report.rejected_distractors >= 1
    assert multi_trace.report.tag_recovery_events >= 1


def test_bayesian_negative_observation_shifts_belief() -> None:
    graph = build_default_lab_graph()
    planner = ActiveSearchPlanner(graph)
    b0 = planner.initialize_belief()
    assert abs(b0["Station_A"] - 1.0 / 3.0) < 1e-6

    b1 = planner.register_negative_observation("Station_A", coverage_factor=1.0)
    assert b1["Station_A"] < 0.06
    assert b1["Station_B"] > 0.45
    assert b1["Station_C"] > 0.45
    assert abs(sum(b1.values()) - 1.0) < 1e-6
