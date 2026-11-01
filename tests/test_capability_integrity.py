"""Method/source disclosure regressions; fixtures never establish learned quality."""

from dataclasses import asdict, replace
import importlib.util
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
import numpy as np
import pytest

from teach_and_find.config import Settings
from teach_and_find.implementation import implementation_summary
from teach_and_find.library import build_library
from teach_and_find.mobile.api import create_app
from teach_and_find.mobile.runtime import OperatorRuntime
from teach_and_find.perception import encoder as encoders
from teach_and_find.perception.memory import ObjectMemoryBank
from teach_and_find.mission import FailureAwareMissionController, MissionState
from teach_and_find.planner import ActiveSearchPlanner, build_default_lab_graph
from teach_and_find.storage import EvidenceStore
from test_mobile import Device


def test_unknown_or_failed_encoder_never_selects_heuristic_substitute(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Heuristic substitute was instantiated")

    monkeypatch.setattr(encoders, "SpatialAppearanceEncoder", forbidden)
    cfg = Settings().perception
    with pytest.raises(ValueError, match="no fallback"):
        encoders.build_encoder(replace(cfg, encoder_backend="misspelled-model"))

    def unavailable(**kwargs):
        raise RuntimeError("Required checkpoint is unavailable")

    monkeypatch.setattr(encoders, "TorchHubBackboneEncoder", unavailable)
    with pytest.raises(RuntimeError, match="checkpoint"):
        encoders.build_encoder(replace(cfg, encoder_backend="torch_hub"))


def test_unknown_angles_and_score_semantics_survive_storage(tmp_path):
    image = np.full((48, 48, 3), (10, 80, 190), np.uint8)
    with EvidenceStore(tmp_path) as store:
        library = build_library(store, Settings())
        obj = library.teach("Fixture crop", [image, image])
        record = library.memory_bank().get_record(obj["name"])
        assert record.view_angles_deg == [None, None]
        result = library.match(image)[0]
        assert "heuristic_score" in result and "calibrated_score" not in result
        assert result["score_semantics"] == "uncalibrated_heuristic_not_probability"
    bank = ObjectMemoryBank(encoders.SpatialAppearanceEncoder())
    assert bank.teach("Unknown angles", [image, image]).view_angles_deg == [None, None]


def test_logical_home_cannot_be_reported_as_physical_return():
    image = np.full((48, 48, 3), (10, 80, 190), np.uint8)
    bank = ObjectMemoryBank(encoders.SpatialAppearanceEncoder())
    bank.teach("Fixture target", [image])
    graph = build_default_lab_graph()
    controller = FailureAwareMissionController(graph, bank, ActiveSearchPlanner(graph))
    controller.start_mission("Fixture target")
    controller.choose_next_station()
    # Explicit state fixture: exercises report bookkeeping, not visual inference.
    controller._complete_confirmed_target()
    report = asdict(controller.build_report())
    assert controller.state == MissionState.SUCCESS
    assert report["succeeded"] is True
    assert report["return_home_result"] == "logical_graph_update_only"
    assert report["physical_return_verified"] is False
    assert "not_measured_navigation" in report["execution_semantics"]
    assert "confidence" not in report
    assert all("Returned safely" not in line for line in report["decision_log"])
    assert any("not executed or measured" in line for line in report["decision_log"])


def test_showcase_reports_opposite_outcomes_without_canned_success():
    path = Path(__file__).resolve().parents[1] / "scripts/run_experiments.py"
    spec = importlib.util.spec_from_file_location("audit_showcase", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = SimpleNamespace(
        found_station_id=None,
        heuristic_score=0.1,
        stations_visited=["Fixture_Z"],
        tag_recovery_events=0,
        total_travel_distance_m=3,
    )
    full = SimpleNamespace(
        true_target_station="Fixture_Z",
        decoy_station="Fixture_Y",
        report=report,
        ground_truth_success=False,
        false_verification=False,
    )
    baseline = SimpleNamespace(
        report=report, ground_truth_success=True, false_verification=False
    )
    lines = "\n".join(module.demo_summary_lines(full, baseline))
    assert "1-View Baseline     : correct_fixture_station=True" in lines
    assert "Multi-View Baseline: correct_fixture_station=False" in lines
    assert (
        "Station_A" not in lines and "SUCCEEDED" not in lines and "FAILED" not in lines
    )


def test_inventory_is_authenticated_uncached_and_not_model_execution_evidence(tmp_path):
    cfg = Settings()
    cfg = replace(
        cfg,
        assistant=replace(cfg.assistant, data_dir=str(tmp_path)),
        mobile=replace(cfg.mobile, pairing_token="audit-test"),
    )
    with TestClient(create_app(cfg, runtime=OperatorRuntime(cfg, Device()))) as client:
        assert client.get("/api/implementation").status_code == 401
        client.post("/api/session", json={"token": "audit-test"})
        response = client.get("/api/implementation")
        payload = response.json()
        assert response.headers["cache-control"] == "no-store"
        assert payload["meaning"].endswith("not_per_run_execution_evidence")
        encoder = next(
            c for c in payload["components"] if c["name"] == "Object appearance encoder"
        )
        assert encoder["research_repository"] is None
        assert (
            encoder["implementation"] == "project_owned_python_opencv_numpy_heuristic"
        )
    # Inspecting configuration cannot import/download Torch or claim it executed.
    optional = implementation_summary(
        replace(cfg, perception=replace(cfg.perception, encoder_backend="torch_hub")),
        "synthetic",
    )
    item = next(
        c for c in optional["components"] if c["name"] == "Object appearance encoder"
    )
    assert item["implementation"] == "optional_torch_hub_adapter"
    assert "not loading or inference evidence" in item["description"]


@pytest.mark.parametrize("kind", ["spatial", "torch_hub"])
def test_empty_image_cannot_become_a_synthetic_embedding(kind):
    encoder = (
        encoders.SpatialAppearanceEncoder()
        if kind == "spatial"
        else object.__new__(encoders.TorchHubBackboneEncoder)
    )
    with pytest.raises(ValueError, match="nonempty crop"):
        encoder.embed(np.empty((0, 0, 3), np.uint8))


def test_unknown_robot_backend_never_opens_an_implicit_relay(monkeypatch):
    import teach_and_find.mobile.runtime as module

    def forbidden(*args, **kwargs):
        raise AssertionError("A substitute robot adapter was selected")

    monkeypatch.setattr(module, "RelayRobot", forbidden)
    cfg = Settings()
    from teach_and_find.storage import AssistantError

    with pytest.raises(AssistantError) as exc:
        module.OperatorRuntime(
            replace(cfg, mobile=replace(cfg.mobile, robot_mode="misspelled-backend"))
        )
    assert exc.value.code == "UNKNOWN_ROBOT_BACKEND"


def test_no_foreground_cannot_enroll_a_center_background_crop():
    from teach_and_find.ros2_bridge import teach_from_frame
    from teach_and_find.apriltag_pose import AprilTagPoseEstimator
    from teach_and_find.perception.proposals import CandidateProposalGenerator

    bank = ObjectMemoryBank(encoders.SpatialAppearanceEncoder())
    blank = np.full((480, 640, 3), 128, np.uint8)
    admitted = teach_from_frame(
        bank,
        blank,
        "Foreground fixture",
        CandidateProposalGenerator(),
        AprilTagPoseEstimator(),
    )
    assert admitted is False
    assert bank.object_names == []


def test_missing_close_view_cannot_reuse_overview_as_new_evidence(monkeypatch):
    from teach_and_find.perception.proposals import CandidateProposalGenerator
    from teach_and_find.sim.evaluator import run_closed_loop_episode
    from teach_and_find.sim.world3d import build_object_catalog, render_teaching_views

    cfg = Settings()
    catalog = build_object_catalog()
    bank = ObjectMemoryBank(
        encoders.SpatialAppearanceEncoder(), cfg.perception, cfg.planner
    )
    taught = render_teaching_views(catalog["secret_box_1"], cfg.camera)
    bank.teach(
        "Secret Box #1",
        [crop for angle, crop in taught],
        [angle for angle, crop in taught],
    )
    original = CandidateProposalGenerator.propose
    calls = []

    def initial_only(self, *args, **kwargs):
        calls.append(True)
        return original(self, *args, **kwargs) if len(calls) == 1 else []

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "Missing close-view evidence was replaced by an overview crop"
        )

    monkeypatch.setattr(CandidateProposalGenerator, "propose", initial_only)
    monkeypatch.setattr(
        FailureAwareMissionController, "evaluate_single_view_candidate", forbidden
    )
    trace = run_closed_loop_episode(
        variant_name="missing-close-view-fixture",
        use_active_planner=True,
        use_multi_view=False,
        base_memory=bank,
        catalog=catalog,
        true_target_station="Station_A",
        decoy_station="Station_C",
        other_station="Station_B",
        seed=11,
    )
    assert any("Missing close-view crop" in line for line in trace.report.decision_log)
    assert trace.report.succeeded is False
