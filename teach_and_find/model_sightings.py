"""Read-only projection of qualified model sightings into shared recorded history.

No numerical quality/visibility or current-room state is invented. These records
remain distinct from operator assertions and retain their original model evidence.
"""

import json

from teach_and_find.errors import AssistantError


def model_observations(
    store, mode, *, object_id=None, start_at=None, end_at=None, limit=100
):
    where, values = ["j.mode=?", "j.status='completed'"], [mode]
    for clause, value in [
        ("s.object_id=?", object_id),
        ("s.captured_at>=?", start_at),
        ("s.captured_at<=?", end_at),
    ]:
        if value is not None:
            where.append(clause)
            values.append(value)
    values.append(limit)
    rows = store.db.execute(
        "SELECT s.*,o.name AS object_name,o.archived_at,j.updated_at AS recorded_at FROM model_sightings s JOIN searches j ON j.id=s.search_id JOIN objects o ON o.id=s.object_id WHERE "
        + " AND ".join(where)
        + " ORDER BY s.captured_at DESC,j.updated_at DESC,s.id LIMIT ?",
        values,
    )
    result = []
    for row in rows:
        sighting = json.loads(row["record_json"])
        qualification = sighting.get("qualification", {})
        evidence = sighting.get("evidence_views", [])
        if (
            not qualification.get("qualified")
            or sighting.get("verdict", {}).get("verdict") != "confirmed"
            or len(evidence) < 2
        ):
            raise AssistantError(
                "MODEL_SIGHTING_EVIDENCE_INVALID",
                "Historical model sighting has no qualified confirmed evidence; no assertion substitute.",
            )
        latest = max(evidence, key=lambda e: e["frame"]["captured_at"])["frame"]
        for view in evidence:
            store.image_bytes(view["frame"]["image_sha"])
        if (
            sighting["object_id"] != row["object_id"]
            or sighting["mode"] != mode
            or latest["captured_at"] != row["captured_at"]
        ):
            raise AssistantError(
                "MODEL_SIGHTING_EVIDENCE_INVALID",
                "Historical capture/identity/mode contract is inconsistent.",
            )
        result.append(
            {
                "id": "model:" + row["id"],
                "object_id": row["object_id"],
                "object_name": row["object_name"],
                "archived_at": row["archived_at"],
                "station": row["station"],
                "assertion": "present",
                "captured_at": row["captured_at"],
                "recorded_at": row["recorded_at"],
                "image_sha": latest["image_sha"],
                "quality": None,
                "visibility": None,
                "source": "model_inference",
                "mode": mode,
                "effective_status": "present",
                "provenance": {
                    **latest["provenance"],
                    "source": sighting["source"],
                    "model_sighting_id": row["id"],
                    "search_id": row["search_id"],
                    "method_profile": sighting["method_profile"],
                    "qualification": qualification,
                    "evidence_views": evidence,
                    "current_state_established": False,
                },
            }
        )
    return result
