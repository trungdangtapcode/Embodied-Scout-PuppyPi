import { useEffect, useState } from "preact/hooks";
import {
  ArrowRight,
  Camera,
  Check,
  Clock3,
  Download,
  MapPin,
  RefreshCw,
  ScanLine,
  Search,
} from "lucide-preact";
import { api, evidence, post, when } from "./api";
import { t } from "./i18n";
import { ResearchMemory } from "./ResearchMemory";
import type { ObjectRecord } from "./types";
import type { Robot } from "./useRobot";
import type { RoomAnswer, RoomMemory, SceneAnalysis, SceneCandidate } from "./roomTypes";

// Preserve the console's Manrope/forest/paper design. The evidence timeline is
// the focal interaction; region cards never imply measured floor geometry.
const reasonText = (reason: string) => {
  const messages: Record<string, string> = {
    historical_sighting: "A recorded sighting, not a claim about the current location.",
    recorded_witness: "A recorded observation supports presence within this time range.",
    recorded_counterexample:
      "A recorded observation contradicts continuous presence in this region.",
    unobserved_intervals: "Separate observations cannot establish what happened between captures.",
    capture_time_or_visibility_unknown:
      "Capture timing or visibility is insufficient for this time-range question.",
    conflicting_evidence: "The recorded observations conflict. Review the source images.",
    no_usable_evidence: "There is no usable recorded sighting for this question.",
    evidence_limit_reached: "Too much history to safely resolve this question in one assessment.",
  };
  return t(messages[reason] || reason);
};
const kindText = (kind: string) =>
  t(
    kind === "last_seen"
      ? "Last seen"
      : kind === "seen_during"
        ? "Seen during a time range"
        : "Stayed throughout a time range",
  );
const localInput = (date: Date) =>
  new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 19);

function AnswerView({ answer }: { answer: RoomAnswer }) {
  const download = () => {
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(answer, null, 2)], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `room-answer-${answer.id}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return (
    <section
      class={`room-answer ${answer.status}`}
      aria-label={t("Room answer")}
      aria-live="polite"
    >
      <div class="section-title">
        <span class={`badge ${answer.status === "supported" ? "green" : "amber"}`}>
          {t(
            answer.status === "supported"
              ? "Supported"
              : answer.status === "refuted"
                ? "Contradicted"
                : "Unknown",
          )}
        </span>
        <button class="icon-button" onClick={download} aria-label={t("Download answer")}>
          <Download size={17} />
        </button>
      </div>
      <h3>
        {answer.object_name}
        {answer.station ? ` · ${answer.station}` : ""}
      </h3>
      <p>{reasonText(answer.reason)}</p>
      {answer.start_at && answer.end_at && (
        <small>
          {when(answer.start_at)} — {when(answer.end_at)}
        </small>
      )}
      {answer.evidence_truncated && (
        <p class="room-caveat">
          {t("The evidence window is limited. No complete-history claim is made.")}
        </p>
      )}
      <div class="answer-evidence">
        {answer.evidence.slice(0, 4).map((row) => (
          <a key={row.id} href={evidence(row.image_sha)} target="_blank" rel="noreferrer">
            <img
              src={evidence(row.image_sha)}
              alt={t("Evidence at {station}", { station: row.station })}
            />
            <span>
              <strong>{row.station}</strong>
              <small>{when(row.captured_at)}</small>
            </span>
          </a>
        ))}
      </div>
      <small class="muted">
        {t("Based on recorded assertions. Continuous observation is not verified.")}
      </small>
    </section>
  );
}

function CandidateCard({
  candidate,
  disabled,
  confirmed,
  onConfirm,
}: {
  candidate: SceneCandidate;
  disabled: boolean;
  confirmed: boolean;
  onConfirm: (objectId: string) => void;
}) {
  const [objectId, setObjectId] = useState(candidate.matches[0]?.object_id || "");
  const selected = candidate.matches.find((match) => match.object_id === objectId);
  return (
    <article class="scene-candidate">
      <img
        src={evidence(candidate.crop_image_sha)}
        alt={t("Candidate {index}", { index: candidate.index + 1 })}
      />
      <div class="scene-candidate-body">
        <span class="eyebrow">{t("CANDIDATE {index}", { index: candidate.index + 1 })}</span>
        <label>
          {t("Suggested object")}
          <select
            aria-label={t("Candidate object {index}", { index: candidate.index + 1 })}
            value={objectId}
            disabled={disabled || confirmed}
            onChange={(event) => setObjectId(event.currentTarget.value)}
          >
            {candidate.matches.map((match) => (
              <option key={match.object_id} value={match.object_id}>
                {match.object_name}
              </option>
            ))}
          </select>
        </label>
        <small>
          {t("Appearance score {score} · not a probability", {
            score: (selected?.score || 0).toFixed(2),
          })}
        </small>
        <button
          class="button secondary wide"
          disabled={disabled || confirmed || !objectId}
          onClick={() => onConfirm(objectId)}
        >
          {confirmed ? <Check size={16} /> : <ArrowRight size={16} />}
          {t(confirmed ? "Sighting recorded" : "Confirm sighting")}
        </button>
      </div>
    </article>
  );
}

export function RoomConsole({
  robot,
  objects,
  onRefresh,
}: {
  robot: Robot;
  objects: ObjectRecord[];
  onRefresh: () => Promise<void>;
}) {
  const [room, setRoom] = useState<RoomMemory | null>(null);
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);
  const [objectId, setObjectId] = useState(objects[0]?.id || "");
  const [kind, setKind] = useState<RoomAnswer["kind"]>("last_seen");
  const [station, setStation] = useState("");
  const [start, setStart] = useState(localInput(new Date(Date.now() - 3600000)));
  const [end, setEnd] = useState(localInput(new Date()));
  const [answer, setAnswer] = useState<RoomAnswer | null>(null);
  const [analysis, setAnalysis] = useState<SceneAnalysis | null>(null);
  const [confirmed, setConfirmed] = useState<number[]>([]);
  const [observedRegion, setObservedRegion] = useState("");
  const [filter, setFilter] = useState("");
  const load = async () => setRoom(await api<RoomMemory>("/room"));
  useEffect(() => {
    const abort = new AbortController();
    void api<RoomMemory>("/room", { signal: abort.signal })
      .then((result) => {
        if (!abort.signal.aborted) setRoom(result);
      })
      .catch((error) => {
        if (!abort.signal.aborted) setError(error.message);
      });
    setObjectId((current) =>
      objects.some((obj) => obj.id === current) ? current : objects[0]?.id || "",
    );
    return () => abort.abort();
  }, [objects]);
  const run = async (work: () => Promise<void>) => {
    setWorking(true);
    setError("");
    try {
      await work();
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    } finally {
      setWorking(false);
    }
  };
  const ask = (event: Event) => {
    event.preventDefault();
    void run(async () => {
      setAnswer(
        await post<RoomAnswer>("/room/queries", {
          kind,
          object_id: objectId,
          ...(kind === "last_seen"
            ? {}
            : {
                station,
                start_at: new Date(start).toISOString(),
                end_at: new Date(end).toISOString(),
              }),
        }),
      );
      await load();
    });
  };
  const analyze = () =>
    void run(async () => {
      const result = await post<SceneAnalysis>("/room/analyses", {
        frame_id: robot.displayed.current,
      });
      setAnalysis(result);
      setConfirmed([]);
    });
  const confirm = (index: number, objectId: string) =>
    void run(async () => {
      await post(`/room/analyses/${analysis!.id}/confirm`, {
        proposal_index: index,
        object_id: objectId,
        station: observedRegion,
      });
      setConfirmed((current) => [...current, index]);
      await load();
      await onRefresh();
    });
  const disabled = working || !robot.online;
  const timeline = room?.timeline.filter((row) => !filter || row.station === filter) || [];
  return (
    <div class="room-console">
      <div class="room-intro">
        <div>
          <span class="eyebrow">{t("PLACES / OBJECTS / TIME")}</span>
          <h2>{t("Room memory")}</h2>
          <p>{t("Follow the evidence from a place to a moment.")}</p>
        </div>
        <button class="button secondary" disabled={disabled} onClick={() => void run(load)}>
          <RefreshCw size={16} />
          {t("Refresh memory")}
        </button>
      </div>
      {error && (
        <div class="banner" role="alert">
          {error}
        </div>
      )}
      <ResearchMemory robot={robot} />
      <details class="legacy-memory">
        <summary>{t("Operator assertions and appearance baseline")}</summary>
        <p class="muted">
          {t(
            "These comparison tools use operator assertions and a local appearance heuristic. They do not supply Mind Palace answers.",
          )}
        </p>
        <div class="room-workspace">
          <section class="panel room-regions">
            <div class="section-title">
              <h2>{t("Observed regions")}</h2>
              <MapPin size={18} />
            </div>
            <p class="muted">
              {t("Last recorded sightings. These are not live object positions.")}
            </p>
            {!room && !error && <p role="status">{t("Loading memory…")}</p>}
            {room && !room.regions.length && (
              <div class="empty">
                <MapPin size={28} />
                <h3>{t("Start with a sighting")}</h3>
                <p>{t("Record a region in Inspect, or analyze a camera view below.")}</p>
              </div>
            )}
            <div class="region-list">
              {room?.regions.map((region) => {
                const members = room.objects.filter((obj) => obj.last_seen?.station === region);
                return (
                  <button
                    key={region}
                    class={`region-card ${filter === region ? "selected" : ""}`}
                    onClick={() => {
                      setFilter(filter === region ? "" : region);
                      setStation(region);
                    }}
                  >
                    <span class="region-name">
                      <MapPin size={16} />
                      <strong>{region}</strong>
                      <span>{members.length}</span>
                    </span>
                    {members.length ? (
                      members.map((obj) => (
                        <span class="region-object" key={obj.id}>
                          <img src={evidence(obj.reference_image_sha)} alt="" />
                          <span>
                            <strong>{obj.name}</strong>
                            <small>{when(obj.last_seen!.captured_at)}</small>
                          </span>
                        </span>
                      ))
                    ) : (
                      <small>{t("No recorded positive sighting")}</small>
                    )}
                  </button>
                );
              })}
            </div>
            {room?.objects.some((obj) => !obj.last_seen) && (
              <p class="room-caveat">
                {t("{count} taught objects have no usable sighting in this mode.", {
                  count: room.objects.filter((obj) => !obj.last_seen).length,
                })}
              </p>
            )}
          </section>
          <section class="panel ask-room">
            <div class="section-title">
              <h2>{t("Ask Room")}</h2>
              <Search size={18} />
            </div>
            <p class="muted">{t("A precise question, with source images in the answer.")}</p>
            <form onSubmit={ask}>
              <label>
                {t("Question")}
                <select
                  value={kind}
                  onChange={(event) => setKind(event.currentTarget.value as RoomAnswer["kind"])}
                >
                  <option value="last_seen">{t("Where was it last seen?")}</option>
                  <option value="seen_during">{t("Was it seen here during this time?")}</option>
                  <option value="stayed_at">{t("Did it stay here throughout this time?")}</option>
                </select>
              </label>
              <label>
                {t("Object")}
                <select
                  required
                  value={objectId}
                  onChange={(event) => setObjectId(event.currentTarget.value)}
                >
                  <option value="" disabled>
                    {t("Choose a taught object")}
                  </option>
                  {objects.map((obj) => (
                    <option key={obj.id} value={obj.id}>
                      {obj.name}
                    </option>
                  ))}
                </select>
              </label>
              {kind !== "last_seen" && (
                <>
                  <label>
                    {t("Region")}
                    <input
                      required
                      maxLength={120}
                      value={station}
                      list="room-regions"
                      onInput={(event) => setStation(event.currentTarget.value)}
                    />
                  </label>
                  <div class="time-range">
                    <label>
                      {t("From")}
                      <input
                        required
                        type="datetime-local"
                        step="1"
                        value={start}
                        onInput={(event) => setStart(event.currentTarget.value)}
                      />
                    </label>
                    <label>
                      {t("Until")}
                      <input
                        required
                        type="datetime-local"
                        step="1"
                        value={end}
                        onInput={(event) => setEnd(event.currentTarget.value)}
                      />
                    </label>
                  </div>
                  <button
                    type="button"
                    class="text-button"
                    onClick={() => {
                      setStart(localInput(new Date(Date.now() - 3600000)));
                      setEnd(localInput(new Date()));
                    }}
                  >
                    {t("Use latest hour")}
                  </button>
                </>
              )}
              <button class="button primary wide" disabled={disabled || !objectId}>
                <Search size={16} />
                {t(working ? "Working…" : "Ask from evidence")}
              </button>
            </form>
            {answer && <AnswerView answer={answer} />}
            {!!room?.recent_queries.length && (
              <details class="recent-answers">
                <summary>{t("Saved answers")}</summary>
                {room.recent_queries.map((query) => (
                  <button key={query.id} onClick={() => setAnswer(query)}>
                    <span>
                      {query.object_name}
                      <small>{kindText(query.kind)}</small>
                    </span>
                    <Clock3 size={15} />
                  </button>
                ))}
              </details>
            )}
          </section>
        </div>
        <section class="panel scene-analysis">
          <div class="section-title">
            <h2>{t("Analyze a viewpoint")}</h2>
            <ScanLine size={18} />
          </div>
          <p>
            {t(
              "Find foreground candidates and compare them with taught objects. Review before recording a sighting.",
            )}
          </p>
          {robot.image && (
            <div class="scene-live-preview">
              <img
                src={robot.image.url}
                alt={t("Live scene view")}
                onLoad={() => robot.imageLoaded(robot.image!.id)}
                onError={robot.imageFailed}
              />
            </div>
          )}
          <div class="scene-toolbar">
            <button
              class="button primary"
              onClick={analyze}
              disabled={
                disabled ||
                !objects.length ||
                !robot.state?.camera.fresh ||
                !robot.image ||
                !robot.displayed.current ||
                robot.armed
              }
            >
              <Camera size={17} />
              {t("Analyze current view")}
            </button>
            <span class="muted">{t("Local appearance baseline · no model download")}</span>
          </div>
          {analysis && (
            <>
              <div class="analysis-source">
                <a href={evidence(analysis.image_sha)} target="_blank" rel="noreferrer">
                  <img src={evidence(analysis.image_sha)} alt={t("Analyzed camera frame")} />
                </a>
                <div>
                  <strong>{t("Frozen source frame")}</strong>
                  <p>{when(analysis.captured_at)}</p>
                  <small>
                    {t(
                      "Suggestions need confirmation. An empty candidate list does not establish absence.",
                    )}
                  </small>
                </div>
              </div>
              <label class="analysis-region">
                {t("Observed region")}
                <input
                  value={observedRegion}
                  maxLength={120}
                  placeholder={t("Where did you observe this?")}
                  list="room-regions"
                  onInput={(event) => setObservedRegion(event.currentTarget.value)}
                />
              </label>
              {analysis.candidates.length ? (
                <div class="candidate-grid">
                  {analysis.candidates.map((candidate) => (
                    <CandidateCard
                      key={`${analysis.id}:${candidate.index}`}
                      candidate={candidate}
                      confirmed={confirmed.includes(candidate.index)}
                      disabled={disabled || !observedRegion.trim()}
                      onConfirm={(object) => confirm(candidate.index, object)}
                    />
                  ))}
                </div>
              ) : (
                <p class="room-caveat">
                  {t(
                    "No foreground candidates in this view. Try a clearer or closer view; nothing was marked absent.",
                  )}
                </p>
              )}
            </>
          )}
        </section>
        <section class="panel room-timeline">
          <div class="section-title">
            <h2>{t("Evidence timeline")}</h2>
            <Clock3 size={18} />
          </div>
          <div class="timeline-toolbar">
            <p class="muted">{t("Capture order, with uncertainty kept visible.")}</p>
            {filter && (
              <button class="text-button" onClick={() => setFilter("")}>
                {t("Clear region filter")} · {filter}
              </button>
            )}
          </div>
          {!timeline.length && <p class="muted">{t("No observations in this view yet.")}</p>}
          {timeline.map((row, index) => (
            <div key={row.id} class="timeline-item">
              <a
                class="timeline-witness"
                href={evidence(row.image_sha)}
                target="_blank"
                rel="noreferrer"
              >
                <img
                  src={evidence(row.image_sha)}
                  alt={t("Evidence at {station}", { station: row.station })}
                />
              </a>
              <div class="timeline-copy">
                <time>{when(row.captured_at)}</time>
                <strong>{row.object_name}</strong>
                <span>
                  {row.station} ·{" "}
                  {t(
                    row.effective_status === "present"
                      ? "Recorded present"
                      : row.effective_status === "absent"
                        ? "Recorded absent"
                        : "Unclear observation",
                  )}
                </span>
                <small>
                  {t(row.source === "operator" ? "Operator assertion" : "Recorded assertion")} ·{" "}
                  {row.mode}
                </small>
                {index < timeline.length - 1 &&
                  row.captured_at !== timeline[index + 1].captured_at && (
                    <div class="observation-gap">{t("Between captures: not verified")}</div>
                  )}
              </div>
            </div>
          ))}
          {room?.timeline_truncated && (
            <p class="muted">
              {t("Showing the most recent observations; earlier history remains stored.")}
            </p>
          )}
        </section>
        <datalist id="room-regions">
          {room?.regions.map((region) => (
            <option value={region} key={region} />
          ))}
        </datalist>
      </details>
    </div>
  );
}
