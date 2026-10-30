"""Algorithm 2: Active View Verification (IEVE-inspired Sequential Bayesian Accumulator)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from teach_and_find.config import VerificationSettings
from teach_and_find.perception.memory import MatchResult


class VerificationStatus(str, Enum):
    """Decision state of multi-view candidate verification."""

    NEED_MORE_VIEWS = "NEED_MORE_VIEWS"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class ViewEvidence:
    """Single viewpoint observation recorded during active verification."""

    step_idx: int
    view_angle_deg: float
    distance_m: float
    match: MatchResult
    delta_log_odds: float
    cumulative_log_odds: float
    posterior_prob: float
    crop_bgr: np.ndarray


@dataclass
class VerificationSession:
    """Tracks sequential multi-angle evidence for one physical candidate object."""

    target_name: str
    station_id: str
    candidate_id: str
    settings: VerificationSettings = field(default_factory=VerificationSettings)
    log_odds: float = 0.0
    history: list[ViewEvidence] = field(default_factory=list)
    status: VerificationStatus = VerificationStatus.NEED_MORE_VIEWS

    @property
    def confidence(self) -> float:
        """Posterior probability P(H1 | views) = sigmoid(log_odds)."""
        clipped = max(-20.0, min(20.0, self.log_odds))
        return 1.0 / (1.0 + math.exp(-clipped))

    def distinct_view_count(self) -> int:
        """Count observations separated by at least min_angle_separation_deg."""
        accepted_angles: list[float] = []
        min_sep = self.settings.min_angle_separation_deg
        for ev in self.history:
            if all(abs(ev.view_angle_deg - prev) >= min_sep for prev in accepted_angles):
                accepted_angles.append(ev.view_angle_deg)
        return len(accepted_angles)

    def _angular_novelty_weight(self, angle_deg: float) -> float:
        if not self.history:
            return 1.0
        min_diff = min(abs(angle_deg - ev.view_angle_deg) for ev in self.history)
        if min_diff < self.settings.min_angle_separation_deg:
            # Repeated angle carries low new information (prevents static-angle overconfidence)
            return 0.20
        bonus = min(min_diff / 35.0, 1.0)
        return 1.0 + 0.25 * bonus

    def _distance_reliability_weight(self, distance_m: float) -> float:
        # Optimal sharp inspection zone on PuppyPi 640x480 camera is ~0.38m - 0.55m
        raw = 0.95 / (max(0.20, distance_m) + 0.35)
        return max(0.45, min(1.30, raw))

    def update(
        self,
        match: MatchResult,
        view_angle_deg: float,
        distance_m: float,
        crop_bgr: np.ndarray,
    ) -> VerificationStatus:
        """Incorporate a new viewpoint observation and update verification status."""
        if self.status != VerificationStatus.NEED_MORE_VIEWS:
            return self.status

        w_dist = self._distance_reliability_weight(distance_m)
        w_ang = self._angular_novelty_weight(view_angle_deg)

        sim_term = match.best_proto_sim - self.settings.similarity_midpoint
        margin_term = match.margin - self.settings.margin_midpoint
        raw_llr = (sim_term + 0.45 * margin_term) / self.settings.likelihood_temperature

        # Penalize sharp viewpoint inconsistency (e.g. front face matched, side face mismatched)
        if self.history and w_ang >= 1.0 and match.best_proto_sim < (self.settings.similarity_midpoint - 0.03):
            raw_llr -= 1.15

        delta = w_dist * w_ang * raw_llr
        self.log_odds += delta

        ev = ViewEvidence(
            step_idx=len(self.history),
            view_angle_deg=view_angle_deg,
            distance_m=distance_m,
            match=match,
            delta_log_odds=delta,
            cumulative_log_odds=self.log_odds,
            posterior_prob=self.confidence,
            crop_bgr=crop_bgr.copy(),
        )
        self.history.append(ev)

        distinct_views = self.distinct_view_count()
        if (
            self.log_odds >= self.settings.confirm_log_odds
            and distinct_views >= self.settings.min_distinct_angles_for_confirm
        ):
            self.status = VerificationStatus.CONFIRMED
        elif self.log_odds <= self.settings.reject_log_odds:
            self.status = VerificationStatus.REJECTED
        elif len(self.history) >= self.settings.max_verification_views:
            # Final decision at view budget limit
            if (
                self.log_odds >= 0.75 * self.settings.confirm_log_odds
                and distinct_views >= self.settings.min_distinct_angles_for_confirm
                and min(e.match.best_proto_sim for e in self.history) >= (self.settings.similarity_midpoint - 0.04)
            ):
                self.status = VerificationStatus.CONFIRMED
            else:
                self.status = VerificationStatus.REJECTED

        return self.status

    def next_viewpoint_angle_deg(self) -> float | None:
        """Select the next unvisited arc angle around the candidate object."""
        if self.status != VerificationStatus.NEED_MORE_VIEWS:
            return None
        min_sep = self.settings.min_angle_separation_deg
        for candidate_angle in self.settings.arc_angles_deg:
            if all(abs(candidate_angle - ev.view_angle_deg) >= min_sep for ev in self.history):
                return float(candidate_angle)
        return None
