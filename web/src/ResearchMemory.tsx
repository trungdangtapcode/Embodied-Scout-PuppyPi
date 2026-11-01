import { useEffect, useState } from "preact/hooks";
import { Camera, BookOpen, ArrowRight, X, RefreshCw } from "lucide-preact";
import { api, post, evidence, when } from "./api";
import { t } from "./i18n";
import type { Robot } from "./useRobot";

type View = { id: string; name: string; region_name: string };
type Episode = { id: string; name: string; created_at: string };
type Capture = {
  id: string;
  episode_id: string;
  episode_name?: string;
  region_name: string;
  view_name: string;
  image_sha: string;
  captured_at: string;
  description: { description: string; visibility: string } | null;
};
type MemoryResult = {
  answer?: string;
  reason?: string;
  description?: { description: string };
  citations?: string[];
  evidence?: Capture[];
  provenance?: { model: string; revision: string; calls: unknown[] };
};
type Job = {
  id: string;
  kind: string;
  status: string;
  stage: string;
  created_at: string;
  error_code: string | null;
  request: { question?: string };
  result: MemoryResult | null;
  steps: {
    stage: string;
    event?: string;
    elapsed_s?: number;
    output?: unknown;
    http_status?: number;
  }[];
};
type Overview = {
  enabled: boolean;
  mode: string;
  model: string;
  worker: { alive: boolean; status: string; error_code: string | null } | null;
  views: View[];
  episodes: Episode[];
  captures: Capture[];
  jobs: Job[];
};

const terminal = (job: Job) => !["queued", "running"].includes(job.status);

export function ResearchMemory({ robot }: { robot: Robot }) {
  const [memory, setMemory] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [region, setRegion] = useState("");
  const [viewName, setViewName] = useState("");
  const [viewId, setViewId] = useState("");
  const [episodeName, setEpisodeName] = useState("");
  const [episodeId, setEpisodeId] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [question, setQuestion] = useState("");
  const [openJob, setOpenJob] = useState("");
  const load = async () => setMemory(await api<Overview>("/memory"));
  useEffect(() => {
    let disposed = false;
    const refresh = async () => {
      try {
        const result = await api<Overview>("/memory");
        if (!disposed) setMemory(result);
      } catch (e) {
        if (!disposed) setError((e as Error).message);
      }
    };
    void refresh();
    const timer = setInterval(() => {
      if (robot.online && !document.hidden) void refresh();
    }, 1500);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, [robot.online]);
  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await action();
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  if (!memory)
    return (
      <section class="panel">
        <p>{error || t("Loading research memory…")}</p>
      </section>
    );
  const disabled = busy || !robot.online || !memory.enabled;
  const currentView = viewId || memory.views[0]?.id || "";
  const currentEpisode = episodeId || memory.episodes[0]?.id || "";
  const active = memory.jobs.filter((j) => !terminal(j));
  const job = memory.jobs.find((j) => j.id === openJob) || memory.jobs[0];
  const toggleEpisode = (id: string) =>
    setSelected(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);
  return (
    <section class="research-memory panel" aria-label={t("Mind Palace memory")}>
      <div class="section-title">
        <div>
          <span class="eyebrow">{t("RECORDED MEMORY / MIND PALACE")}</span>
          <h2>{t("Capture. Recall. Inspect.")}</h2>
        </div>
        <span class={`badge ${memory.worker?.alive ? "green" : "amber"}`}>
          {t(memory.worker?.alive ? "Worker online" : "Worker unavailable")}
        </span>
      </div>
      <p class="muted">
        {t(
          "Ask about saved camera captures. Answers do not establish current room state or continuous presence.",
        )}
      </p>
      <small>
        {memory.model} · {memory.mode}
      </small>
      <p class="muted">
        {t(
          "Uses pinned Mind Palace source for retrieval and reasoning with a VLM API. Regions and viewpoints are operator registered; no automatic 3D map, tracking or learned world model.",
        )}
      </p>
      {!memory.enabled && (
        <p class="banner">
          {t(
            "Research memory is disabled on this host. Enable and start the memory worker; no fallback is used.",
          )}
        </p>
      )}
      {memory.enabled && !memory.worker?.alive && (
        <p class="room-caveat">
          {t(
            "Captures can queue while the worker is offline. They will not receive a synthetic answer.",
          )}{" "}
          {memory.worker?.error_code}
        </p>
      )}
      {error && (
        <p class="banner" role="alert">
          {error}
        </p>
      )}
      <div class="research-workspace">
        <div class="memory-capture-form">
          <h3>
            <Camera size={17} /> {t("Capture memory")}
          </h3>
          <details>
            <summary>{t("Register a viewpoint")}</summary>
            <label>
              {t("Region name")}
              <input value={region} onInput={(e) => setRegion(e.currentTarget.value)} />
            </label>
            <label>
              {t("Viewpoint name")}
              <input value={viewName} onInput={(e) => setViewName(e.currentTarget.value)} />
            </label>
            <button
              class="button secondary"
              disabled={disabled || !region.trim() || !viewName.trim()}
              onClick={() =>
                void run(async () => {
                  const view = await post<View>("/memory/views", {
                    region_name: region,
                    viewpoint_name: viewName,
                  });
                  setViewId(view.id);
                  setRegion("");
                  setViewName("");
                })
              }
            >
              {t("Save viewpoint")}
            </button>
            <small>{t("Region names are registered metadata. Geometry is unknown.")}</small>
          </details>
          <label>
            {t("Memory viewpoint")}
            <select
              aria-label={t("Memory viewpoint")}
              value={currentView}
              onChange={(e) => setViewId(e.currentTarget.value)}
            >
              <option value="">{t("Choose a viewpoint")}</option>
              {memory.views.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.region_name} · {v.name}
                </option>
              ))}
            </select>
          </label>
          <div class="episode-create">
            <label>
              {t("New episode name")}
              <input value={episodeName} onInput={(e) => setEpisodeName(e.currentTarget.value)} />
            </label>
            <button
              class="button secondary"
              disabled={disabled || !episodeName.trim()}
              onClick={() =>
                void run(async () => {
                  const episode = await post<Episode>("/memory/episodes", { name: episodeName });
                  setEpisodeId(episode.id);
                  setEpisodeName("");
                })
              }
            >
              {t("Create episode")}
            </button>
          </div>
          <label>
            {t("Capture episode")}
            <select
              aria-label={t("Capture episode")}
              value={currentEpisode}
              onChange={(e) => setEpisodeId(e.currentTarget.value)}
            >
              <option value="">{t("Choose an episode")}</option>
              {memory.episodes.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.name}
                </option>
              ))}
            </select>
          </label>
          <button
            class="button primary"
            disabled={
              disabled ||
              !currentView ||
              !currentEpisode ||
              !robot.displayed.current ||
              !robot.state?.camera.fresh ||
              robot.armed
            }
            onClick={() =>
              void run(async () => {
                const job = await post<Job>("/memory/captures", {
                  frame_id: robot.displayed.current,
                  episode_id: currentEpisode,
                  view_id: currentView,
                  request_key: crypto.randomUUID(),
                });
                setOpenJob(job.id);
              })
            }
          >
            <Camera size={16} />
            {t("Capture displayed frame")}
          </button>
          <small>
            {t(
              "One frame per viewpoint in an episode. Start another episode for a later observation.",
            )}
          </small>
        </div>
        <div class="memory-question-form">
          <h3>
            <BookOpen size={17} /> {t("Ask memory")}
          </h3>
          <fieldset>
            <legend>{t("Episodes to search")}</legend>
            {memory.episodes.length === 0 && (
              <p class="muted">{t("Create an episode and complete a capture first.")}</p>
            )}
            {memory.episodes.map((e) => (
              <label class="episode-choice" key={e.id}>
                <input
                  type="checkbox"
                  checked={selected.includes(e.id)}
                  onChange={() => toggleEpisode(e.id)}
                />
                <span>
                  {e.name}
                  <small>{when(e.created_at)}</small>
                </span>
              </label>
            ))}
          </fieldset>
          <label>
            {t("Memory question")}
            <textarea
              rows={3}
              value={question}
              onInput={(e) => setQuestion(e.currentTarget.value)}
              placeholder={t("What was visible in these saved observations?")}
            />
          </label>
          <button
            class="button primary"
            disabled={disabled || !question.trim() || !selected.length}
            onClick={() =>
              void run(async () => {
                const job = await post<Job>("/memory/questions", {
                  question,
                  episode_ids: selected,
                  request_key: crypto.randomUUID(),
                  scope: "recorded_memory",
                });
                setOpenJob(job.id);
              })
            }
          >
            {t("Ask Mind Palace")}
            <ArrowRight size={16} />
          </button>
        </div>
      </div>
      {active.length > 0 && (
        <p class="memory-running" role="status">
          {t("Jobs in progress")}: {active.length} ·{" "}
          {t("Capture and control remain independent of inference.")}
        </p>
      )}
      {memory.jobs.length > 0 && (
        <div class="memory-run-layout">
          <div class="memory-run-list" aria-label={t("Memory runs")}>
            {memory.jobs.map((j) => (
              <button
                key={j.id}
                class={`memory-run ${j.id === job?.id ? "selected" : ""}`}
                onClick={() => setOpenJob(j.id)}
              >
                <span>{j.kind === "question" ? j.request.question : t("Camera capture")}</span>
                <small>
                  {j.status} · {j.stage} · {when(j.created_at)}
                </small>
              </button>
            ))}
          </div>
          {job && (
            <section class="memory-result" aria-label={t("Mind Palace result")} aria-live="polite">
              <div class="section-title">
                <span class={`badge ${job.status === "succeeded" ? "green" : "amber"}`}>
                  {job.status}
                </span>
                {!terminal(job) && (
                  <button
                    class="button secondary"
                    disabled={busy || !robot.online}
                    onClick={() =>
                      void run(async () => {
                        await post(`/memory/jobs/${job.id}/cancel`);
                      })
                    }
                  >
                    <X size={15} />
                    {t("Cancel job")}
                  </button>
                )}
              </div>
              {job.request.question && <h3>{job.request.question}</h3>}
              {!terminal(job) && (
                <p>
                  <RefreshCw size={15} /> {t("Current stage")}: {job.stage}
                </p>
              )}
              {job.error_code && (
                <p class="banner" role="alert">
                  {job.error_code} · {t("The run failed. No fallback answer was generated.")}
                </p>
              )}
              {job.status === "cancelled" && (
                <p>{t("Cancelled. An API request already sent may still incur usage.")}</p>
              )}
              {job.result?.answer && (
                <>
                  <p class="memory-answer-text">{job.result.answer}</p>
                  <small>
                    {t(
                      "Model-generated answer. Citation IDs are checked against inspected images; factual correctness is not independently verified.",
                    )}
                  </small>
                </>
              )}
              {job.result?.reason && <p>{job.result.reason}</p>}
              {job.result?.description && <p>{job.result.description.description}</p>}
              <div class="memory-contact-sheet">
                {job.result?.evidence?.map((c) => (
                  <a key={c.id} href={evidence(c.image_sha)} target="_blank" rel="noreferrer">
                    <img
                      src={evidence(c.image_sha)}
                      alt={t("Inspected capture at {station}", { station: c.region_name })}
                      loading="lazy"
                    />
                    <span>
                      {c.region_name} · {c.view_name} {c.episode_name && ` · ${c.episode_name}`}
                    </span>
                    <small>
                      {when(c.captured_at)} ·{" "}
                      {t(
                        job.result?.citations?.includes(c.id)
                          ? "Cited by model"
                          : "Image inspected",
                      )}
                    </small>
                  </a>
                ))}
              </div>
              {job.result?.provenance && (
                <small>
                  {job.result.provenance.model} · {job.result.provenance.revision.slice(0, 8)} ·{" "}
                  {job.result.provenance.calls.length} {t("API calls")}
                </small>
              )}
              <details>
                <summary>{t("Execution trace")}</summary>
                <ol>
                  {job.steps.map((step, i) => (
                    <li key={i}>
                      {step.stage} · {step.event || "recorded"}
                      {step.elapsed_s != null && ` · ${step.elapsed_s.toFixed(2)} s`}
                      {step.http_status != null && ` · HTTP ${step.http_status}`}
                      {step.output != null && (
                        <details>
                          <summary>{t("Model output")}</summary>
                          <pre>{JSON.stringify(step.output, null, 2)}</pre>
                        </details>
                      )}
                    </li>
                  ))}
                </ol>
              </details>
            </section>
          )}
        </div>
      )}
      {memory.captures.length > 0 && (
        <details class="memory-capture-history">
          <summary>
            {t("Saved memory captures")} ({memory.captures.length})
          </summary>
          <div class="memory-contact-sheet">
            {memory.captures.map((c) => (
              <a key={c.id} href={evidence(c.image_sha)} target="_blank" rel="noreferrer">
                <img
                  src={evidence(c.image_sha)}
                  alt={t("Memory capture at {station}", { station: c.region_name })}
                  loading="lazy"
                />
                <span>
                  {c.region_name} · {when(c.captured_at)}
                </span>
                <small>{c.description?.description || t("Description not available")}</small>
              </a>
            ))}
          </div>
        </details>
      )}
    </section>
  );
}
