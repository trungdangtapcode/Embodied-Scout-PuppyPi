"""Persisted foreground suggestions with explicit operator confirmation."""

from __future__ import annotations

from dataclasses import asdict
import json
from uuid import uuid4

from teach_and_find.camera import CameraFrame
from teach_and_find.library import ObjectLibrary, label, utc_now
from teach_and_find.perception.proposals import CandidateProposalGenerator
from teach_and_find.room import RoomService
from teach_and_find.storage import AssistantError


class SceneService:
    def __init__(self, library: ObjectLibrary):
        self.library = library
        self.store = library.store

    def analyze(self, frame: CameraFrame, *, mode: str) -> dict:
        RoomService._mode(mode)
        objects = self.library.list()
        if not objects:
            raise AssistantError(
                "REFERENCES_REQUIRED", "Teach an object before analyzing a view."
            )
        bank = self.library.memory_bank(mode=mode)
        proposals = CandidateProposalGenerator(
            self.library.settings.perception
        ).propose(frame.image)
        candidates = []
        for index, proposal in enumerate(proposals):
            embedding = self.library.encoder.embed(proposal.crop_bgr)
            matches = []
            for obj in objects:
                match = asdict(bank.match_embedding(embedding, obj["name"]))
                matches.append(
                    {
                        "object_id": obj["id"],
                        "object_name": obj["name"],
                        "score": match["heuristic_score"],
                        "similarity": match["best_proto_sim"],
                    }
                )
            matches.sort(key=lambda item: item["score"], reverse=True)
            candidates.append(
                {
                    "index": index,
                    "bbox_xywh": list(proposal.bbox_xywh),
                    "crop_image_sha": self.store.save_image(proposal.crop_bgr),
                    "matches": matches[
                        : self.library.settings.room.matches_per_proposal
                    ],
                    "decision": "candidate_only",
                }
            )
        result = {
            "schema_version": 1,
            "id": str(uuid4()),
            "created_at": utc_now(),
            "mode": mode,
            "frame_id": frame.frame_id,
            "captured_at": frame.captured_at,
            "image_sha": self.store.save_image(frame.image),
            "provenance": frame.provenance,
            "encoder_signature": self.library.signature,
            "provider": "foreground_proposals_v1",
            "candidates": candidates,
            "meaning": "uncalibrated_suggestions_not_observations",
            "method": {
                "proposal": "project_owned_python_opencv_saliency_morphology_contours",
                "proposal_learned_model": False,
                "matching": "project_owned_prototype_similarity_with_authored_weights",
                "encoder_signature": self.library.signature,
                "paper_implementation_reused_for_proposals_or_matching": False,
                "score_semantics": "uncalibrated_heuristic_not_probability",
                "identity_and_region_source": "operator_confirmation",
            },
        }
        try:
            payload = json.dumps(result, allow_nan=False)
        except (ValueError, TypeError) as error:
            raise AssistantError(
                "INVALID_PROVENANCE", "Scene metadata and scores must be finite JSON."
            ) from error
        with self.store.db:
            self.store.db.execute(
                "INSERT INTO scene_analyses VALUES (?, ?, ?, ?)",
                (result["id"], result["created_at"], mode, payload),
            )
        return result

    def get(self, analysis_id: str, *, mode: str) -> dict:
        RoomService._mode(mode)
        row = self.store.db.execute(
            "SELECT result_json FROM scene_analyses WHERE id = ? AND mode = ?",
            (analysis_id, mode),
        ).fetchone()
        if row is None:
            raise AssistantError(
                "ANALYSIS_NOT_FOUND",
                "Scene analysis does not exist in this evidence mode.",
            )
        return json.loads(row[0])

    def confirm(
        self,
        analysis_id: str,
        proposal_index: int,
        object_id: str,
        station: str,
        *,
        mode: str,
    ) -> dict:
        analysis = self.get(analysis_id, mode=mode)
        if (
            not isinstance(proposal_index, int)
            or proposal_index < 0
            or proposal_index >= len(analysis["candidates"])
        ):
            raise AssistantError(
                "INVALID_CANDIDATE", "Choose a candidate in this analysis."
            )
        candidate = analysis["candidates"][proposal_index]
        if object_id not in {match["object_id"] for match in candidate["matches"]}:
            raise AssistantError(
                "INVALID_CANDIDATE", "Choose one of the suggested enrolled objects."
            )
        station = label(station)
        self.store.db.execute("BEGIN IMMEDIATE")
        try:
            previous = self.store.db.execute(
                "SELECT observation_id FROM scene_confirmations WHERE analysis_id = ? AND proposal_index = ?",
                (analysis_id, proposal_index),
            ).fetchone()
            if previous:
                observation = self.library.observation(previous[0])
                if (
                    observation["object_id"] != object_id
                    or observation["station"] != station
                ):
                    raise AssistantError(
                        "CONFIRMATION_CONFLICT",
                        "This candidate already has a different recorded confirmation.",
                    )
            else:
                observation = self.library.observe(
                    object_id,
                    station,
                    "present",
                    self.store.load_image(analysis["image_sha"]),
                    analysis["captured_at"],
                    mode=mode,
                    source="operator",
                    provenance={
                        **analysis["provenance"],
                        "scene_analysis_id": analysis_id,
                        "proposal_index": proposal_index,
                        "bbox_xywh": candidate["bbox_xywh"],
                        "crop_image_sha": candidate["crop_image_sha"],
                        "confirmation": "operator_review_of_frozen_frame",
                        "quality_visibility_source": "fixed_operator_confirmation_defaults_not_measured",
                    },
                    commit=False,
                )
                self.store.db.execute(
                    "INSERT INTO scene_confirmations VALUES (?, ?, ?)",
                    (analysis_id, proposal_index, observation["id"]),
                )
            self.store.db.commit()
            return observation
        except Exception:
            self.store.db.rollback()
            raise
