import { useEffect, useRef, useState } from "preact/hooks";
import { ScanEye, Square, X } from "lucide-preact";
import { api, evidence, post } from "./api";
import { t } from "./i18n";
import type { Robot } from "./useRobot";

type Frame = {
  frame_id: string;
  image_sha: string;
  width: number;
  height: number;
  capture_unix_ms: number;
  captured_at: string;
};
type Observation = Frame & {
  sequence: number;
  generation: number;
  mask_sha: string;
  step_s: number;
  display_age_s: number;
  stale: boolean;
  observation_state: string;
};
type Session = {
  id: string;
  revision: number;
  generation: number;
  status: string;
  error_code: string | null;
  anchor: Frame;
  dropped_frames: number;
  preview: null | {
    selected: number;
    elapsed_s: number;
    candidates: { mask_sha: string; model_mask_quality_score: number; foreground_pixels: number }[];
  };
  stream: null | {
    phase: string;
    pending: number;
    peak_live_pending: number;
    producer_replacements: number;
    pending_replacements: number;
    skipped_frames: number;
  };
  latest: Observation | null;
  observations: Observation[];
};
type Overview = {
  enabled: boolean;
  device: string;
  offer_hz: number;
  worker: { alive: boolean; status: string } | null;
  sessions: Session[];
};
const active = (s: Session) =>
  ["selecting", "preview_pending", "preview_ready", "start_pending", "running"].includes(s.status);
const maskUrl = (sha: string) => `/api/tracking/masks/${sha}`;

function ProcessedFrame({ frame }: { frame: Observation }) {
  const loaded = useRef(new Set<string>());
  const [ready, setReady] = useState(false);
  const [failure, setFailure] = useState(false);
  const finish = (kind: string) => {
    loaded.current.add(kind);
    if (loaded.current.size !== 2) return;
    setReady(true);
    requestAnimationFrame(() =>
      requestAnimationFrame(() => {
        window.dispatchEvent(
          new CustomEvent("puppypi-tracking-painted", {
            detail: {
              ...frame,
              painted_client_unix_ms: performance.timeOrigin + performance.now(),
            },
          }),
        );
      }),
    );
  };
  return (
    <div class="tracking-camera" data-sequence={frame.sequence}>
      {failure && <p role="alert">{t("Failed to load paired model evidence.")}</p>}
      {!ready && !failure && (
        <span class="tracking-rendering">{t("Loading paired model evidence…")}</span>
      )}
      <svg
        viewBox={`0 0 ${frame.width} ${frame.height}`}
        style={{ visibility: ready ? "visible" : "hidden" }}
        role="img"
        aria-label={t("Actual tracking mask on its processed frame")}
      >
        <defs>
          <mask
            id={`target-mask-${frame.generation}-${frame.sequence}`}
            maskUnits="userSpaceOnUse"
            x="0"
            y="0"
            width={frame.width}
            height={frame.height}
            style={{ maskType: "luminance" }}
          >
            <image
              href={maskUrl(frame.mask_sha)}
              width={frame.width}
              height={frame.height}
              onLoad={() => finish("mask")}
              onError={() => setFailure(true)}
            />
          </mask>
        </defs>
        <image
          href={evidence(frame.image_sha)}
          width={frame.width}
          height={frame.height}
          onLoad={() => finish("source")}
          onError={() => setFailure(true)}
        />
        <rect
          width={frame.width}
          height={frame.height}
          mask={`url(#target-mask-${frame.generation}-${frame.sequence})`}
          class="tracking-tint"
        />
      </svg>
      <div class="tracking-caption">
        {t(
          frame.stale
            ? "Historical / delayed observation"
            : "Processed observation · identity unverified",
        )}{" "}
        · {Math.round(frame.display_age_s * 1000)} ms {t("age at server response")}
      </div>
    </div>
  );
}

export function TrackingConsole({ robot }: { robot: Robot }) {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [tool, setTool] = useState<"point" | "exclude" | "box">("point");
  const [points, setPoints] = useState<number[][]>([]);
  const [labels, setLabels] = useState<number[]>([]);
  const [box, setBox] = useState<number[] | null>(null);
  const [candidate, setCandidate] = useState(0);
  const epoch = useRef(0);
  const mutation = useRef(0);
  const current = useRef<Session | null>(null);
  current.current = session;
  const pointerStart = useRef<number[] | null>(null);
  useEffect(() => {
    let closed = false,
      loading = false;
    const load = async () => {
      if (loading || mutation.current) return;
      loading = true;
      const version = epoch.current;
      try {
        const result = await api<Overview>("/tracking");
        if (closed) return;
        setOverview(result);
        const id = current.current?.id || result.sessions[0]?.id;
        if (id) {
          const s = await api<Session>(
            `/tracking/sessions/${id}?after=${current.current?.latest?.sequence ?? -1}`,
          );
          if (!closed && epoch.current === version) {
            if (s.preview && current.current?.preview?.selected !== s.preview.selected)
              setCandidate(s.preview.selected);
            current.current = s;
            setSession(s);
          }
        }
      } catch (e) {
        if (!closed) setError((e as Error).message);
      } finally {
        loading = false;
      }
    };
    void load();
    const timer = setInterval(() => {
      if (!document.hidden && robot.online) void load();
    }, 250);
    return () => {
      closed = true;
      clearInterval(timer);
    };
  }, [robot.online]);
  const run = async (work: () => Promise<Session>) => {
    const version = ++epoch.current;
    mutation.current = version;
    setBusy(true);
    setError("");
    try {
      const value = await work();
      if (epoch.current !== version) return;
      current.current = value;
      setSession(value);
      if (value.preview) setCandidate(value.preview.selected);
    } catch (e) {
      if (epoch.current === version) setError((e as Error).message);
    } finally {
      if (mutation.current === version) {
        mutation.current = 0;
        setBusy(false);
      }
    }
  };
  const pin = () =>
    void run(async () => {
      const value = await post<Session>("/tracking/anchors", {
        frame_id: robot.displayed.current,
        request_key: crypto.randomUUID(),
      });
      setPoints([]);
      setLabels([]);
      setBox(null);
      return value;
    });
  const coordinate = (event: PointerEvent, svg: SVGSVGElement): number[] | null => {
    const matrix = svg.getScreenCTM();
    if (!matrix || !session) return null;
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
    return point.x >= 0 &&
      point.x < session.anchor.width &&
      point.y >= 0 &&
      point.y < session.anchor.height
      ? [point.x, point.y]
      : null;
  };
  if (!overview?.enabled) return null;
  const selecting = !!session && ["selecting", "preview_ready"].includes(session.status);
  return (
    <section class="panel tracking-console" aria-label={t("Interactive target tracking")}>
      <div class="section-title">
        <div>
          <span class="eyebrow">SAM 2.1 / CUTIE · {overview.device.toUpperCase()}</span>
          <h2>{t("Select a target. Keep its evidence.")}</h2>
        </div>
        {session && active(session) && (
          <button
            class="button secondary"
            onClick={() => void run(() => post(`/tracking/sessions/${session.id}/stop`))}
          >
            <Square size={16} />
            {t("Stop tracking")}
          </button>
        )}
      </div>
      <p class="muted">
        {t(
          "Select an object on a frozen camera image. Original SAM creates the mask; original Cutie processes future frames. Tracking does not confirm physical identity.",
        )}
      </p>
      <span class={`badge ${overview.worker?.alive ? "green" : "amber"}`}>
        {t(overview.worker?.alive ? "Tracking worker online" : "Tracking worker unavailable")}
      </span>
      {error && (
        <p role="alert" class="banner">
          {error}
        </p>
      )}
      <div class="tracking-actions">
        <button
          class="button primary"
          disabled={
            busy ||
            !overview.worker?.alive ||
            !robot.state?.camera.fresh ||
            robot.armed ||
            (!!session && active(session))
          }
          onClick={pin}
        >
          <ScanEye size={17} />
          {t("Select target")}
        </button>
        <small>{t("Stationary observation only. No robot motion is requested.")}</small>
      </div>
      {session && (
        <>
          <div class="tracking-status">
            <strong>
              {t("Session")}: {session.status}
            </strong>
            <small>
              {session.error_code || t("Model evidence · identity unverified")} ·{" "}
              {session.dropped_frames} {t("producer frames dropped")}
            </small>
          </div>
          {session.stream && (
            <p class="muted" data-tracking-phase={session.stream.phase}>
              {t("Scheduling")}: {session.stream.phase} · {session.stream.pending}{" "}
              {t("pending source frames")} · {session.stream.pending_replacements}{" "}
              {t("pending frames replaced")} · {session.stream.skipped_frames}{" "}
              {t("admitted frames skipped")}
            </p>
          )}
          {session.anchor &&
            ["selecting", "preview_pending", "preview_ready"].includes(session.status) && (
              <>
                <div class="tracking-camera">
                  <svg
                    viewBox={`0 0 ${session.anchor.width} ${session.anchor.height}`}
                    role="img"
                    aria-label={t("Frozen target selection image")}
                    onPointerDown={(e) => {
                      if (!selecting) return;
                      const p = coordinate(e, e.currentTarget);
                      if (!p) return;
                      pointerStart.current = p;
                      e.currentTarget.setPointerCapture(e.pointerId);
                      if (tool !== "box") {
                        setPoints([...points, p]);
                        setLabels([...labels, tool === "point" ? 1 : 0]);
                      }
                    }}
                    onPointerUp={(e) => {
                      if (!selecting || tool !== "box" || !pointerStart.current) return;
                      const p = coordinate(e, e.currentTarget),
                        start = pointerStart.current;
                      pointerStart.current = null;
                      if (p)
                        setBox([
                          Math.min(p[0], start[0]),
                          Math.min(p[1], start[1]),
                          Math.max(p[0], start[0]),
                          Math.max(p[1], start[1]),
                        ]);
                    }}
                    onPointerCancel={() => {
                      pointerStart.current = null;
                    }}
                  >
                    <image
                      href={evidence(session.anchor.image_sha)}
                      width={session.anchor.width}
                      height={session.anchor.height}
                    />
                    {box && (
                      <rect
                        x={box[0]}
                        y={box[1]}
                        width={box[2] - box[0]}
                        height={box[3] - box[1]}
                        class="tracking-prompt-box"
                      />
                    )}
                    {points.map((p, i) => (
                      <circle
                        key={i}
                        cx={p[0]}
                        cy={p[1]}
                        r="5"
                        class={labels[i] ? "tracking-positive" : "tracking-negative"}
                      />
                    ))}
                  </svg>
                  <div class="tracking-caption">
                    {t("Frozen source · points and box are operator input")}
                  </div>
                </div>
                <div class="tracking-tools">
                  {(
                    [
                      ["point", "Add point"],
                      ["exclude", "Exclude area"],
                      ["box", "Draw box"],
                    ] as const
                  ).map(([id, name]) => (
                    <button
                      class="button secondary"
                      aria-pressed={tool === id}
                      disabled={!selecting}
                      onClick={() => setTool(id)}
                    >
                      {t(name)}
                    </button>
                  ))}
                  <button
                    class="button secondary"
                    disabled={!selecting}
                    onClick={() => {
                      setPoints([]);
                      setLabels([]);
                      setBox(null);
                    }}
                  >
                    <X size={16} />
                    {t("Reset prompt")}
                  </button>
                </div>
                <details>
                  <summary>{t("Keyboard box input")}</summary>
                  <div class="tracking-box-input">
                    {["Left", "Top", "Right", "Bottom"].map((name, i) => (
                      <label>
                        {t(name)}
                        <input
                          aria-label={t(`Target box ${name.toLowerCase()}`)}
                          type="number"
                          min="0"
                          step="1"
                          value={box?.[i] ?? ""}
                          onInput={(e) => {
                            const next = box ? [...box] : [0, 0, 0, 0];
                            next[i] = Number(e.currentTarget.value);
                            setBox(next);
                          }}
                        />
                      </label>
                    ))}
                  </div>
                </details>
                <button
                  class="button primary"
                  disabled={busy || !selecting || (!box && !points.length)}
                  onClick={() =>
                    void run(() =>
                      post(`/tracking/sessions/${session.id}/prompts`, {
                        revision: session.revision,
                        points,
                        labels,
                        box,
                      }),
                    )
                  }
                >
                  {t("Preview model mask")}
                </button>
                {session.preview && (
                  <div class="tracking-previews">
                    {session.preview.candidates.map((c, i) => (
                      <button
                        class={`tracking-preview ${candidate === i ? "selected" : ""}`}
                        aria-label={`${t("Mask candidate")} ${i + 1}`}
                        aria-pressed={candidate === i}
                        onClick={() => setCandidate(i)}
                      >
                        <img src={maskUrl(c.mask_sha)} alt={`${t("Actual SAM mask")} ${i + 1}`} />
                        <span>
                          {t("Model mask quality")}: {c.model_mask_quality_score.toFixed(3)}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
                <button
                  class="button primary"
                  disabled={busy || session.status !== "preview_ready"}
                  onClick={() =>
                    void run(() =>
                      post(`/tracking/sessions/${session.id}/start`, {
                        revision: session.revision,
                        candidate,
                      }),
                    )
                  }
                >
                  {t("Track this object")}
                </button>
              </>
            )}
          {session.latest && (
            <ProcessedFrame
              key={`${session.id}-${session.latest.generation}-${session.latest.sequence}`}
              frame={session.latest}
            />
          )}
          <details class="tracking-method">
            <summary>{t("Method and execution details")}</summary>
            <p>
              {t(
                "Original SAM 2.1 tiny and original Cutie base-mega. Custom scheduling uses bounded bootstrap sampling, then one replaceable latest frame. Skipped frames and temporal gaps are recorded; identity and sampling quality remain unverified. Empty-mask and time-gap rules are custom heuristics. A stale result does not establish the current location.",
              )}
            </p>
            <small>
              {t(
                "Upstream mask quality scores are not identity probabilities. Missing models fail without substitute output.",
              )}
            </small>
          </details>
        </>
      )}
    </section>
  );
}
