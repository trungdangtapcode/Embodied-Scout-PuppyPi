export interface State {
  mode: "synthetic" | "physical";
  connected: boolean;
  camera: {
    available: boolean;
    frame_id: string | null;
    age_s: number | null;
    fresh: boolean;
    captured_at: string | null;
    freshness_verified: boolean;
  };
  control: {
    enabled: boolean;
    ready: boolean;
    armed: boolean;
    owned: boolean;
    reason: string;
    challenge: string;
    command: { vx_cm_s: number; yaw_rate_rad_s: number };
    last_ack_at: string | null;
    lease_s: number;
  };
  events: { id: string; at: string; kind: string; message: string }[];
}
export interface ObjectRecord {
  id: string;
  name: string;
  created_at: string;
  references: { image_sha: string }[];
}
export interface Observation {
  id: string;
  assertion: string;
  station: string;
  captured_at: string;
  image_sha: string;
  mode: string;
  source: string;
  provenance: Record<string, unknown>;
}
export interface Checklist {
  id: string;
  name: string;
  rules: { object_id: string; expected_station: string }[];
}
export interface Report {
  id: string;
  created_at: string;
  mode: string;
  checklist: Checklist;
  summary: { pass: number; fail: number; unknown: number };
  findings: {
    object_name: string;
    expected_station: string;
    reference_image_sha: string;
    status: "pass" | "fail" | "unknown";
    reason: string;
    evidence: Observation[];
  }[];
}
export interface ModelSighting {
  object_id: string;
  station: string;
  captured_at: string;
  search_id: string;
  mode: string;
  evidence_views: { ordinal: number; frame: { image_sha: string; captured_at: string } }[];
}
export interface History {
  automatic_sightings?: ModelSighting[];
  observations: Observation[];
  last_seen: { last_seen: Observation | null };
}
