"""Algorithm 1: Few-Shot Object Memory with Prototype Margin & Semantic Location Priors."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from teach_and_find.config import PerceptionSettings, PlannerSettings
from teach_and_find.perception.encoder import VisualEncoder


@dataclass
class ObjectRecord:
    """Stored multi-view prototype bank and semantic observation history for a taught object."""

    name: str
    prototypes: np.ndarray                  # shape (K, D), L2-normalized view embeddings
    reference_crops: list[np.ndarray]       # taught BGR crops for evidence dashboard
    view_angles_deg: list[float] = field(default_factory=list)
    station_hit_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class MatchResult:
    """Detailed prototype matching score against a taught target and known distractors."""

    target_name: str
    best_proto_sim: float
    mean_top2_sim: float
    nearest_other_sim: float
    margin: float
    calibrated_score: float
    matched_view_idx: int


class ObjectMemoryBank:
    """Stores few-shot visual prototypes, distractor embeddings, and semantic priors."""

    def __init__(
        self,
        encoder: VisualEncoder,
        perception_cfg: PerceptionSettings | None = None,
        planner_cfg: PlannerSettings | None = None,
    ) -> None:
        self.encoder = encoder
        self.perception_cfg = perception_cfg or PerceptionSettings()
        self.planner_cfg = planner_cfg or PlannerSettings()
        self._objects: dict[str, ObjectRecord] = {}
        self._distractor_bank: list[np.ndarray] = []

    @property
    def object_names(self) -> list[str]:
        return sorted(self._objects.keys())

    def get_record(self, name: str) -> ObjectRecord:
        if name not in self._objects:
            raise KeyError(f"Object '{name}' has not been taught in ObjectMemoryBank.")
        return self._objects[name]

    def teach(
        self,
        name: str,
        crops_bgr: list[np.ndarray],
        view_angles_deg: list[float] | None = None,
    ) -> ObjectRecord:
        """Enroll or update an object from K=3..5 multi-angle reference crops."""
        if not crops_bgr:
            raise ValueError("teach() requires at least one reference crop.")

        embeddings = np.stack([self.encoder.embed(crop) for crop in crops_bgr], axis=0)
        angles = (
            list(view_angles_deg)
            if view_angles_deg is not None
            else [float(i) for i in range(len(crops_bgr))]
        )
        existing_counts = (
            dict(self._objects[name].station_hit_counts) if name in self._objects else {}
        )
        record = ObjectRecord(
            name=name,
            prototypes=embeddings,
            reference_crops=[crop.copy() for crop in crops_bgr],
            view_angles_deg=angles,
            station_hit_counts=existing_counts,
        )
        self._objects[name] = record
        return record

    def register_distractor_embedding(self, embedding: np.ndarray) -> None:
        """Cache a rejected candidate embedding so repeat views carry stronger negative contrast."""
        if len(self._distractor_bank) >= 64:
            self._distractor_bank.pop(0)
        self._distractor_bank.append(embedding.astype(np.float32))

    def restore_record(self, record: ObjectRecord) -> None:
        """Restore persisted prototypes after the caller checks encoder identity."""
        prototypes = record.prototypes
        if (prototypes.ndim != 2 or prototypes.shape[1] != self.encoder.embedding_dim
                or len(prototypes) == 0 or not np.isfinite(prototypes).all()
                or len(record.reference_crops) != len(prototypes)
                or len(record.view_angles_deg) != len(prototypes)):
            raise ValueError("Stored object prototypes are incompatible or incomplete.")
        self._objects[record.name] = ObjectRecord(
            name=record.name, prototypes=prototypes.copy(),
            reference_crops=[crop.copy() for crop in record.reference_crops],
            view_angles_deg=list(record.view_angles_deg),
            station_hit_counts=dict(record.station_hit_counts),
        )

    def register_distractor_crop(self, crop_bgr: np.ndarray) -> None:
        self.register_distractor_embedding(self.encoder.embed(crop_bgr))

    def match_embedding(self, query_emb: np.ndarray, target_name: str) -> MatchResult:
        """Score a candidate embedding against target multi-view prototypes and distractors."""
        record = self.get_record(target_name)
        sims = record.prototypes @ query_emb
        best_idx = int(np.argmax(sims))
        best_sim = float(sims[best_idx])

        sorted_sims = np.sort(sims)[::-1]
        top_k = sorted_sims[: min(2, len(sorted_sims))]
        mean_top2 = float(np.mean(top_k))

        # Contrast against other taught objects AND previously rejected distractors
        competitor_sims: list[float] = []
        for other_name, other_rec in self._objects.items():
            if other_name == target_name:
                continue
            competitor_sims.append(float(np.max(other_rec.prototypes @ query_emb)))
        for neg_emb in self._distractor_bank:
            competitor_sims.append(float(np.dot(neg_emb, query_emb)))

        nearest_other = max(competitor_sims) if competitor_sims else 0.55
        margin = best_sim - nearest_other

        # Calibrated score blends prototype similarity with distractor margin bonus
        w_margin = self.perception_cfg.distractor_margin_weight
        calibrated = (1.0 - 0.25) * best_sim + 0.25 * mean_top2 + w_margin * margin

        return MatchResult(
            target_name=target_name,
            best_proto_sim=best_sim,
            mean_top2_sim=mean_top2,
            nearest_other_sim=nearest_other,
            margin=margin,
            calibrated_score=float(calibrated),
            matched_view_idx=best_idx,
        )

    def match_crop(self, crop_bgr: np.ndarray, target_name: str) -> tuple[MatchResult, np.ndarray]:
        emb = self.encoder.embed(crop_bgr)
        return self.match_embedding(emb, target_name), emb

    def record_sighting(self, name: str, station_id: str) -> None:
        """Update semantic location memory when an object is confirmed at a station."""
        record = self.get_record(name)
        record.station_hit_counts[station_id] = record.station_hit_counts.get(station_id, 0) + 1

    def get_station_priors(self, name: str, station_ids: list[str]) -> dict[str, float]:
        """Compute Dirichlet-smoothed semantic prior P(target | z) across stations."""
        if not station_ids:
            return {}
        record = self.get_record(name)
        alpha0 = self.planner_cfg.prior_dirichlet_smoothing
        weights = {
            sid: alpha0 + float(record.station_hit_counts.get(sid, 0)) for sid in station_ids
        }
        total = sum(weights.values())
        return {sid: val / total for sid, val in weights.items()}
