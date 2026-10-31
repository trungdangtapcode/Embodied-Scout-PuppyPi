import type { Observation } from "./types";

export interface RoomObservation extends Observation {
  object_name: string;
  effective_status: "present" | "absent" | "unknown";
}
export interface RoomAnswer {
  id: string;
  created_at: string;
  object_name: string;
  kind: "last_seen" | "seen_during" | "stayed_at";
  station: string | null;
  start_at: string | null;
  end_at: string | null;
  mode: string;
  status: "supported" | "refuted" | "unknown";
  reason: string;
  evidence: RoomObservation[];
  evidence_truncated: boolean;
  continuous_coverage_verified: boolean;
}
export interface RoomMemory {
  generated_at: string;
  mode: string;
  regions: string[];
  objects: {
    id: string;
    name: string;
    reference_image_sha: string;
    last_seen: Observation | null;
    latest_observation: Observation | null;
  }[];
  timeline: RoomObservation[];
  timeline_truncated: boolean;
  recent_queries: RoomAnswer[];
}
export interface SceneCandidate {
  index: number;
  crop_image_sha: string;
  bbox_xywh: number[];
  matches: { object_id: string; object_name: string; score: number; similarity: number }[];
}
export interface SceneAnalysis {
  id: string;
  captured_at: string;
  image_sha: string;
  mode: string;
  frame_id: string;
  candidates: SceneCandidate[];
}
