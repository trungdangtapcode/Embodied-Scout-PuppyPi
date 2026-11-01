"""SQLite frame inbox adapter; separate bootstrap history and live pending slot."""

import json
import time

from teach_and_find.storage import AssistantError
from teach_and_find.tracking_schedule import select_frame


class FrameInbox:
    def __init__(self, store, cfg):
        self.store, self.db, self.cfg = store, store.db, cfg

    def create(self, sid):
        self.db.execute("INSERT INTO tracking_streams(session_id) VALUES(?)", (sid,))

    def snapshot(self, sid):
        row = self.db.execute(
            "SELECT * FROM tracking_streams WHERE session_id=?", (sid,)
        ).fetchone()
        if not row:
            return None  # Historical v1 sessions retain their actual method.
        result = dict(row)
        result["pending"] = (
            0
            if row["phase"] == "closed"
            else self.db.execute(
                "SELECT COUNT(*) FROM tracking_frames WHERE session_id=? AND sequence>?",
                (sid, row["claimed_sequence"]),
            ).fetchone()[0]
        )
        result["policy"] = "bounded_bootstrap_then_latest_pending_v2"
        return result

    def publish(self, sid, generation, record, size, producer_replacements):
        """Publish only to the same active generation; one live pending row."""
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute(
                "SELECT s.status,s.generation,s.evidence_bytes,q.* FROM tracking_sessions s JOIN tracking_streams q ON q.session_id=s.id WHERE s.id=?",
                (sid,),
            ).fetchone()
            if not row or row["generation"] != generation or row["phase"] == "closed":
                return False
            if row["evidence_bytes"] + size > self.cfg.evidence_limit_bytes:
                raise AssistantError(
                    "TRACKING_STORAGE_LIMIT",
                    "Source evidence exceeds session byte budget.",
                )
            replaced = 0
            if row["phase"] == "live":
                replaced = self.db.execute(
                    "DELETE FROM tracking_frames WHERE session_id=? AND sequence>0",
                    (sid,),
                ).rowcount
            sequence = row["next_sequence"]
            self.db.execute(
                "INSERT INTO tracking_frames VALUES(?,?,?,?)",
                (sid, sequence, record["frame_id"], json.dumps(record)),
            )
            self.db.execute(
                "UPDATE tracking_streams SET next_sequence=next_sequence+1,offered_frames=offered_frames+1,producer_replacements=producer_replacements+?,pending_replacements=pending_replacements+?,peak_live_pending=MAX(peak_live_pending,?) WHERE session_id=?",
                (producer_replacements, replaced, int(row["phase"] == "live"), sid),
            )
            self.db.execute(
                "UPDATE tracking_sessions SET evidence_bytes=evidence_bytes+?,dropped_frames=dropped_frames+? WHERE id=?",
                (size, producer_replacements, sid),
            )
            if row["phase"] == "bootstrap":
                self.db.execute(
                    "DELETE FROM tracking_frames WHERE session_id=? AND sequence>0 AND sequence<?",
                    (sid, sequence - self.cfg.frame_limit + 1),
                )
        return True

    def claim(self, sid, generation, previous_sequence, previous_capture, *, now=None):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            state = self.db.execute(
                "SELECT q.*,s.generation FROM tracking_streams q JOIN tracking_sessions s ON s.id=q.session_id WHERE q.session_id=?",
                (sid,),
            ).fetchone()
            if (
                not state
                or state["generation"] != generation
                or state["phase"] == "closed"
            ):
                return None
            if state["in_flight_sequence"] is not None:
                raise AssistantError(
                    "TRACKING_CLAIM_CONFLICT",
                    "Another model call owns a source snapshot.",
                )
            frames = [
                (r["sequence"], json.loads(r["record_json"]))
                for r in self.db.execute(
                    "SELECT sequence,record_json FROM tracking_frames WHERE session_id=? AND sequence>? ORDER BY sequence",
                    (sid, previous_sequence),
                )
            ]
            selected = select_frame(
                frames,
                phase=state["phase"],
                previous_sequence=previous_sequence,
                previous_capture=previous_capture,
                now=time.time() if now is None else now,
                max_gap=self.cfg.max_frame_gap_s,
                max_age=self.cfg.max_result_age_s,
            )
            if selected is None:
                return None
            self.db.execute(
                "UPDATE tracking_streams SET claimed_sequence=?,in_flight_sequence=?,skipped_frames=skipped_frames+? WHERE session_id=?",
                (selected.sequence, selected.sequence, selected.skipped, sid),
            )
            if state["phase"] == "live":
                self.db.execute(
                    "DELETE FROM tracking_frames WHERE session_id=? AND sequence>0",
                    (sid,),
                )
            return selected

    def completed(self, sid, sequence, was_head, fresh):
        """Called in the same transaction as generation-guarded publication."""
        state = self.snapshot(sid)
        if state is None:
            raise AssistantError("TRACKING_PROFILE_UNSUPPORTED", "No v2 stream state.")
        phase = state["phase"]
        if phase == "bootstrap" and was_head and fresh:
            pending = self.db.execute(
                "SELECT MAX(sequence) FROM tracking_frames WHERE session_id=? AND sequence>?",
                (sid, sequence),
            ).fetchone()[0]
            self.db.execute(
                "DELETE FROM tracking_frames WHERE session_id=? AND sequence>0 AND (? IS NULL OR sequence<>?)",
                (sid, pending, pending),
            )
            phase = "live"
        self.db.execute(
            "UPDATE tracking_streams SET phase=?,in_flight_sequence=NULL,processed_frames=processed_frames+1,claimed_sequence=?,peak_live_pending=MAX(peak_live_pending,?) WHERE session_id=?",
            (
                phase,
                sequence,
                int(
                    phase == "live"
                    and self.db.execute(
                        "SELECT COUNT(*) FROM tracking_frames WHERE session_id=? AND sequence>?",
                        (sid, sequence),
                    ).fetchone()[0]
                    > 0
                ),
                sid,
            ),
        )
        return phase

    def close(self, sid):
        self.db.execute(
            "UPDATE tracking_streams SET phase='closed',in_flight_sequence=NULL WHERE session_id=?",
            (sid,),
        )
