"""Evidence-linked room projection and conservative historical query answers."""

from __future__ import annotations

from datetime import datetime, timedelta
import json
from uuid import uuid4

from teach_and_find.library import ObjectLibrary, label, timestamp, utc_now
from teach_and_find.storage import AssistantError


class RoomService:
    def __init__(self, library: ObjectLibrary):
        self.library = library
        self.store = library.store
        self.settings = library.settings.room

    @staticmethod
    def _mode(mode: str) -> None:
        if mode not in {"synthetic", "physical", "replay"}:
            raise AssistantError("INVALID_MODE", "Unsupported evidence mode.")

    def _rows(
        self,
        mode: str,
        *,
        object_id: str | None = None,
        limit: int,
        start_at: str | None = None,
        end_at: str | None = None,
    ) -> list[dict]:
        self._mode(mode)
        where = "o.mode = ?"
        parameters: list = [mode]
        if object_id:
            where += " AND o.object_id = ?"
            parameters.append(object_id)
        if start_at is not None:
            where += " AND o.captured_at >= ?"
            parameters.append(start_at)
        if end_at is not None:
            where += " AND o.captured_at <= ?"
            parameters.append(end_at)
        parameters.append(limit)
        rows = self.store.db.execute(
            f"""SELECT o.*, ob.name AS object_name, ob.archived_at
            FROM observations o JOIN objects ob ON ob.id = o.object_id
            WHERE {where} ORDER BY o.captured_at DESC, o.recorded_at DESC, o.id
            LIMIT ?""",
            parameters,
        )
        return [
            {
                **self.library._observation_record(row),
                "effective_status": self.library.effective_status(dict(row)),
            }
            for row in rows
        ]

    def overview(self, *, mode: str) -> dict:
        self._mode(mode)
        timeline = self._rows(mode, limit=self.settings.timeline_limit + 1)
        regions = {
            row[0]
            for row in self.store.db.execute(
                "SELECT DISTINCT station FROM observations WHERE mode = ?", (mode,)
            )
        }
        objects = []
        for obj in self.library.list():
            last = self.library.last_seen(obj["id"], mode=mode)
            objects.append(
                {
                    "id": obj["id"],
                    "name": obj["name"],
                    "reference_image_sha": obj["references"][0]["image_sha"],
                    "last_seen": last["last_seen"],
                    "latest_observation": last["latest_observation"],
                }
            )
        return {
            "schema_version": 1,
            "mode": mode,
            "generated_at": utc_now(),
            "objects": objects,
            "regions": sorted(regions),
            "timeline": timeline[: self.settings.timeline_limit],
            "timeline_truncated": len(timeline) > self.settings.timeline_limit,
            "recent_queries": self.recent_queries(mode=mode),
            "meaning": "recorded_observations_not_live_object_positions",
        }

    def recent_queries(self, *, mode: str) -> list[dict]:
        self._mode(mode)
        return [
            json.loads(row[0])
            for row in self.store.db.execute(
                "SELECT result_json FROM room_queries WHERE mode = ? ORDER BY created_at DESC, id LIMIT ?",
                (mode, self.settings.recent_query_limit),
            )
        ]

    def query(
        self,
        kind: str,
        object_id: str,
        *,
        mode: str,
        station: str | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
    ) -> dict:
        self._mode(mode)
        obj = self.library.get(object_id)
        if kind not in {"last_seen", "seen_during", "stayed_at"}:
            raise AssistantError("INVALID_QUERY", "Choose a supported room question.")
        now = utc_now()
        if kind == "last_seen":
            if station is not None or start_at is not None or end_at is not None:
                raise AssistantError(
                    "INVALID_QUERY", "Last seen does not accept a time range or region."
                )
        else:
            if not station or not start_at or not end_at:
                raise AssistantError(
                    "INVALID_QUERY", "Choose a region and both time bounds."
                )
            station = label(station)
            start_at, end_at = timestamp(start_at), timestamp(end_at)
            if not start_at < end_at <= now:
                raise AssistantError(
                    "INVALID_TIME", "Choose an ordered time range ending in the past."
                )
            if (
                datetime.fromisoformat(end_at) - datetime.fromisoformat(start_at)
            ).total_seconds() > timedelta(
                days=self.settings.maximum_query_days
            ).total_seconds():
                raise AssistantError(
                    "INVALID_TIME", "The requested time range is too large."
                )

        rows = self._rows(
            mode,
            object_id=object_id,
            limit=self.settings.query_evidence_limit + 1,
            start_at=start_at,
            end_at=end_at,
        )
        truncated = len(rows) > self.settings.query_evidence_limit
        rows = rows[: self.settings.query_evidence_limit]
        evidence = (
            rows
            if kind == "last_seen"
            else [row for row in rows if start_at <= row["captured_at"] <= end_at]
        )
        usable = [row for row in evidence if row["effective_status"] != "unknown"]
        status, reason = "unknown", "no_usable_evidence"
        selected: list[dict] = []
        if kind == "last_seen":
            positives = [row for row in usable if row["effective_status"] == "present"]
            if positives:
                selected = [positives[0]]
                # Simultaneous conflicting annotations must not be resolved by row order.
                at_time = [
                    row
                    for row in usable
                    if row["captured_at"] == selected[0]["captured_at"]
                ]
                conflicting = any(
                    (
                        row["station"] != selected[0]["station"]
                        and row["effective_status"] == "present"
                    )
                    or (
                        row["station"] == selected[0]["station"]
                        and row["effective_status"] == "absent"
                    )
                    for row in at_time
                )
                if conflicting:
                    reason, selected = "conflicting_evidence", at_time
                else:
                    status, reason = "supported", "historical_sighting"
        else:
            # Interval verdicts require a capture-time contract. Legacy/physical
            # point estimates without explicit bounds cannot establish ordering.
            timed = [
                row for row in usable if self._inside_interval(row, start_at, end_at)
            ]
            positives = [
                row
                for row in timed
                if row["station"] == station and row["effective_status"] == "present"
            ]
            negatives = [
                row
                for row in timed
                if (row["station"] == station and row["effective_status"] == "absent")
                or (row["station"] != station and row["effective_status"] == "present")
            ]
            if kind == "seen_during" and positives:
                conflicts = [
                    row
                    for row in timed
                    if row["captured_at"] == positives[0]["captured_at"]
                    and (
                        (
                            row["station"] == station
                            and row["effective_status"] == "absent"
                        )
                        or (
                            row["station"] != station
                            and row["effective_status"] == "present"
                        )
                    )
                ]
                if conflicts:
                    reason, selected = "conflicting_evidence", positives[:1] + conflicts
                else:
                    status, reason, selected = (
                        "supported",
                        "recorded_witness",
                        positives[:1],
                    )
            elif kind == "stayed_at" and negatives:
                witness = negatives[0]
                conflicts = [
                    row
                    for row in timed
                    if row["captured_at"] == witness["captured_at"]
                    and row["station"] == station
                    and row["effective_status"] == "present"
                ]
                if conflicts:
                    reason, selected = "conflicting_evidence", [witness] + conflicts
                else:
                    status, reason, selected = (
                        "refuted",
                        "recorded_counterexample",
                        [witness],
                    )
            else:
                reason = (
                    "unobserved_intervals"
                    if timed
                    else "capture_time_or_visibility_unknown"
                )
                selected = evidence[: self.settings.timeline_limit]
        if truncated:
            # Omitted rows could contain a simultaneous contradiction. Never
            # publish a definite verdict from an incomplete conflict group.
            status, reason = "unknown", "evidence_limit_reached"
        result = {
            "schema_version": 1,
            "id": str(uuid4()),
            "created_at": now,
            "mode": mode,
            "kind": kind,
            "object_id": object_id,
            "object_name": obj["name"],
            "station": station,
            "start_at": start_at,
            "end_at": end_at,
            "status": status,
            "reason": reason,
            "evidence": selected,
            "evidence_truncated": truncated
            or len(evidence) > self.settings.timeline_limit,
            "basis": "recorded_assertions",
            "continuous_coverage_verified": False,
        }
        with self.store.db:
            self.store.db.execute(
                "INSERT INTO room_queries VALUES (?, ?, ?, ?)",
                (result["id"], now, mode, json.dumps(result)),
            )
        return result

    @staticmethod
    def _inside_interval(row: dict, start: str, end: str) -> bool:
        provenance = row["provenance"]
        if (
            row["mode"] == "synthetic"
            and provenance.get("capture_time_basis") == "synthetic_render_time"
        ):
            return start <= row["captured_at"] <= end
        lower, upper = (
            provenance.get("capture_start_at"),
            provenance.get("capture_end_at"),
        )
        if not isinstance(lower, str) or not isinstance(upper, str):
            return False
        try:
            lower, upper = timestamp(lower), timestamp(upper)
        except AssistantError:
            return False
        return start <= lower <= row["captured_at"] <= upper <= end
