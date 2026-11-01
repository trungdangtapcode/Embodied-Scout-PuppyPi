"""Custom logical mission FSM and bounded commands; no learned policy or route executor."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from teach_and_find.apriltag_pose import TagObservation
from teach_and_find.config import PuppyMotionLimits, Settings
from teach_and_find.perception.memory import MatchResult, ObjectMemoryBank
from teach_and_find.perception.proposals import CandidateProposal
from teach_and_find.planner import (
    ActiveSearchPlanner,
    SequentialSearchPlanner,
    StationScoreBreakdown,
    TopologicalGraph,
)
from teach_and_find.verification import VerificationSession, VerificationStatus


class MissionState(str, Enum):
    """Explicit failure-aware finite-state machine states."""

    IDLE = "IDLE"
    SELECT_STATION = "SELECT_STATION"
    NAVIGATE_TO_STATION = "NAVIGATE_TO_STATION"
    ALIGN_WITH_TAG = "ALIGN_WITH_TAG"
    RECOVER_TAG = "RECOVER_TAG"
    SCAN_STATION = "SCAN_STATION"
    ACTIVE_VERIFY = "ACTIVE_VERIFY"
    RETURN_HOME = "RETURN_HOME"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


@dataclass(frozen=True)
class PuppyActionCommand:
    """Bounds-checked motion/posture fields informed by vendor guards; physical behavior unverified.

    Note on Hiwonder driver quirks verified from puppy.py:
      - `/puppy_control/velocity` drops commands whenever `vy_cm_s != 0`.
        Therefore `use_velocity_move_topic` automatically switches to `True`
        whenever lateral strafing (`vy_cm_s != 0`) is commanded.
      - `/puppy_control/pose` drops commands whenever `yaw != 0` or `height` outside [-15, -5].
    """

    vx_cm_s: float = 0.0
    vy_cm_s: float = 0.0
    yaw_rate_rad_s: float = 0.0
    pitch_rad: float = math.radians(-10.0)
    height_cm: float = -10.0
    use_velocity_move_topic: bool = False
    description: str = "hold"

    @classmethod
    def clamped(
        cls,
        limits: PuppyMotionLimits,
        vx_cm_s: float = 0.0,
        vy_cm_s: float = 0.0,
        yaw_rate_rad_s: float = 0.0,
        pitch_rad: float | None = None,
        height_cm: float | None = None,
        description: str = "move",
    ) -> PuppyActionCommand:
        vx = max(-limits.max_vx_cm_s, min(limits.max_vx_cm_s, vx_cm_s))
        vy = max(-limits.max_vy_cm_s, min(limits.max_vy_cm_s, vy_cm_s))
        yr = max(
            -limits.max_yaw_rate_rad_s, min(limits.max_yaw_rate_rad_s, yaw_rate_rad_s)
        )
        pitch = (
            limits.min_pitch_rad
            if pitch_rad is not None and pitch_rad < limits.min_pitch_rad
            else limits.max_pitch_rad
            if pitch_rad is not None and pitch_rad > limits.max_pitch_rad
            else (pitch_rad if pitch_rad is not None else math.radians(-10.0))
        )
        h = max(
            -14.5,
            min(-5.5, height_cm if height_cm is not None else limits.stand_height_cm),
        )
        return cls(
            vx_cm_s=vx,
            vy_cm_s=vy,
            yaw_rate_rad_s=yr,
            pitch_rad=pitch,
            height_cm=h,
            use_velocity_move_topic=(abs(vy) > 1e-4),
            description=description,
        )


@dataclass
class MissionEvidenceReport:
    """Structured final mission output with verifiable visual evidence."""

    target_name: str
    succeeded: bool
    found_station_id: str | None
    heuristic_score: float
    stations_visited: list[str]
    rejected_distractors: int
    tag_recovery_events: int
    total_travel_distance_m: float
    evidence_crops: list[np.ndarray] = field(default_factory=list)
    evidence_angles_deg: list[float] = field(default_factory=list)
    decision_log: list[str] = field(default_factory=list)
    execution_semantics: str = "logical_station_search_not_measured_navigation"
    score_semantics: str = "uncalibrated_heuristic_not_probability"
    distance_semantics: str = "configured_graph_distance_not_measured_travel"
    physical_return_verified: bool = False
    return_home_result: str = "not_performed"

    @property
    def confidence(self) -> float:
        """Legacy Python alias, not a calibrated probability."""
        return self.heuristic_score


class FailureAwareMissionController:
    """Coordinates topological search, tag recovery, and multi-view verification."""

    def __init__(
        self,
        graph: TopologicalGraph,
        memory: ObjectMemoryBank,
        planner: ActiveSearchPlanner | SequentialSearchPlanner,
        settings: Settings | None = None,
        use_multi_view_verification: bool = True,
        return_home_on_success: bool = True,
    ) -> None:
        self.graph = graph
        self.memory = memory
        self.planner = planner
        self.settings = settings or Settings()
        self.use_multi_view_verification = use_multi_view_verification
        self.return_home_on_success = return_home_on_success

        self.state: MissionState = MissionState.IDLE
        self.target_name: str = ""
        self.current_node_id: str = "HOME"
        self.active_station_id: str | None = None
        self.exhausted_stations: set[str] = set()
        self.stations_visited: list[str] = []
        self.lost_tag_counter: int = 0
        self.tag_recovery_events: int = 0
        self.rejected_distractors: int = 0
        self.total_travel_distance_m: float = 0.0
        self.active_verification: VerificationSession | None = None
        self.decision_log: list[str] = []
        self.confirmed_crops: list[np.ndarray] = []
        self.confirmed_angles: list[float] = []
        self.final_confidence: float = 0.0

    def start_mission(self, target_name: str, start_node_id: str = "HOME") -> None:
        """Initialize a new active search mission for a taught target."""
        self.memory.get_record(target_name)  # validates target exists in memory
        self.target_name = target_name
        self.current_node_id = start_node_id
        self.active_station_id = None
        self.exhausted_stations.clear()
        self.stations_visited.clear()
        self.lost_tag_counter = 0
        self.tag_recovery_events = 0
        self.rejected_distractors = 0
        self.total_travel_distance_m = 0.0
        self.active_verification = None
        self.confirmed_crops.clear()
        self.confirmed_angles.clear()
        self.final_confidence = 0.0
        self.decision_log = [
            f"Mission started for target '{target_name}' from {start_node_id}."
        ]

        priors = self.memory.get_station_priors(
            target_name, self.graph.search_station_ids
        )
        self.planner.initialize_belief(priors)
        self.state = MissionState.SELECT_STATION

    def choose_next_station(self) -> StationScoreBreakdown | None:
        """Select the highest-utility unexhausted station and transition to navigation."""
        choice = self.planner.select_next_station(
            self.current_node_id,
            exclude_exhausted=self.exhausted_stations,
        )
        if choice is None:
            self.state = MissionState.FAILED
            self.decision_log.append(
                "All stations exhausted without confirming target."
            )
            return None

        self.active_station_id = choice.station_id
        self.total_travel_distance_m += choice.travel_distance_m
        self.current_node_id = choice.station_id
        self.stations_visited.append(choice.station_id)
        self.lost_tag_counter = 0
        self.state = MissionState.ALIGN_WITH_TAG
        self.decision_log.append(
            f"Selected {choice.station_id} (P={choice.belief_prob:.2f}, "
            f"dist={choice.travel_distance_m:.2f}m, score={choice.total_score:.2f})."
        )
        return choice

    def compute_tag_alignment_command(
        self,
        tags: list[TagObservation],
        desired_distance_m: float | None = None,
    ) -> tuple[bool, PuppyActionCommand]:
        """Compute closed-loop velocity/pose command to align with the station AprilTag."""
        assert self.active_station_id is not None
        expected_tag_id = self.graph.nodes[self.active_station_id].apriltag_id
        target_dist = desired_distance_m or self.settings.apriltag.standoff_distance_m
        limits = self.settings.motion

        matching = [t for t in tags if t.tag_id == expected_tag_id]
        if not matching:
            self.lost_tag_counter += 1
            if self.lost_tag_counter == 1:
                self.tag_recovery_events += 1
                self.decision_log.append(
                    f"Tag #{expected_tag_id} not visible at {self.active_station_id}; entering RECOVER_TAG."
                )
            if self.lost_tag_counter > self.settings.apriltag.lost_tag_timeout_steps:
                self.state = MissionState.SCAN_STATION
                self.exhausted_stations.add(self.active_station_id)
                self.planner.register_negative_observation(
                    self.active_station_id, coverage_factor=0.25
                )
                self.decision_log.append(
                    f"Tag #{expected_tag_id} recovery timed out at {self.active_station_id}; issuing bounded halt/skip logic (physical stop unverified)."
                )
                self.state = MissionState.SELECT_STATION
                return False, PuppyActionCommand.clamped(
                    limits, description="halt_after_tag_timeout"
                )

            self.state = MissionState.RECOVER_TAG
            # Alternate gentle yaw scan in place and slight pitch sweep
            sweep_dir = 1.0 if (self.lost_tag_counter % 2 == 1) else -1.0
            pitch = math.radians(-12.0 if self.lost_tag_counter <= 2 else -18.0)
            return False, PuppyActionCommand.clamped(
                limits,
                vx_cm_s=0.0,
                vy_cm_s=0.0,
                yaw_rate_rad_s=sweep_dir * math.radians(18.0),
                pitch_rad=pitch,
                description=f"recover_tag_sweep_{self.lost_tag_counter}",
            )

        # Tag acquired! Reset recovery counter
        self.lost_tag_counter = 0
        self.state = MissionState.ALIGN_WITH_TAG
        obs = matching[0]
        dist_err = obs.distance_m - target_dist
        bearing_err = obs.bearing_rad

        if abs(dist_err) <= 0.07 and abs(bearing_err) <= math.radians(6.5):
            self.state = MissionState.SCAN_STATION
            return True, PuppyActionCommand.clamped(
                limits,
                pitch_rad=math.radians(-14.0),
                description="aligned_ready_to_scan",
            )

        vx = 28.0 * dist_err  # proportional cm/s
        yaw_rate = -1.15 * bearing_err
        return False, PuppyActionCommand.clamped(
            limits,
            vx_cm_s=vx,
            vy_cm_s=0.0,
            yaw_rate_rad_s=yaw_rate,
            pitch_rad=math.radians(-10.0),
            description="visual_servo_to_tag",
        )

    def compute_arc_viewpoint_command(
        self,
        current_angle_deg: float,
        desired_angle_deg: float,
        radius_m: float,
    ) -> PuppyActionCommand:
        """Command lateral arc motion around a candidate using /puppy_control/velocity_move."""
        limits = self.settings.motion
        delta_rad = math.radians(desired_angle_deg - current_angle_deg)
        # Arc length s = r * delta_theta; counter-rotate yaw so camera stays pointed at object
        vy_cm_s = max(-limits.max_vy_cm_s, min(limits.max_vy_cm_s, 18.0 * delta_rad))
        yaw_rate = -vy_cm_s / max(25.0, radius_m * 100.0)
        return PuppyActionCommand.clamped(
            limits,
            vx_cm_s=0.0,
            vy_cm_s=vy_cm_s,
            yaw_rate_rad_s=yaw_rate,
            pitch_rad=math.radians(-16.0),
            description=f"arc_to_{desired_angle_deg:+.0f}deg",
        )

    def evaluate_single_view_candidate(
        self, match: MatchResult, crop_bgr: np.ndarray
    ) -> bool:
        """Ablation mode: decide immediately from a single frontal view without active verification."""
        if (
            match.best_proto_sim
            >= self.settings.perception.single_view_confirm_threshold
        ):
            self.final_confidence = float(min(0.99, match.best_proto_sim))
            self.confirmed_crops = [crop_bgr.copy()]
            self.confirmed_angles = [0.0]
            self._complete_confirmed_target()
            return True
        return False

    def start_candidate_verification(self, candidate_id: str) -> VerificationSession:
        assert self.active_station_id is not None
        self.state = MissionState.ACTIVE_VERIFY
        self.active_verification = VerificationSession(
            target_name=self.target_name,
            station_id=self.active_station_id,
            candidate_id=candidate_id,
            settings=self.settings.verification,
        )
        return self.active_verification

    def step_candidate_verification(
        self,
        proposal: CandidateProposal,
        view_angle_deg: float,
        distance_m: float,
    ) -> VerificationStatus:
        """Process one active verification view and update memory/FSM on confirm or reject."""
        assert self.active_verification is not None
        match, emb = self.memory.match_crop(proposal.crop_bgr, self.target_name)
        status = self.active_verification.update(
            match=match,
            view_angle_deg=view_angle_deg,
            distance_m=distance_m,
            crop_bgr=proposal.crop_bgr,
        )
        if status == VerificationStatus.CONFIRMED:
            self.final_confidence = self.active_verification.confidence
            self.confirmed_crops = [
                ev.crop_bgr for ev in self.active_verification.history
            ]
            self.confirmed_angles = [
                ev.view_angle_deg for ev in self.active_verification.history
            ]
            self.decision_log.append(
                f"CONFIRMED '{self.target_name}' at {self.active_station_id} "
                f"after {len(self.active_verification.history)} views "
                f"(heuristic_score={self.final_confidence:.2f}; not calibrated)."
            )
            self._complete_confirmed_target()
        elif status == VerificationStatus.REJECTED:
            self.rejected_distractors += 1
            self.memory.register_distractor_embedding(emb)
            self.decision_log.append(
                f"REJECTED distractor '{self.active_verification.candidate_id}' at {self.active_station_id} "
                f"after {len(self.active_verification.history)} views "
                f"(heuristic_score={self.active_verification.heuristic_score:.2f}; not calibrated)."
            )
            self.active_verification = None
            self.state = MissionState.SCAN_STATION
        return status

    def finish_station_unsuccessful(self, coverage_factor: float = 1.0) -> None:
        """Record no confirmed target and apply the authored station-score update."""
        assert self.active_station_id is not None
        sid = self.active_station_id
        self.exhausted_stations.add(sid)
        new_belief = self.planner.register_negative_observation(
            sid, coverage_factor=coverage_factor
        )
        formatted = ", ".join(f"{k}:{v:.2f}" for k, v in sorted(new_belief.items()))
        self.decision_log.append(
            f"No confirmed target at {sid}. Updated belief -> {{{formatted}}}."
        )
        self.state = MissionState.SELECT_STATION

    def _complete_confirmed_target(self) -> None:
        assert self.active_station_id is not None
        self.memory.record_sighting(self.target_name, self.active_station_id)
        if self.return_home_on_success and "HOME" in self.graph.nodes:
            _, home_dist = self.graph.shortest_path(self.current_node_id, "HOME")
            self.total_travel_distance_m += home_dist
            self.current_node_id = "HOME"
            self.decision_log.append(
                f"Logical HOME bookkeeping only (+{home_dist:.2f}m configured graph distance); "
                "return motion was not executed or measured."
            )
        self.state = MissionState.SUCCESS

    def build_report(self) -> MissionEvidenceReport:
        return MissionEvidenceReport(
            target_name=self.target_name,
            succeeded=(self.state == MissionState.SUCCESS),
            found_station_id=self.active_station_id
            if self.state == MissionState.SUCCESS
            else None,
            heuristic_score=self.final_confidence,
            stations_visited=list(self.stations_visited),
            rejected_distractors=self.rejected_distractors,
            tag_recovery_events=self.tag_recovery_events,
            total_travel_distance_m=self.total_travel_distance_m,
            evidence_crops=list(self.confirmed_crops),
            evidence_angles_deg=list(self.confirmed_angles),
            decision_log=list(self.decision_log),
            return_home_result=(
                "logical_graph_update_only"
                if self.state == MissionState.SUCCESS
                and self.return_home_on_success
                and "HOME" in self.graph.nodes
                else "not_performed"
            ),
        )
