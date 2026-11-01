import { useEffect, useState } from "preact/hooks";
import { ScanEye, X } from "lucide-preact";
import { api, post, evidence, when } from "./api";
import { t } from "./i18n";
import type { ObjectRecord } from "./types";
import type { Robot } from "./useRobot";

type Detection = {
  detection_index: number;
  xyxy: number[];
  model_score: number;
  prompt_name: string;
  prompt_object_id: string;
  mask_polygon_xy: number[][];
};
type VisionFrame = {
  frame_id: string;
  image_sha: string;
  captured_at: string;
  width: number;
  height: number;
  elapsed_s: number;
  detections: Detection[];
  tracks: { track_id: number; detection_index: number; xyxy: number[] }[];
};
type VisionJob = {
  id: string;
  created_at: string;
  status: string;
  stage: string;
  error_code: string | null;
  result: {
    frames: VisionFrame[];
    provenance: { revision: string; checkpoint_sha256: string; device: string; method: string };
  } | null;
  steps: { stage: string; message?: string }[];
};
type Overview = {
  enabled: boolean;
  mode: string;
  model: string;
  worker: { alive: boolean } | null;
  jobs: VisionJob[];
};
const active = (job: VisionJob) => ["queued", "running"].includes(job.status);
const statusLabel = (job: VisionJob) => job.status === "succeeded" ? t("Executed / quality unverified") : job.status;

export function VisionConsole({ robot }: { robot: Robot }) {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [objects, setObjects] = useState<ObjectRecord[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [openJob, setOpenJob] = useState("");
  const [frameIndex, setFrameIndex] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let disposed = false;
    const load = async () => {
      try {
        const [vision, library] = await Promise.all([api<Overview>("/vision"), api<ObjectRecord[]>("/objects")]);
        if (!disposed) { setOverview(vision); setObjects(library); }
      } catch (e) {
        if (!disposed) setError((e as Error).message);
      }
    };
    void load();
    const timer = setInterval(() => { if (robot.online && !document.hidden) void load(); }, 1500);
    return () => { disposed = true; clearInterval(timer); };
  }, [robot.online]);
  const run = async (action: () => Promise<void>) => {
    setBusy(true); setError("");
    try { await action(); setOverview(await api<Overview>("/vision")); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  const job = overview?.jobs.find(j => j.id === openJob) || overview?.jobs[0];
  const frames = job?.result?.frames || [];
  const frame = frames[Math.min(frameIndex, frames.length - 1)];
  const prompts = objects.filter(o => selected.includes(o.id)).map(o => o.id);
  const running = overview?.jobs.some(active);
  return (
    <section class="vision-console panel" aria-label={t("Learned visual perception")}>
      <div class="section-title">
        <div><span class="eyebrow">YOLOE / SAVPE + BYTETRACK</span><h2>{t("See the model's evidence.")}</h2></div>
        <span class={`badge ${overview?.worker?.alive ? "green" : "amber"}`}>
          {t(overview?.worker?.alive ? "Vision worker online" : "Vision worker unavailable")}
        </span>
      </div>
      <p class="muted">{t("Actual upstream visual prompting and segmentation, followed by ByteTrack association. Candidate labels can be wrong. Track IDs apply only within this recorded window.")}</p>
      <small>{overview?.model || "YOLOE"} · {overview?.mode || "…"} · CPU</small>
      {!overview?.enabled && <p class="room-caveat">{t("Learned vision is disabled. Run vision setup and enable the app profile; no baseline is substituted.")}</p>}
      {error && <p class="banner" role="alert">{error}</p>}
      <fieldset class="vision-prompts">
        <legend>{t("Reference objects supplied to the model")}</legend>
        {objects.length === 0 && <p class="muted">{t("Teach an object with cropped reference images in Library first.")}</p>}
        {objects.map(o => <label key={o.id} class="vision-prompt">
          <input type="checkbox" checked={selected.includes(o.id)}
            onChange={() => setSelected(selected.includes(o.id) ? selected.filter(id => id !== o.id) : [...selected, o.id])} />
          <img src={evidence(o.references[0].image_sha)} alt="" />
          <span>{o.name}</span>
        </label>)}
      </fieldset>
      <div class="vision-actions">
        <button class="button primary" disabled={busy || running || !overview?.enabled || !robot.online || !prompts.length || !robot.state?.camera.fresh || robot.armed}
          onClick={() => void run(async () => {
            const result = await post<VisionJob>("/vision/jobs", { frame_id: robot.displayed.current, object_ids: prompts, request_key: crypto.randomUUID() });
            setOpenJob(result.id); setFrameIndex(0);
          })}><ScanEye size={17} />{t("Analyze camera window")}</button>
        <small>{t("Saved frames ending at the displayed image. No robot motion is requested.")}</small>
      </div>
      {overview && !overview.worker?.alive && overview.enabled && <p class="room-caveat">{t("Jobs remain queued until the separate CPU worker starts.")}</p>}
      {!!overview?.jobs.length && <div class="vision-run-tabs" aria-label={t("Vision runs")}>
        {overview.jobs.map(j => <button key={j.id} class={`memory-run ${j.id === job?.id ? "selected" : ""}`}
          aria-pressed={j.id === job?.id} onClick={() => { setOpenJob(j.id); setFrameIndex(0); }}>
          <span>{statusLabel(j)}</span><small>{when(j.created_at)}</small>
        </button>)}
      </div>}
      {job && <div class="vision-result" aria-label={t("Vision result")}>
        <div class="section-title"><strong>{t("Run status")}: {statusLabel(job)}{job.status !== "succeeded" && ` · ${job.stage}`}</strong>
          {active(job) && <button class="button secondary" disabled={busy || !robot.online}
            onClick={() => void run(async () => { await post(`/vision/jobs/${job.id}/cancel`); })}><X size={16} />{t("Cancel vision job")}</button>}
        </div>
        {job.error_code && <p class="banner" role="alert">{job.error_code} · {t("Inference failed. No substitute result was generated.")}</p>}
        {frame && <>
          <div class="vision-evidence-layout">
            <div class="vision-image">
              <svg viewBox={`0 0 ${frame.width} ${frame.height}`} role="img" aria-label={t("Model detections on saved camera image")}>
                <image href={evidence(frame.image_sha)} width={frame.width} height={frame.height} />
                {frame.detections.map(d => <g key={d.detection_index}>
                  <polygon points={d.mask_polygon_xy.map(p => p.join(",")).join(" ")} class="vision-mask" />
                  <rect x={d.xyxy[0]} y={d.xyxy[1]} width={d.xyxy[2] - d.xyxy[0]} height={d.xyxy[3] - d.xyxy[1]} class="vision-box" />
                  <text x={d.xyxy[0] + 3} y={Math.max(16, d.xyxy[1] - 5)} class="vision-box-label">{d.detection_index + 1}</text>
                </g>)}
              </svg>
              <span class="vision-image-caption">{overview?.mode} · {t("Model output / unverified candidates")}</span>
            </div>
            <div class="vision-detections">
              <span class="eyebrow">{t("DETECTIONS / TRACK ASSOCIATIONS")}</span>
              {frame.detections.length === 0 && <p>{t("No detections above the configured threshold. This does not prove absence.")}</p>}
              {frame.detections.map(d => {
                const track = frame.tracks.find(tr => tr.detection_index === d.detection_index);
                return <div class="vision-detection" key={d.detection_index}>
                  <strong>{d.detection_index + 1}. {d.prompt_name}</strong>
                  <small>{t("Model score")}: {d.model_score.toFixed(3)} · {track ? `${t("Track")} #${track.track_id}` : t("Unassociated")}</small>
                </div>;
              })}
              <small>{t("Scores are uncalibrated. Names come from reference enrollment; exact identity is not verified.")}</small>
            </div>
          </div>
          <label class="vision-scrubber">{t("Recorded frame")} {Math.min(frameIndex + 1, frames.length)} / {frames.length}
            <input type="range" min={0} max={frames.length - 1} value={Math.min(frameIndex, frames.length - 1)} onInput={e => setFrameIndex(Number(e.currentTarget.value))} />
          </label>
          <small>{when(frame.captured_at)} · {frame.elapsed_s.toFixed(3)} s · {frame.frame_id}</small>
          <p class="room-caveat">{t("This window is historical evidence. It does not establish current location, autonomous navigation or a predictive world model.")}</p>
        </>}
        {job.result && <details><summary>{t("Executed source and checkpoint")}</summary><pre>{JSON.stringify(job.result.provenance, null, 2)}</pre></details>}
        <details><summary>{t("Vision execution trace")}</summary><ol>{job.steps.map((step, i) => <li key={i}>{step.stage}{step.message && ` · ${step.message}`}</li>)}</ol></details>
        <a class="text-button" href={`/api/vision/jobs/${encodeURIComponent(job.id)}`} target="_blank" rel="noreferrer">{t("Open run JSON")}</a>
      </div>}
    </section>
  );
}
