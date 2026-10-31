"""Room memory, temporal support and candidate-confirmation regressions."""

from dataclasses import replace
import time

import numpy as np
import pytest

from teach_and_find.camera import CameraFrame
from teach_and_find.config import Settings
from teach_and_find.library import build_library, utc_now
from teach_and_find.room import RoomService
from teach_and_find.scene import SceneService
from teach_and_find.storage import AssistantError, EvidenceStore


def image():
    frame = np.full((180, 240, 3), 225, np.uint8)
    frame[60:140, 90:150] = (40, 80, 200)
    frame[80:120, 110:120] = (230, 230, 230)
    return frame


def observe(library, obj, at, station="A", assertion="present", **kwargs):
    return library.observe(
        obj,
        station,
        assertion,
        image(),
        at,
        mode="synthetic",
        provenance={"capture_time_basis": "synthetic_render_time"},
        **kwargs,
    )


def test_sparse_history_never_certifies_continuous_presence_and_answers_persist(
    tmp_path,
):
    with EvidenceStore(tmp_path) as store:
        library = build_library(store, Settings())
        obj = library.teach("Case", [image()])["id"]
        observe(library, obj, "2026-01-01T10:00:00Z")
        observe(library, obj, "2026-01-01T10:10:00Z")
        service = RoomService(library)
        args = dict(
            object_id=obj,
            mode="synthetic",
            station="A",
            start_at="2026-01-01T09:59:00Z",
            end_at="2026-01-01T10:11:00Z",
        )
        first = service.query("stayed_at", **args)
        assert first["status"] == "unknown"
        assert first["reason"] == "unobserved_intervals"
        assert not first["continuous_coverage_verified"]
        assert service.query("seen_during", **args)["status"] == "supported"
        observe(library, obj, "2026-01-01T10:05:00Z", "B")
        changed = service.query("stayed_at", **args)
        assert changed["status"] == "refuted"
        assert changed["evidence"][0]["station"] == "B"
    with EvidenceStore(tmp_path) as store:
        service = RoomService(build_library(store, Settings()))
        snapshots = service.recent_queries(mode="synthetic")
        assert (
            next(q for q in snapshots if q["id"] == first["id"])["status"] == "unknown"
        )
        assert service.overview(mode="physical")["timeline"] == []


def test_occlusion_and_conflicts_do_not_become_temporal_proof(tmp_path):
    with EvidenceStore(tmp_path) as store:
        library = build_library(store, Settings())
        obj = library.teach("Case", [image()])["id"]
        observe(library, obj, "2026-01-01T10:00:00Z")
        observe(
            library, obj, "2026-01-01T10:05:00Z", assertion="absent", visibility=0.1
        )
        args = dict(
            object_id=obj,
            mode="synthetic",
            station="A",
            start_at="2026-01-01T09:59:00Z",
            end_at="2026-01-01T10:06:00Z",
        )
        service = RoomService(library)
        assert service.query("stayed_at", **args)["status"] == "unknown"
        observe(library, obj, "2026-01-01T10:00:00Z", "B")
        assert service.query("seen_during", **args)["reason"] == "conflicting_evidence"
        assert service.query("last_seen", obj, mode="synthetic")["status"] == "unknown"


def test_unverified_physical_timestamps_do_not_establish_interval_witness(tmp_path):
    with EvidenceStore(tmp_path) as store:
        library = build_library(store, Settings())
        obj = library.teach("Case", [image()])["id"]
        library.observe(
            obj, "A", "present", image(), "2026-01-01T10:00:00Z", mode="physical"
        )
        answer = RoomService(library).query(
            "seen_during",
            obj,
            mode="physical",
            station="A",
            start_at="2026-01-01T09:00:00Z",
            end_at="2026-01-01T11:00:00Z",
        )
        assert answer["status"] == "unknown"
        assert answer["reason"] == "capture_time_or_visibility_unknown"
        assert (
            RoomService(library).query("last_seen", obj, mode="physical")["reason"]
            == "historical_sighting"
        )


def test_query_validation_and_bounded_read_are_explicit(tmp_path):
    cfg = Settings()
    cfg = replace(cfg, room=replace(cfg.room, query_evidence_limit=1))
    with EvidenceStore(tmp_path) as store:
        library = build_library(store, cfg)
        obj = library.teach("Case", [image()])["id"]
        observe(library, obj, "2026-01-01T10:00:00Z")
        observe(library, obj, "2026-01-01T10:10:00Z", assertion="unknown")
        service = RoomService(library)
        assert service.query("last_seen", obj, mode="synthetic")["evidence_truncated"]
        observe(library, obj, "2026-01-01T10:11:00Z")
        assert (
            service.query("last_seen", obj, mode="synthetic")["reason"]
            == "evidence_limit_reached"
        )
        # Apply the range before the cap; newer unrelated records cannot hide an old witness.
        assert (
            service.query(
                "seen_during",
                obj,
                mode="synthetic",
                station="A",
                start_at="2026-01-01T09:59:00Z",
                end_at="2026-01-01T10:01:00Z",
            )["status"]
            == "supported"
        )
        with pytest.raises(AssistantError):
            service.query("last_seen", obj, mode="synthetic", station="A")
        with pytest.raises(AssistantError):
            service.query(
                "stayed_at",
                obj,
                mode="synthetic",
                station="A",
                start_at="2026-01-01T11:00:00Z",
                end_at="2026-01-01T10:00:00Z",
            )


def test_scene_suggestions_require_idempotent_operator_confirmation(tmp_path):
    with EvidenceStore(tmp_path) as store:
        library = build_library(store, Settings())
        obj = library.teach("Case", [image()[57:143, 87:153]])["id"]
        scene = SceneService(library)
        frame = CameraFrame(
            image(),
            "test:1",
            utc_now(),
            time.monotonic(),
            0,
            True,
            {"capture_time_basis": "synthetic_render_time", "camera_id": "test"},
        )
        analysis = scene.analyze(frame, mode="synthetic")
        assert analysis["candidates"]
        assert not library.history(obj)
        assert analysis["candidates"][0]["decision"] == "candidate_only"
        result = scene.confirm(analysis["id"], 0, obj, "A", mode="synthetic")
        repeated = scene.confirm(analysis["id"], 0, obj, "A", mode="synthetic")
        assert result["id"] == repeated["id"]
        assert len(library.history(obj)) == 1
        assert result["source"] == "operator"
        assert result["provenance"]["scene_analysis_id"] == analysis["id"]
        with pytest.raises(AssistantError) as error:
            scene.confirm(analysis["id"], 0, obj, "B", mode="synthetic")
        assert error.value.code == "CONFIRMATION_CONFLICT"
        assert len(library.history(obj)) == 1
        with pytest.raises(AssistantError):
            scene.get(analysis["id"], mode="physical")


def test_empty_scene_is_not_recorded_as_absence(tmp_path):
    with EvidenceStore(tmp_path) as store:
        library = build_library(store, Settings())
        obj = library.teach("Case", [image()])["id"]
        blank = np.full((180, 240, 3), 150, np.uint8)
        frame = CameraFrame(blank, "test:2", utc_now(), time.monotonic(), 0, True, {})
        result = SceneService(library).analyze(frame, mode="synthetic")
        assert result["candidates"] == []
        assert library.history(obj) == []


def test_invalid_source_metadata_cannot_become_a_saved_analysis(tmp_path):
    with EvidenceStore(tmp_path) as store:
        library = build_library(store, Settings())
        library.teach("Case", [image()])
        frame = CameraFrame(
            image(),
            "test:invalid",
            utc_now(),
            time.monotonic(),
            0,
            True,
            {"clock_error": float("nan")},
        )
        with pytest.raises(AssistantError) as error:
            SceneService(library).analyze(frame, mode="synthetic")
        assert error.value.code == "INVALID_PROVENANCE"
        assert (
            store.db.execute("SELECT COUNT(*) FROM scene_analyses").fetchone()[0] == 0
        )


def test_confirmation_failure_rolls_back_sighting_and_binding(tmp_path):
    with EvidenceStore(tmp_path) as store:
        library = build_library(store, Settings())
        obj = library.teach("Case", [image()])["id"]
        frame = CameraFrame(
            image(), "test:rollback", utc_now(), time.monotonic(), 0, True, {}
        )
        scene = SceneService(library)
        analysis = scene.analyze(frame, mode="synthetic")
        store.db.execute(
            "CREATE TRIGGER fail_binding BEFORE INSERT ON scene_confirmations BEGIN SELECT RAISE(ABORT, 'injected storage failure'); END"
        )
        import sqlite3

        with pytest.raises(sqlite3.IntegrityError):
            scene.confirm(analysis["id"], 0, obj, "A", mode="synthetic")
        assert library.history(obj) == []
        assert (
            store.db.execute("SELECT COUNT(*) FROM scene_confirmations").fetchone()[0]
            == 0
        )
        store.db.execute("DROP TRIGGER fail_binding")
        assert (
            scene.confirm(analysis["id"], 0, obj, "A", mode="synthetic")["source"]
            == "operator"
        )


def test_concurrent_confirmations_create_one_sighting(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    with EvidenceStore(tmp_path) as store:
        library = build_library(store, Settings())
        obj = library.teach("Case", [image()])["id"]
        analysis = SceneService(library).analyze(
            CameraFrame(
                image(), "test:parallel", utc_now(), time.monotonic(), 0, True, {}
            ),
            mode="synthetic",
        )

    def confirm(_):
        with EvidenceStore(tmp_path) as store:
            return SceneService(build_library(store, Settings())).confirm(
                analysis["id"],
                0,
                obj,
                "A",
                mode="synthetic",
            )["id"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(confirm, range(2)))
    assert len(set(ids)) == 1
    with EvidenceStore(tmp_path) as store:
        assert store.db.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 1
