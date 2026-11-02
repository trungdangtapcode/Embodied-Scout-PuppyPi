import { useEffect, useState } from "preact/hooks";
import { Search, CircleStop, Download, MapPin, ChevronRight } from "lucide-preact";
import { api, evidence, post, when } from "./api";
import type { ObjectRecord } from "./types";

type Frame = { image_sha: string; captured_at: string; frame_id: string };
type Match = {
  reference_index: number;
  supported: boolean;
  inliers: number;
  matches: number;
  reference_coverage: number;
};
type Candidate = {
  crop_image_sha: string;
  descriptor_supported: boolean;
  matches: Match[];
  floor_xy: number[] | null;
  proposal_prompt_name?: string;
  identity_name?: string;
  reference_comparison: { best_score: number; margin: number | null; reason: string };
};
type View = { frame: Frame; pose: { x: number; y: number; yaw: number }; candidates: Candidate[] };
type Run = {
  id: string;
  object_id: string;
  status: string;
  created_at: string;
  views: View[];
  result: { verdict: string; station?: string; reason?: string } | null;
  model_readout?: { verdict: string; station?: string } | null;
  error: { code: string; message: string } | null;
  method: string;
};
type Sighting = {
  object_id: string;
  station: string;
  captured_at: string;
  search_id: string;
  evidence_views: { ordinal: number; frame: Frame }[];
};
type Overview = {
  enabled: boolean;
  quality_gate: string;
  worker: { alive: boolean } | null;
  runs: (Pick<Run, "id" | "object_id" | "status" | "created_at" | "result" | "error"> & {
    view_count: number;
    revision: string;
    stage: string;
  })[];
  sightings: Sighting[];
  method: string;
};

export function SearchConsole({ objects }: { objects: ObjectRecord[] }) {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [target, setTarget] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [selected, setSelected] = useState("");
  const [detail, setDetail] = useState<Run | null>(null);
  useEffect(() => {
    let disposed = false;
    const refresh = () =>
      api<Overview>("/search").then(
        (value) => {
          if (!disposed) {
            setOverview(value);
            setError("");
          }
        },
        (reason) => {
          if (!disposed) setError(String(reason));
        },
      );
    void refresh();
    const timer = setInterval(() => {
      void refresh();
    }, 1500);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, []);
  const active = overview?.runs.find((r) => ["queued", "running"].includes(r.status));
  const summary = overview?.runs.find((r) => r.id === selected) || active || overview?.runs[0];
  useEffect(() => {
    if (!summary) return;
    const controller = new AbortController();
    void api<Run>(`/search/${summary.id}`, { signal: controller.signal })
      .then(setDetail)
      .catch((reason) => {
        if (!controller.signal.aborted) setError(String(reason));
      });
    return () => controller.abort();
  }, [summary?.id, summary?.revision]);
  const run = detail?.id === summary?.id ? detail : null;
  const objectId = target || objects[0]?.id || "";
  const name = (id: string) => objects.find((o) => o.id === id)?.name || id;
  async function start() {
    setPending(true);
    setError("");
    try {
      const created = await post<Run>("/search", {
        object_id: objectId,
        request_key: crypto.randomUUID(),
      });
      setSelected(created.id);
      setOverview(await api<Overview>("/search"));
    } catch (reason) {
      setError(String(reason));
    } finally {
      setPending(false);
    }
  }
  async function cancel() {
    if (!active) return;
    try {
      await post(`/search/${active.id}/cancel`);
      setOverview(await api<Overview>("/search"));
    } catch (reason) {
      setError(String(reason));
    }
  }
  async function download() {
    if (!run) return;
    let exported: Run;
    try {
      exported = await api<Run>(`/search/${run.id}?export=true`);
    } catch (reason) {
      setError(String(reason));
      return;
    }
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(exported, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `search-${run.id}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }
  return (
    <div class="search-console">
      <section class="panel search-request">
        <div class="panel-heading">
          <div>
            <span class="eyebrow">TEACH → SEARCH → VERIFY → REMEMBER</span>
            <h2>Find a registered object</h2>
          </div>
          <Search size={22} />
        </div>
        <p role="status">
          {overview?.quality_gate === "QUALIFIED_SYNTHETIC_PROFILE"
            ? "Qualified synthetic profile · real-room quality unverified"
            : "Identity unqualified · automatic memory blocked"}
        </p>
        <label class="field">
          Registered target
          <select
            aria-label="Search target"
            value={objectId}
            onChange={(e) => setTarget(e.currentTarget.value)}
          >
            {objects.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </select>
        </label>
        <div class="search-actions">
          <button
            class="button primary"
            onClick={() => void start()}
            disabled={
              pending || !!active || !objectId || !overview?.enabled || !overview.worker?.alive
            }
          >
            <Search size={17} />
            Start station search
          </button>
          <button class="button danger" disabled={!active} onClick={() => void cancel()}>
            <CircleStop size={17} />
            Cancel and stop
          </button>
        </div>
        <small>
          {overview?.worker?.alive
            ? "Search worker connected"
            : "Search worker unavailable — inference cannot start"}
        </small>
        <details class="search-method">
          <summary>Method and limitations</summary>
          <p>
            Actual YOLOE proposals → DINOv2 gallery comparison → DISK/LightGlue correspondences.
            Custom multi-view geometry; calibrated AprilTags and PythonRobotics navigation.
          </p>
          <p class="search-disclosure">
            Kinematic simulator; supplied map and reference images. Inconclusive does not prove
            absence. Matching shared surfaces does not establish exact identity. No learned world
            model or physical verification.
          </p>
          <small>Qualification: {overview?.quality_gate || "unknown"}</small>
        </details>
        {error && (
          <p role="alert" class="error">
            {error}
          </p>
        )}
      </section>
      <section class="panel">
        <div class="panel-heading">
          <h2>Search evidence</h2>
          <button class="text-button" disabled={!run} onClick={download}>
            <Download size={16} />
            Export run
          </button>
        </div>
        {!!overview?.runs.length && (
          <label class="field">
            Run
            <select
              aria-label="Search run"
              value={run?.id || ""}
              onChange={(e) => setSelected(e.currentTarget.value)}
            >
              {overview.runs.map((r) => (
                <option key={r.id} value={r.id}>
                  {when(r.created_at)} · {name(r.object_id)} · {r.status}
                </option>
              ))}
            </select>
          </label>
        )}
        {!run ? (
          <p>
            Enroll at least two reference views in Library, then start a search on the calibrated
            search simulator.
          </p>
        ) : (
          <>
            <div class="search-verdict">
              <span class="badge">{run.status}</span>
              <strong>
                {run.result?.verdict ||
                  (run.status === "running" ? "Moving / collecting evidence" : "No verdict")}
              </strong>
              {run.result?.station && (
                <span>
                  <MapPin size={15} />
                  {run.result.station}
                </span>
              )}
            </div>
            {run.error && (
              <p role="alert">
                {run.error.code}: {run.error.message}
              </p>
            )}
            {!run.result && run.model_readout && (
              <p>
                Recorded model readout: {run.model_readout.verdict}. Final publication: {run.status}
                . A model readout alone is not a verified memory record.
              </p>
            )}
            {run.result?.reason && <p>{run.result.reason.replaceAll("_", " ")}</p>}
            <p class="search-disclosure">
              {run.method}. Captures below are synthetic rendered input processed by actual models;
              region names are never model identity labels.
            </p>
            <div class="search-views">
              {run.views.map((view, index) => (
                <article key={view.frame.frame_id} class="search-view">
                  <img src={evidence(view.frame.image_sha)} alt={`Search capture ${index + 1}`} />
                  <div>
                    <h3>
                      View {index + 1} <ChevronRight size={15} />
                      {when(view.frame.captured_at)}
                    </h3>
                    <small>
                      Observed tag pose: {view.pose.x.toFixed(2)}, {view.pose.y.toFixed(2)} m ·{" "}
                      {((view.pose.yaw * 180) / Math.PI).toFixed(1)}°
                    </small>
                    <p>{view.candidates.length} model proposals for this target</p>
                    {view.candidates.map((candidate, i) => (
                      <details key={i}>
                        <summary>
                          Candidate {i + 1} ·{" "}
                          {candidate.descriptor_supported
                            ? "descriptor supported"
                            : "descriptor rejected"}
                        </summary>
                        <img
                          class="search-crop"
                          src={evidence(candidate.crop_image_sha)}
                          alt={`Model candidate ${i + 1}`}
                        />
                        {candidate.proposal_prompt_name && (
                          <p>
                            YOLOE proposal label: {candidate.proposal_prompt_name}
                            <br />
                            DINOv2 gallery identity: {candidate.identity_name}
                          </p>
                        )}
                        <p>
                          Cosine {candidate.reference_comparison.best_score.toFixed(3)} · margin{" "}
                          {candidate.reference_comparison.margin === null
                            ? "unavailable"
                            : candidate.reference_comparison.margin.toFixed(3)}
                          . Uncalibrated comparison scores.
                        </p>
                        {candidate.matches.map((m) => (
                          <p key={m.reference_index}>
                            Reference {m.reference_index + 1}: {m.inliers}/{m.matches} geometric
                            inliers · {(m.reference_coverage * 100).toFixed(0)}% coverage ·{" "}
                            {m.supported ? "supported" : "insufficient"}
                          </p>
                        ))}
                      </details>
                    ))}
                  </div>
                </article>
              ))}
            </div>
          </>
        )}
      </section>
      <section class="panel">
        <div class="panel-heading">
          <h2>Automatic recorded sightings</h2>
          <MapPin size={20} />
        </div>
        <p>
          Model-derived historical observations, separate from operator assertions. They do not
          establish the current room state.
        </p>
        {!overview?.sightings.length ? (
          <p>No confirmed model sighting. A completed search may remain inconclusive.</p>
        ) : (
          overview.sightings.map((s) => (
            <article class="search-sighting" key={s.search_id}>
              <strong>
                {name(s.object_id)} · {s.station}
              </strong>
              <span>{when(s.captured_at)}</span>
              <small>Learned inference + custom geometric verification · synthetic</small>
              <div>
                {s.evidence_views.map((v) => (
                  <img
                    key={v.ordinal}
                    src={evidence(v.frame.image_sha)}
                    alt={`Recorded sighting view ${v.ordinal + 1}`}
                  />
                ))}
              </div>
            </article>
          ))
        )}
      </section>
    </div>
  );
}
