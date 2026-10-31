"""Persistence, provenance, and compatibility regressions for object memory."""

from dataclasses import replace
import sqlite3

import numpy as np
import pytest

from teach_and_find.config import Settings
from teach_and_find.library import ObjectLibrary, build_library
from teach_and_find.perception import SpatialAppearanceEncoder
from teach_and_find.storage import AssistantError, EvidenceStore, MIGRATIONS


@pytest.fixture
def crop():
    image = np.full((80, 80, 3), (30, 60, 180), dtype=np.uint8)
    image[15:65, 33:44] = (210, 190, 20)
    return image


def test_enrollment_restart_matching_rename_update_archive(tmp_path, crop):
    with EvidenceStore(tmp_path) as store:
        library = build_library(store, Settings())
        obj = library.teach("Tool Pouch", [crop], [0])
        library.observe(
            obj["id"], "Station_A", "present", crop, "2026-01-01T10:00:00+09:00"
        )
    with EvidenceStore(tmp_path) as store:
        library = build_library(store, Settings())
        assert library.match(crop)[0]["object_id"] == obj["id"]
        assert library.match(crop)[0]["best_proto_sim"] == pytest.approx(1.0)
        renamed = library.rename(obj["id"], "My Pouch")
        assert renamed["id"] == obj["id"]
        assert library.memory_bank().get_record("My Pouch").station_hit_counts == {
            "Station_A": 1
        }
        updated = library.teach("My Pouch", [crop, crop], [0, 30], object_id=obj["id"])
        assert len(updated["references"]) == 2
        assert len(library.history(obj["id"])) == 1
        library.archive(obj["id"])
        assert library.list() == []
        assert len(library.list(include_archived=True)) == 1
        assert library.last_seen(obj["id"])["last_seen"]["station"] == "Station_A"
        assert library.teach("My Pouch", [crop])["id"] != obj["id"]


def test_capture_order_and_provenance_not_insertion_order(tmp_path, crop):
    with EvidenceStore(tmp_path) as store:
        library = build_library(store, Settings())
        obj = library.teach("Pouch", [crop])["id"]
        library.observe(obj, "B", "present", crop, "2026-01-01T12:00:00Z")
        library.observe(obj, "A", "present", crop, "2026-01-01T08:00:00Z")
        library.observe(obj, "B", "absent", crop, "2026-01-01T13:00:00Z")
        library.observe(
            obj,
            "Fake",
            "present",
            crop,
            "2026-01-01T14:00:00Z",
            mode="synthetic",
            source="synthetic",
        )
        result = library.last_seen(obj)
        assert result["last_seen"]["station"] == "B"
        assert result["latest_observation"]["assertion"] == "absent"
        assert library.memory_bank().get_record("Pouch").station_hit_counts == {
            "A": 1,
            "B": 1,
        }


def test_encoder_identity_guard_even_when_dimensions_match(tmp_path, crop):
    with EvidenceStore(tmp_path) as store:
        first = ObjectLibrary(store, SpatialAppearanceEncoder(), "revision-a")
        obj = first.teach("Pouch", [crop])
        second = ObjectLibrary(store, SpatialAppearanceEncoder(), "revision-b")
        for action in (
            second.memory_bank,
            lambda: second.teach("Pouch", [crop], object_id=obj["id"]),
        ):
            with pytest.raises(AssistantError, match="different encoder"):
                action()
        settings = Settings()
        settings = replace(
            settings,
            perception=replace(settings.perception, encoder_backend="torch_hub"),
        )
        with pytest.raises(AssistantError) as error:
            build_library(store, settings)
        assert error.value.code == "ENCODER_REVISION_REQUIRED"


def test_invalid_enrollment_preserves_existing_references(tmp_path, crop):
    with EvidenceStore(tmp_path) as store:
        library = build_library(store, Settings())
        first = library.teach("Pouch", [crop])
        other = library.teach("Other", [crop])
        with pytest.raises(AssistantError):
            library.teach("Other", [crop, crop], [0, 30], object_id=first["id"])
        assert library.get(first["id"])["references"] == first["references"]
        assert library.get(other["id"])["name"] == "Other"
        for images, angles in (([], None), ([crop], [0, 30]), ([crop], [float("nan")])):
            with pytest.raises(AssistantError):
                library.teach("Bad", images, angles)
        assert len(library.list()) == 2


@pytest.mark.parametrize(
    "kwargs",
    [
        {"captured_at": "2026-01-01T10:00:00"},
        {"captured_at": "2999-01-01T00:00:00Z"},
        {"quality": float("nan")},
        {"visibility": -0.1},
        {"assertion": "maybe"},
    ],
)
def test_invalid_observation_cannot_enter_history(tmp_path, crop, kwargs):
    with EvidenceStore(tmp_path) as store:
        library = build_library(store, Settings())
        obj = library.teach("Pouch", [crop])["id"]
        arguments = dict(
            station="A",
            assertion="present",
            image=crop,
            captured_at="2026-01-01T10:00:00Z",
        )
        arguments.update(kwargs)
        with pytest.raises(AssistantError):
            library.observe(obj, **arguments)
        assert library.history(obj) == []


def test_upgrade_old_schema_and_reject_newer_schema(tmp_path, crop):
    connection = sqlite3.connect(tmp_path / "assistant.sqlite3")
    for statement in MIGRATIONS[0]:
        connection.execute(statement)
    connection.execute("PRAGMA user_version=1")
    connection.commit()
    connection.close()
    with EvidenceStore(tmp_path) as store:
        library = build_library(store, Settings())
        obj = library.teach("Pouch", [crop])
        assert store.db.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
        store.db.execute("PRAGMA user_version=999")
    with pytest.raises(AssistantError) as error:
        EvidenceStore(tmp_path)
    assert error.value.code == "SCHEMA_TOO_NEW"
    connection = sqlite3.connect(tmp_path / "assistant.sqlite3")
    assert connection.execute("SELECT id FROM objects").fetchone()[0] == obj["id"]
    connection.close()


def test_corrupted_evidence_is_detected(tmp_path, crop):
    with EvidenceStore(tmp_path) as store:
        digest = store.save_image(crop)
        (store.images / f"{digest}.png").write_bytes(b"corrupt")
        with pytest.raises(AssistantError) as error:
            store.load_image(digest)
        assert error.value.code == "EVIDENCE_CORRUPT"
