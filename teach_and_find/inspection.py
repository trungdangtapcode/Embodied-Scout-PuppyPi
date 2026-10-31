"""Evidence-based checklist evaluation and portable inspection reports."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from html import escape
import json
import math
from pathlib import Path
import shutil
from uuid import uuid4

from teach_and_find.library import ObjectLibrary, label, timestamp, utc_now
from teach_and_find.storage import AssistantError


class InspectionService:
    def __init__(self, library: ObjectLibrary) -> None:
        self.library = library
        self.store = library.store

    def create_checklist(self, name: str, items: list[tuple[str, str]]) -> dict:
        name = label(name)
        if not items or len({item[0] for item in items}) != len(items):
            raise AssistantError(
                "INVALID_CHECKLIST",
                "Provide distinct objects with one expected station each.",
            )
        rules = []
        for object_id, station in items:
            record = self.library.get(object_id)
            rules.append(
                {
                    "object_id": object_id,
                    "object_name": record["name"],
                    "expected_station": label(station),
                    "reference_image_sha": record["references"][0]["image_sha"],
                }
            )
        result = {
            "id": str(uuid4()),
            "name": name,
            "created_at": utc_now(),
            "rules": rules,
        }
        with self.store.db:
            self.store.db.execute(
                "INSERT INTO checklists VALUES (?, ?, ?, ?)",
                (result["id"], name, result["created_at"], json.dumps(rules)),
            )
        return result

    def checklist(self, checklist_id: str) -> dict:
        row = self.store.db.execute(
            "SELECT * FROM checklists WHERE id=?", (checklist_id,)
        ).fetchone()
        if row is None:
            raise AssistantError("CHECKLIST_NOT_FOUND", "Checklist does not exist.")
        return {
            "id": row["id"],
            "name": row["name"],
            "created_at": row["created_at"],
            "rules": json.loads(row["rules_json"]),
        }

    def list_checklists(self) -> list[dict]:
        return [
            self.checklist(row[0])
            for row in self.store.db.execute(
                "SELECT id FROM checklists ORDER BY created_at, id"
            ).fetchall()
        ]

    def _finding(self, rule: dict, observations: list[dict]) -> dict:
        finding = {
            **rule,
            "status": "unknown",
            "reason": "no_fresh_evidence",
            "evidence": observations,
        }
        record = self.library.get(rule["object_id"], include_archived=True)
        if record["archived_at"]:
            finding["reason"] = "archived_object"
            return finding
        latest: dict[str, list[dict]] = {}
        # Preserve all simultaneous observations so contradictory facts never
        # become a confident decision through arbitrary UUID or insertion order.
        for observation in observations:
            station = observation["station"]
            if station not in latest:
                latest[station] = [observation]
            elif observation["captured_at"] == latest[station][0]["captured_at"]:
                latest[station].append(observation)
        states = {}
        conflicts = []
        for station, group in latest.items():
            statuses = {self.library.effective_status(row) for row in group}
            states[station] = next(iter(statuses)) if len(statuses) == 1 else "unknown"
            if len(statuses) > 1:
                conflicts.append(group[0]["captured_at"])
        positive_times = [
            row["captured_at"]
            for row in observations
            if self.library.effective_status(row) == "present"
        ]
        last_positive_time = max(positive_times, default="")
        if conflicts and max(conflicts) >= last_positive_time:
            finding["reason"] = "conflicting_assertions"
            return finding
        positives = [
            group[0]
            for station, group in latest.items()
            if states[station] == "present"
        ]
        # A later sighting elsewhere supersedes an old location even if that
        # later location has subsequently been cleared or become uncertain.
        positives = [
            row for row in positives if row["captured_at"] == last_positive_time
        ]
        positives.sort(key=lambda row: row["captured_at"], reverse=True)
        expected = rule["expected_station"]
        if positives:
            newest = positives[0]
            if (
                len(positives) > 1
                and positives[1]["captured_at"] == newest["captured_at"]
            ):
                finding["reason"] = "conflicting_locations"
            elif (
                states.get(expected) == "unknown"
                and latest[expected][0]["captured_at"] >= newest["captured_at"]
            ):
                finding["reason"] = "insufficient_or_conflicting_view"
            else:
                correct = newest["station"] == rule["expected_station"]
                finding.update(
                    status="pass" if correct else "fail",
                    reason="present_at_expected_station" if correct else "misplaced",
                    observed_station=newest["station"],
                )
        elif states.get(rule["expected_station"]) == "absent":
            finding.update(status="fail", reason="missing")
        elif rule["expected_station"] in latest:
            finding["reason"] = (
                "insufficient_or_conflicting_view"
                if states[expected] == "unknown"
                else "location_no_longer_supported"
            )
        return finding

    def run(
        self,
        checklist_id: str,
        *,
        mode: str = "replay",
        as_of: str | None = None,
        max_age_s: float | None = None,
    ) -> dict:
        if mode not in {"synthetic", "replay", "physical"}:
            raise AssistantError(
                "INVALID_MODE", "Choose synthetic, replay, or physical evidence."
            )
        checklist = self.checklist(checklist_id)
        cfg = self.library.settings.assistant
        max_age_s = cfg.inspection_max_age_s if max_age_s is None else max_age_s
        if not math.isfinite(max_age_s) or max_age_s <= 0:
            raise AssistantError(
                "INVALID_AGE", "Evidence age limit must be positive and finite."
            )
        created_at = utc_now()
        as_of = timestamp(as_of) if as_of else created_at
        if as_of > created_at:
            raise AssistantError(
                "INVALID_TIME", "Inspection cutoff cannot be in the future."
            )
        try:
            start = (
                datetime.fromisoformat(as_of) - timedelta(seconds=max_age_s)
            ).isoformat(timespec="microseconds")
        except OverflowError as error:
            raise AssistantError(
                "INVALID_AGE", "Evidence age limit exceeds the timestamp range."
            ) from error
        findings = []
        for rule in checklist["rules"]:
            observations = [
                row
                for row in self.library.history(rule["object_id"])
                if start <= row["captured_at"] <= as_of and row["mode"] == mode
            ]
            findings.append(self._finding(rule, observations))
        counts = Counter(item["status"] for item in findings)
        report = {
            "schema_version": 1,
            "id": str(uuid4()),
            "checklist": checklist,
            "created_at": created_at,
            "capture_time_cutoff": as_of,
            "mode": mode,
            "policy": {
                "max_age_s": max_age_s,
                "minimum_quality": cfg.minimum_quality,
                "minimum_visibility": cfg.minimum_visibility,
            },
            "summary": {key: counts[key] for key in ("pass", "fail", "unknown")},
            "findings": findings,
            "assessment": "recorded_evidence_only; no new camera observation or robot motion",
        }
        with self.store.db:
            self.store.db.execute(
                "INSERT INTO inspection_reports VALUES (?, ?, ?, ?)",
                (
                    report["id"],
                    checklist_id,
                    created_at,
                    json.dumps(report, allow_nan=False),
                ),
            )
        return report

    def report(self, report_id: str) -> dict:
        row = self.store.db.execute(
            "SELECT report_json FROM inspection_reports WHERE id=?", (report_id,)
        ).fetchone()
        if row is None:
            raise AssistantError(
                "REPORT_NOT_FOUND", "Inspection report does not exist."
            )
        return json.loads(row[0])

    def export(self, report_id: str, destination: str | Path) -> dict:
        report = self.report(report_id)
        destination = Path(destination).expanduser().resolve()
        if destination.exists():
            raise AssistantError(
                "EXPORT_EXISTS",
                "Use a new export directory to preserve previous reports.",
            )
        images = {finding["reference_image_sha"] for finding in report["findings"]}
        images.update(
            row["image_sha"]
            for finding in report["findings"]
            for row in finding["evidence"]
        )
        # Validate every image before creating any export files.
        payloads = {digest: self.store.image_bytes(digest) for digest in images}
        destination.mkdir(parents=True, exist_ok=False)
        try:
            (destination / "evidence").mkdir()
            for digest, payload in payloads.items():
                (destination / "evidence" / f"{digest}.png").write_bytes(payload)
            report["exported_images"] = {
                digest: f"evidence/{digest}.png" for digest in sorted(images)
            }
            (destination / "report.json").write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            rows = []
            for finding in report["findings"]:
                photos = [
                    f'<figure><img src="evidence/{finding["reference_image_sha"]}.png" alt="Enrollment reference"><figcaption>Enrollment reference</figcaption></figure>'
                ]
                for observation in finding["evidence"]:
                    caption = f"{observation['station']} | {observation['captured_at']} | {observation['assertion']} | {observation['source']}"
                    photos.append(
                        f'<figure><img src="evidence/{observation["image_sha"]}.png" alt="Observation"><figcaption>{escape(caption)}</figcaption></figure>'
                    )
                rows.append(
                    "<tr>"
                    + "".join(
                        f"<td>{escape(str(finding[key]))}</td>"
                        for key in (
                            "object_name",
                            "expected_station",
                            "status",
                            "reason",
                        )
                    )
                    + "<td>"
                    + "".join(photos)
                    + "</td></tr>"
                )
            title = escape(report["checklist"]["name"])
            summary = escape(json.dumps(report["summary"]))
            html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>body{{font:16px system-ui;margin:2rem;color:#172b35}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #bbc9d1;padding:12px;text-align:left;vertical-align:top}}img{{max-width:220px;max-height:160px}}figure{{display:inline-block;margin:4px;max-width:240px}}figcaption{{font-size:12px;overflow-wrap:anywhere}}</style></head>
<body><h1>{title}</h1><p>Recorded evidence inspection · {escape(report["mode"])} · {escape(report["created_at"])}</p>
<p>{summary}</p><p>Unknown means the available evidence does not establish the requested condition. Capture cutoff: {escape(report["capture_time_cutoff"])}. Maximum evidence age: {report["policy"]["max_age_s"]} seconds.</p>
<table><thead><tr><th>Object</th><th>Expected station</th><th>Result</th><th>Reason</th><th>Evidence</th></tr></thead><tbody>{"".join(rows)}</tbody></table></body></html>"""
            (destination / "report.html").write_text(html, encoding="utf-8")
        except Exception:
            shutil.rmtree(destination)
            raise
        return {
            "report_id": report_id,
            "directory": str(destination),
            "html": str(destination / "report.html"),
            "json": str(destination / "report.json"),
        }
