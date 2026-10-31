"""Inspection findings must reflect fresh, visible, provenance-matched evidence."""

import json

import numpy as np
import pytest

from teach_and_find.config import Settings
from teach_and_find.inspection import InspectionService
from teach_and_find.library import build_library
from teach_and_find.storage import AssistantError, EvidenceStore


@pytest.fixture
def system(tmp_path):
    with EvidenceStore(tmp_path / "state") as store:
        library = build_library(store, Settings())
        image = np.random.default_rng(2).integers(0, 256, (60, 60, 3), dtype=np.uint8)
        obj = library.teach('<script>alert("x")</script>', [image])["id"]
        service = InspectionService(library)
        checklist = service.create_checklist("Lab <check>", [(obj, "A")])
        yield library, service, obj, checklist["id"], image


def inspect(system, **kwargs):
    return system[1].run(
        system[3], as_of="2026-01-01T12:05:00Z", max_age_s=300, **kwargs
    )


@pytest.mark.parametrize(
    "assertion,visibility,expected",
    [
        ("present", 1.0, "pass"),
        ("absent", 1.0, "fail"),
        ("absent", 0.2, "unknown"),
        ("present", 0.2, "unknown"),
        ("unknown", 1.0, "unknown"),
    ],
)
def test_present_missing_and_obscured_views(system, assertion, visibility, expected):
    library, _, obj, _, image = system
    record = library.observe(
        obj, "A", assertion, image, "2026-01-01T12:03:00Z", visibility=visibility
    )
    result = inspect(system)
    assert result["findings"][0]["status"] == expected
    assert library.observation(record["id"])["assertion"] == assertion


def test_stale_future_cutoff_and_wrong_mode_evidence_are_excluded(system):
    library, _, obj, _, image = system
    library.observe(obj, "A", "present", image, "2026-01-01T11:00:00Z")
    library.observe(obj, "A", "present", image, "2026-01-01T12:06:00Z")
    library.observe(
        obj, "A", "present", image, "2026-01-01T12:03:00Z", mode="synthetic"
    )
    assert inspect(system)["summary"] == {"pass": 0, "fail": 0, "unknown": 1}


def test_relocation_and_later_clearance_of_other_station(system):
    library, _, obj, _, image = system
    library.observe(obj, "A", "present", image, "2026-01-01T12:01:00Z")
    library.observe(obj, "B", "present", image, "2026-01-01T12:02:00Z")
    library.observe(obj, "A", "absent", image, "2026-01-01T12:03:00Z")
    assert inspect(system)["findings"][0]["reason"] == "misplaced"
    library.observe(obj, "B", "absent", image, "2026-01-01T12:04:00Z")
    assert inspect(system)["findings"][0]["reason"] == "missing"


def test_conflicting_simultaneous_evidence_cannot_confirm(system):
    library, _, obj, _, image = system
    library.observe(obj, "A", "present", image, "2026-01-01T12:01:00Z")
    library.observe(obj, "B", "present", image, "2026-01-01T12:01:00Z")
    assert inspect(system)["findings"][0]["reason"] == "conflicting_locations"
    library.observe(obj, "A", "absent", image, "2026-01-01T12:02:00Z")
    library.observe(obj, "A", "present", image, "2026-01-01T12:02:00Z")
    library.observe(obj, "B", "unknown", image, "2026-01-01T12:02:00Z")
    assert inspect(system)["findings"][0]["status"] == "unknown"


def test_report_snapshot_survives_library_changes_and_exports(system, tmp_path):
    library, service, obj, checklist_id, image = system
    library.observe(obj, "A", "present", image, "2026-01-01T12:03:00Z")
    report = inspect(system)
    library.rename(obj, "Renamed")
    library.archive(obj)
    assert service.report(report["id"]) == report
    assert inspect(system)["findings"][0]["reason"] == "archived_object"
    exported = service.export(report["id"], tmp_path / "report")
    html = (tmp_path / "report/report.html").read_text()
    assert "<script>" not in html and "&lt;script&gt;" in html
    payload = json.loads((tmp_path / "report/report.json").read_text())
    for path in payload["exported_images"].values():
        assert (tmp_path / "report" / path).is_file()
    with pytest.raises(AssistantError) as error:
        service.export(report["id"], tmp_path / "report")
    assert error.value.code == "EXPORT_EXISTS"
    assert exported["report_id"] == report["id"]
    # Checklist and report remain usable after a process restart.
    with EvidenceStore(library.store.root) as reopened:
        fresh = InspectionService(build_library(reopened, Settings()))
        assert fresh.checklist(checklist_id)["rules"][0]["object_id"] == obj
        assert fresh.report(report["id"]) == report


@pytest.mark.parametrize("final_assertion", ["absent", "unknown"])
def test_clearing_new_location_does_not_resurrect_old_location(system, final_assertion):
    library, _, obj, _, image = system
    library.observe(obj, "A", "present", image, "2026-01-01T12:01:00Z")
    library.observe(obj, "B", "present", image, "2026-01-01T12:02:00Z")
    library.observe(obj, "B", final_assertion, image, "2026-01-01T12:03:00Z")
    finding = inspect(system)["findings"][0]
    assert finding["status"] == "unknown"
    assert finding["reason"] == "location_no_longer_supported"


@pytest.mark.parametrize("assertions", [("unknown",), ("present", "absent")])
def test_newer_uncertainty_at_expected_station_blocks_old_misplacement(
    system, assertions
):
    library, _, obj, _, image = system
    library.observe(obj, "B", "present", image, "2026-01-01T12:01:00Z")
    for assertion in assertions:
        library.observe(obj, "A", assertion, image, "2026-01-01T12:02:00Z")
    assert inspect(system)["findings"][0]["status"] == "unknown"


def test_missing_evidence_does_not_leave_partial_export(system, tmp_path):
    library, service, _, _, _ = system
    report = inspect(system)
    digest = report["findings"][0]["reference_image_sha"]
    (library.store.images / f"{digest}.png").unlink()
    with pytest.raises(AssistantError):
        service.export(report["id"], tmp_path / "incomplete")
    assert not (tmp_path / "incomplete").exists()
