"""Algorithm 3: Topological Active Search Planner & Sequential Baseline."""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

from teach_and_find.config import PlannerSettings


@dataclass(frozen=True)
class StationNode:
    """Node in the topological navigation graph."""

    station_id: str
    apriltag_id: int
    position_xy: tuple[float, float]
    heading_deg: float = 0.0
    is_search_station: bool = True
    visibility_quality: float = 1.0


@dataclass
class TopologicalGraph:
    """Undirected weighted topological map connecting HOME and search stations."""

    nodes: dict[str, StationNode] = field(default_factory=dict)
    adjacency: dict[str, dict[str, float]] = field(default_factory=dict)

    def add_node(self, node: StationNode) -> None:
        self.nodes[node.station_id] = node
        self.adjacency.setdefault(node.station_id, {})

    def add_edge(self, u: str, v: str, cost_m: float | None = None) -> None:
        if u not in self.nodes or v not in self.nodes:
            raise KeyError(f"Both '{u}' and '{v}' must exist in TopologicalGraph.")
        if cost_m is None:
            ux, uy = self.nodes[u].position_xy
            vx, vy = self.nodes[v].position_xy
            cost_m = math.hypot(vx - ux, vy - uy)
        self.adjacency[u][v] = float(cost_m)
        self.adjacency[v][u] = float(cost_m)

    @property
    def search_station_ids(self) -> list[str]:
        return sorted(sid for sid, node in self.nodes.items() if node.is_search_station)

    def shortest_path(self, start_id: str, goal_id: str) -> tuple[list[str], float]:
        """Compute shortest topological route and metric distance via Dijkstra."""
        if start_id == goal_id:
            return [start_id], 0.0

        pq: list[tuple[float, str, list[str]]] = [(0.0, start_id, [start_id])]
        best_cost: dict[str, float] = {start_id: 0.0}

        while pq:
            cost, curr, path = heapq.heappop(pq)
            if curr == goal_id:
                return path, cost
            if cost > best_cost.get(curr, float("inf")):
                continue
            for nxt, w in self.adjacency.get(curr, {}).items():
                ncost = cost + w
                if ncost < best_cost.get(nxt, float("inf")):
                    best_cost[nxt] = ncost
                    heapq.heappush(pq, (ncost, nxt, path + [nxt]))

        raise ValueError(f"No topological path between '{start_id}' and '{goal_id}'.")

    def max_pairwise_distance(self) -> float:
        ids = list(self.nodes.keys())
        max_d = 1.0
        for i, u in enumerate(ids):
            for v in ids[i + 1 :]:
                try:
                    _, d = self.shortest_path(u, v)
                    max_d = max(max_d, d)
                except ValueError:
                    continue
        return max_d


def build_default_lab_graph() -> TopologicalGraph:
    """Construct the standard 3-station + HOME controlled room topology."""
    graph = TopologicalGraph()
    graph.add_node(
        StationNode("HOME", apriltag_id=0, position_xy=(0.0, 0.0), heading_deg=90.0, is_search_station=False)
    )
    graph.add_node(
        StationNode("Station_A", apriltag_id=1, position_xy=(-1.35, 1.55), heading_deg=135.0, visibility_quality=0.95)
    )
    graph.add_node(
        StationNode("Station_B", apriltag_id=2, position_xy=(0.0, 2.25), heading_deg=90.0, visibility_quality=1.00)
    )
    graph.add_node(
        StationNode("Station_C", apriltag_id=3, position_xy=(1.45, 1.40), heading_deg=45.0, visibility_quality=0.95)
    )
    graph.add_edge("HOME", "Station_A")
    graph.add_edge("HOME", "Station_B")
    graph.add_edge("HOME", "Station_C")
    graph.add_edge("Station_A", "Station_B")
    graph.add_edge("Station_B", "Station_C")
    graph.add_edge("Station_A", "Station_C")
    return graph


def _binary_entropy(prob: float) -> float:
    p = max(1e-6, min(1.0 - 1e-6, prob))
    return float(-p * math.log2(p) - (1.0 - p) * math.log2(1.0 - p))


@dataclass(frozen=True)
class StationScoreBreakdown:
    """Explainable score components for dashboard display and thesis evaluation."""

    station_id: str
    belief_prob: float
    travel_distance_m: float
    normalized_cost: float
    info_gain: float
    total_score: float


class ActiveSearchPlanner:
    """Selects next search station via S(z) = alpha*P(target|z) - beta*D(z) + gamma*U(z)."""

    def __init__(
        self,
        graph: TopologicalGraph,
        settings: PlannerSettings | None = None,
    ) -> None:
        self.graph = graph
        self.settings = settings or PlannerSettings()
        self._max_dist = self.graph.max_pairwise_distance()
        self.belief: dict[str, float] = {}
        self.visit_counts: dict[str, int] = {}

    def initialize_belief(self, priors: dict[str, float] | None = None) -> dict[str, float]:
        stations = self.graph.search_station_ids
        if not priors:
            uniform = 1.0 / float(max(len(stations), 1))
            self.belief = {sid: uniform for sid in stations}
        else:
            raw = {sid: max(1e-4, float(priors.get(sid, 1.0))) for sid in stations}
            total = sum(raw.values())
            self.belief = {sid: val / total for sid, val in raw.items()}
        self.visit_counts = {sid: 0 for sid in stations}
        return dict(self.belief)

    def score_stations(
        self,
        current_node_id: str,
        exclude_exhausted: set[str] | None = None,
    ) -> list[StationScoreBreakdown]:
        excluded = exclude_exhausted or set()
        scores: list[StationScoreBreakdown] = []

        for sid in self.graph.search_station_ids:
            if sid in excluded:
                continue
            prob = self.belief.get(sid, 0.0)
            _, dist_m = self.graph.shortest_path(current_node_id, sid)
            norm_cost = dist_m / self._max_dist

            node = self.graph.nodes[sid]
            visits = self.visit_counts.get(sid, 0)
            novelty_decay = 1.0 / (1.0 + 1.5 * visits)
            info_gain = _binary_entropy(prob) * node.visibility_quality * novelty_decay

            total = (
                self.settings.alpha_prior * prob
                - self.settings.beta_travel_cost * norm_cost
                + self.settings.gamma_info_gain * info_gain
            )
            scores.append(
                StationScoreBreakdown(
                    station_id=sid,
                    belief_prob=prob,
                    travel_distance_m=dist_m,
                    normalized_cost=norm_cost,
                    info_gain=info_gain,
                    total_score=total,
                )
            )

        scores.sort(key=lambda item: item.total_score, reverse=True)
        return scores

    def select_next_station(
        self,
        current_node_id: str,
        exclude_exhausted: set[str] | None = None,
    ) -> StationScoreBreakdown | None:
        ranked = self.score_stations(current_node_id, exclude_exhausted=exclude_exhausted)
        return ranked[0] if ranked else None

    def register_negative_observation(
        self,
        station_id: str,
        coverage_factor: float = 1.0,
    ) -> dict[str, float]:
        """Bayesian posterior update across all stations when target is NOT found at station_id."""
        self.visit_counts[station_id] = self.visit_counts.get(station_id, 0) + 1
        eff_recall = max(0.05, min(0.98, self.settings.station_detection_recall * coverage_factor))
        p_z = self.belief.get(station_id, 0.0)
        denom = max(1e-6, 1.0 - eff_recall * p_z)

        updated: dict[str, float] = {}
        for sid, prob in self.belief.items():
            if sid == station_id:
                updated[sid] = ((1.0 - eff_recall) * prob) / denom
            else:
                updated[sid] = prob / denom

        total = sum(updated.values())
        self.belief = {sid: val / total for sid, val in updated.items()}
        return dict(self.belief)


class SequentialSearchPlanner:
    """Baseline fixed-order station planner (Station_A -> Station_B -> Station_C) for ablation."""

    def __init__(self, graph: TopologicalGraph) -> None:
        self.graph = graph
        self.visit_counts: dict[str, int] = {}
        self.belief: dict[str, float] = {}

    def initialize_belief(self, priors: dict[str, float] | None = None) -> dict[str, float]:
        stations = self.graph.search_station_ids
        uniform = 1.0 / float(max(len(stations), 1))
        self.belief = {sid: uniform for sid in stations}
        self.visit_counts = {sid: 0 for sid in stations}
        return dict(self.belief)

    def select_next_station(
        self,
        current_node_id: str,
        exclude_exhausted: set[str] | None = None,
    ) -> StationScoreBreakdown | None:
        excluded = exclude_exhausted or set()
        for sid in self.graph.search_station_ids:
            if sid in excluded or self.visit_counts.get(sid, 0) > 0:
                continue
            _, dist_m = self.graph.shortest_path(current_node_id, sid)
            return StationScoreBreakdown(
                station_id=sid,
                belief_prob=self.belief.get(sid, 0.0),
                travel_distance_m=dist_m,
                normalized_cost=dist_m,
                info_gain=0.0,
                total_score=0.0,
            )
        return None

    def register_negative_observation(
        self,
        station_id: str,
        coverage_factor: float = 1.0,
    ) -> dict[str, float]:
        self.visit_counts[station_id] = self.visit_counts.get(station_id, 0) + 1
        return dict(self.belief)
