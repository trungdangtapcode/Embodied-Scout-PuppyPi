"""Durable station-search state, immutable references and automatic model evidence.

No perception runs in this service. Terminal publication uses a guarded transaction;
cancellation and restart prevent late sightings. Operator assertions remain separate.
"""

from dataclasses import asdict
import json
import hashlib
import time
from uuid import uuid4

from teach_and_find.errors import AssistantError
from teach_and_find.library import utc_now
from teach_and_find.search_qualification import (
    qualification_state,
    control_snapshot,
    profile_signature,
    execution_environment,
)

ACTIVE = ("queued", "running")
METHOD = "YOLOE + DINOv2 + ByteTrack + DISK/LightGlue; custom geometric multi-view policy; AprilTag geometry + PythonRobotics known-map navigation"


class SearchService:
    def __init__(self, store, settings):
        self.store, self.settings = store, settings

    def get(self, identifier):
        row = self.store.db.execute(
            "SELECT * FROM searches WHERE id=?", (identifier,)
        ).fetchone()
        if row is None:
            raise AssistantError("SEARCH_NOT_FOUND", "Search does not exist.")
        result = dict(row)
        result.pop("owner")
        for key in ("payload", "result", "error"):
            value = result.pop(key + "_json")
            result[key] = json.loads(value) if value else None
        result["views"] = [
            json.loads(r[0])
            for r in self.store.db.execute(
                "SELECT record_json FROM search_views WHERE search_id=? ORDER BY ordinal",
                (identifier,),
            )
        ]
        result["events"] = [
            dict(r)
            for r in self.store.db.execute(
                "SELECT at,kind,record_json FROM search_events WHERE search_id=? ORDER BY id",
                (identifier,),
            )
        ]
        result["method"] = METHOD
        readouts = [
            json.loads(event["record_json"])["result"]
            for event in result["events"]
            if event["kind"] == "verification_evaluated"
        ]
        result["model_readout"] = readouts[-1] if readouts else None
        return result

    def overview(self):
        worker = self.store.db.execute(
            "SELECT * FROM search_worker WHERE id=1"
        ).fetchone()
        worker = dict(worker) if worker else None
        if worker:
            worker["alive"] = (
                time.time() - worker["seen_at"] < 8 and worker["status"] == "ready"
            )
        latest = self.store.db.execute(
            "SELECT payload_json FROM searches ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        qualification = (
            qualification_state(self.settings, json.loads(latest[0])["calibration"])
            if latest
            else {"qualified": False, "reason": "NO_SEARCH_PROFILE_SNAPSHOT"}
        )
        return {
            "enabled": self.settings.search.enabled,
            "quality_gate": qualification["reason"],
            "qualification": qualification,
            "worker": worker,
            "method": METHOD,
            "runs": self.summaries(),
            "sightings": [
                json.loads(r[0])
                for r in self.store.db.execute(
                    "SELECT record_json FROM model_sightings ORDER BY captured_at DESC LIMIT 30"
                )
            ],
        }

    def summaries(self):
        result = []
        rows = self.store.db.execute(
            "SELECT id,object_id,status,created_at,result_json,error_json FROM searches ORDER BY created_at DESC LIMIT 15"
        )
        for row in rows:
            count = self.store.db.execute(
                "SELECT COUNT(*) FROM search_views WHERE search_id=?", (row["id"],)
            ).fetchone()[0]
            stage = self.store.db.execute(
                "SELECT kind FROM search_events WHERE search_id=? ORDER BY id DESC LIMIT 1",
                (row["id"],),
            ).fetchone()
            verdict = json.loads(row["result_json"]) if row["result_json"] else None
            result.append(
                {
                    "id": row["id"],
                    "object_id": row["object_id"],
                    "status": row["status"],
                    "created_at": row["created_at"],
                    "view_count": count,
                    "revision": f"{row['status']}:{count}",
                    "stage": stage[0] if stage else row["status"],
                    "result": {
                        k: verdict[k]
                        for k in ("verdict", "station", "reason")
                        if k in verdict
                    }
                    if verdict
                    else None,
                    "error": json.loads(row["error_json"])
                    if row["error_json"]
                    else None,
                }
            )
        return result

    def detail(self, identifier, *, export=False):
        run = self.get(identifier)
        if export:
            return run
        # Interactive polling does not transfer archived poses/correspondence arrays.
        run.pop("events")
        run.pop("payload")
        for view in run["views"]:
            provenance = view.pop("vision")["provenance"]
            view["vision_provenance"] = provenance
            for candidate in view["candidates"]:
                candidate["matches"] = [
                    {
                        k: v
                        for k, v in match.items()
                        if k
                        not in {
                            "reference_points",
                            "query_points",
                            "inlier_mask",
                            "homography",
                        }
                    }
                    for match in candidate["matches"]
                ]
        return run

    def seen(self, status="ready"):
        with self.store.db:
            self.store.db.execute(
                "INSERT OR REPLACE INTO search_worker VALUES (1,?,?)",
                (time.time(), status),
            )

    def create(
        self, object_id, owner, request_key, calibration, mode, motion_generation=None
    ):
        owner = hashlib.sha256(owner.encode()).hexdigest()
        if not 1 <= self.settings.search.max_inspection_views <= 4:
            raise AssistantError(
                "SEARCH_BUDGET_INVALID",
                "Choose one to four configured inspection views.",
            )
        if not self.settings.search.enabled or not self.settings.vision.enabled:
            raise AssistantError(
                "SEARCH_DISABLED",
                "Search and required learned vision must both be enabled.",
            )
        if mode != "synthetic" or calibration["id"] != "authored-search-lab-v8":
            raise AssistantError(
                "SEARCH_CALIBRATION_UNSUPPORTED",
                "Only the explicitly calibrated kinematic search simulator is validated.",
            )
        if not request_key or len(request_key) > 128:
            raise AssistantError("SEARCH_KEY_INVALID", "Provide a bounded request key.")
        with self.store.db:
            self.store.db.execute("BEGIN IMMEDIATE")
            existing = self.store.db.execute(
                "SELECT id,object_id FROM searches WHERE owner=? AND request_key=?",
                (owner, request_key),
            ).fetchone()
            if existing:
                if existing["object_id"] != object_id:
                    raise AssistantError(
                        "IDEMPOTENCY_CONFLICT", "This key belongs to another target."
                    )
                return self.get(existing["id"])
            worker = self.store.db.execute(
                "SELECT * FROM search_worker WHERE id=1"
            ).fetchone()
            if (
                not worker
                or time.time() - worker["seen_at"] > 8
                or worker["status"] != "ready"
            ):
                raise AssistantError(
                    "SEARCH_WORKER_UNAVAILABLE",
                    "Start the separate search worker; no substitute.",
                )
            if self.store.db.execute(
                "SELECT 1 FROM searches WHERE status IN ('queued','running')"
            ).fetchone():
                raise AssistantError(
                    "SEARCH_BUSY", "Only one station search may own motion."
                )
            references = []
            for obj in self.store.db.execute(
                "SELECT id,name FROM objects WHERE archived_at IS NULL ORDER BY id"
            ):
                refs = [
                    r[0]
                    for r in self.store.db.execute(
                        "SELECT image_sha FROM reference_views WHERE object_id=? ORDER BY ordinal",
                        (obj["id"],),
                    )
                ]
                if not 1 <= len(refs) <= self.settings.vision.max_references:
                    raise AssistantError(
                        "SEARCH_REFERENCES_INVALID",
                        "All active reference sets must fit the model budget.",
                    )
                for sha in refs:
                    self.store.image_bytes(sha)
                references.append(
                    {"object_id": obj["id"], "name": obj["name"], "image_shas": refs}
                )
            target = next((r for r in references if r["object_id"] == object_id), None)
            if (
                target is None
                or len(target["image_shas"]) < 2
                or len(references) > self.settings.vision.max_objects
            ):
                raise AssistantError(
                    "SEARCH_REFERENCES_INVALID",
                    "Enroll at least two target views within the object budget.",
                )
            identifier = str(uuid4())
            payload = {
                "schema_version": 2,
                "motion_generation": motion_generation,
                "camera_profile": asdict(self.settings.camera),
                "control_profile": control_snapshot(self.settings),
                "references": references,
                "calibration": calibration,
                "search_profile": asdict(self.settings.search),
                "vision_profile": {
                    **asdict(self.settings.vision),
                    "profile_version": 3,
                },
            }
            payload["profile_signature"] = profile_signature(
                self.settings, calibration, payload
            )[0]
            self.store.db.execute(
                "INSERT INTO searches VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    identifier,
                    object_id,
                    owner,
                    request_key,
                    "queued",
                    utc_now(),
                    utc_now(),
                    json.dumps(payload),
                    None,
                    None,
                    mode,
                ),
            )
        return self.get(identifier)

    def claim(self):
        with self.store.db:
            self.store.db.execute("BEGIN IMMEDIATE")
            row = self.store.db.execute(
                "SELECT id FROM searches WHERE status='queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            self.store.db.execute(
                "UPDATE searches SET status='running',updated_at=? WHERE id=?",
                (utc_now(), row[0]),
            )
        return self.get(row[0])

    def check(self, identifier):
        row = self.store.db.execute(
            "SELECT status FROM searches WHERE id=?", (identifier,)
        ).fetchone()
        if not row or row[0] != "running":
            raise AssistantError(
                "SEARCH_CANCELLED",
                "Search is no longer running; no late result or motion.",
            )

    def event(self, identifier, kind, record):
        with self.store.db:
            self.check(identifier)
            self.store.db.execute(
                "INSERT INTO search_events(search_id,at,kind,record_json) VALUES (?,?,?,?)",
                (identifier, utc_now(), kind, json.dumps(record)),
            )

    def view(self, identifier, record):
        with self.store.db:
            self.store.db.execute("BEGIN IMMEDIATE")
            self.check(identifier)
            ordinal = self.store.db.execute(
                "SELECT COUNT(*) FROM search_views WHERE search_id=?", (identifier,)
            ).fetchone()[0]
            self.store.db.execute(
                "INSERT INTO search_views VALUES (?,?,?)",
                (identifier, ordinal, json.dumps(record)),
            )

    def finish(self, identifier, result, sighting=None, error=None):
        with self.store.db:
            self.store.db.execute("BEGIN IMMEDIATE")
            self.check(identifier)
            if sighting is not None:
                if result.get("verdict") != "confirmed" or not sighting.get(
                    "evidence_views"
                ):
                    raise AssistantError(
                        "SEARCH_INVALID_SIGHTING",
                        "A confirmed verdict with traceable model views is mandatory.",
                    )
                stored = {
                    r["ordinal"]: json.loads(r["record_json"])
                    for r in self.store.db.execute(
                        "SELECT ordinal,record_json FROM search_views WHERE search_id=?",
                        (identifier,),
                    )
                }
                evidence = sighting["evidence_views"]
                row = self.store.db.execute(
                    "SELECT object_id,mode FROM searches WHERE id=?", (identifier,)
                ).fetchone()
                if (
                    len({v["ordinal"] for v in evidence}) < 2
                    or sighting["object_id"] != row["object_id"]
                    or sighting["mode"] != row["mode"]
                    or sighting["search_id"] != identifier
                    or any(
                        v["ordinal"] not in stored
                        or stored[v["ordinal"]]["frame"] != v["frame"]
                        for v in evidence
                    )
                ):
                    raise AssistantError(
                        "SEARCH_INVALID_SIGHTING",
                        "Sighting must cite distinct stored capture records for the same target, run and mode.",
                    )
                for item in evidence:
                    self.store.image_bytes(item["frame"]["image_sha"])
                payload = json.loads(
                    self.store.db.execute(
                        "SELECT payload_json FROM searches WHERE id=?", (identifier,)
                    ).fetchone()[0]
                )
                qualification = qualification_state(
                    self.settings, payload["calibration"], payload
                )
                if not qualification["qualified"]:
                    raise AssistantError(
                        "SEARCH_QUALITY_NOT_QUALIFIED",
                        "The identity policy has not passed its acceptance evaluation for this profile ("
                        + qualification["reason"]
                        + "). Automatic verified memory is blocked.",
                    )
                sighting["qualification"] = qualification
                if (
                    execution_environment(list(stored.values()))
                    != qualification["environment"]
                ):
                    raise AssistantError(
                        "SEARCH_QUALITY_NOT_QUALIFIED",
                        "Executed model package versions differ from the qualified profile; no publication or alternate backend.",
                    )
                self.store.db.execute(
                    "INSERT INTO model_sightings VALUES (?,?,?,?,?,?)",
                    (
                        str(uuid4()),
                        identifier,
                        sighting["object_id"],
                        sighting["station"],
                        sighting["captured_at"],
                        json.dumps(sighting),
                    ),
                )
            self.store.db.execute(
                "UPDATE searches SET status=?,updated_at=?,result_json=?,error_json=? WHERE id=?",
                (
                    "failed" if error else "completed",
                    utc_now(),
                    json.dumps(result) if result else None,
                    json.dumps(error) if error else None,
                    identifier,
                ),
            )

    def cancel_one(self, identifier, reason="operator_cancelled_search"):
        with self.store.db:
            self.store.db.execute(
                "UPDATE searches SET status='cancelled',updated_at=?,error_json=? WHERE id=? AND status IN ('queued','running')",
                (
                    utc_now(),
                    json.dumps({"code": "SEARCH_CANCELLED", "message": reason}),
                    identifier,
                ),
            )
        return self.get(identifier)

    def cancel_all(self, reason="operator_stop"):
        with self.store.db:
            self.store.db.execute(
                "UPDATE searches SET status='cancelled',updated_at=?,error_json=? WHERE status IN ('queued','running')",
                (
                    utc_now(),
                    json.dumps({"code": "SEARCH_CANCELLED", "message": reason}),
                ),
            )

    def interrupt(self):
        with self.store.db:
            self.store.db.execute(
                "UPDATE searches SET status='interrupted',updated_at=?,error_json=? WHERE status IN ('queued','running')",
                (
                    utc_now(),
                    json.dumps(
                        {
                            "code": "SEARCH_WORKER_INTERRUPTED",
                            "message": "No automatic resume after restart.",
                        }
                    ),
                ),
            )
