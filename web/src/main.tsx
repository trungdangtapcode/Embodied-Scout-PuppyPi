import { render, type ComponentChildren } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";
import {
  Activity,
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  ArrowUpRight,
  Camera,
  Check,
  ChevronRight,
  CircleStop,
  ClipboardCheck,
  Download,
  Fingerprint,
  FolderOpen,
  History as HistoryIcon,
  Layers,
  LoaderCircle,
  LockKeyhole,
  LogOut,
  Plus,
  Radio,
  RefreshCw,
  ScanLine,
  ShieldCheck,
  SlidersHorizontal,
  Square,
  Upload,
  Wifi,
  WifiOff,
  X,
} from "lucide-preact";
import "@fontsource/manrope/latin-400.css";
import "@fontsource/manrope/latin-500.css";
import "@fontsource/manrope/latin-600.css";
import "@fontsource/manrope/latin-700.css";
import "@fontsource/manrope/vietnamese-400.css";
import "@fontsource/manrope/vietnamese-500.css";
import "@fontsource/manrope/vietnamese-600.css";
import "@fontsource/manrope/vietnamese-700.css";
import "./style.css";
import { t, getLocale, setLocale, type Locale } from "./i18n";
import { api, evidence, post, timeOf, when } from "./api";
import type { Checklist, History, ObjectRecord, Report } from "./types";
import { type Robot, useRobot } from "./useRobot";
import { RoomConsole } from "./RoomConsole";

type Tab = "monitor" | "control" | "inspect" | "library";
const getNavigation = () =>
  [
    { id: "monitor", label: "Monitor", icon: Activity, subtitle: t("Your current viewpoint") },
    {
      id: "control",
      label: t("Control"),
      icon: SlidersHorizontal,
      subtitle: t("Take control, one step at a time"),
    },
    {
      id: "inspect",
      label: "Inspect",
      icon: ScanLine,
      subtitle: t("Every finding, backed by evidence"),
    },
    {
      id: "library",
      label: t("Library"),
      icon: Layers,
      subtitle: t("Objects your robot remembers"),
    },
  ] as const;
function label(key: string) {
  const labels: Record<string, string> = {
    pass: t("Pass"),
    fail: t("Needs review"),
    unknown: t("Unknown"),
    present: t("Present"),
    absent: t("Absent"),
    correct_location: t("Correct location"),
    missing: t("Missing object"),
    wrong_location: t("Wrong location"),
    no_fresh_evidence: t("No fresh evidence"),
    insufficient_visibility: t("Limited visibility"),
    uncertain_evidence: t("Uncertain evidence"),
    archived_object: t("Archived object"),
    present_at_expected_station: t("Correct location"),
    misplaced: t("Wrong location"),
    insufficient_or_conflicting_view: t("Unclear or conflicting view"),
    console_ready: t("Console ready"),
    camera_connected: t("Camera connected"),
    camera_disconnected: t("Camera disconnected"),
    control_armed: t("Control armed"),
    control_stopped: t("Control disarmed"),
    demo_loaded: t("Demo loaded"),
    observation_saved: t("Evidence saved"),
    object_taught: t("Object taught"),
    inspection_completed: t("Assessment completed"),
  };
  return labels[key] || key.replaceAll("_", " ");
}

function Badge({ children, tone = "" }: { children: ComponentChildren; tone?: string }) {
  return <span class={`badge ${tone}`}>{children}</span>;
}
function Empty({ title, children }: { title: string; children: ComponentChildren }) {
  return (
    <div class="empty">
      <ScanLine size={32} />
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ComponentChildren;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
    return () => ref.current?.close();
  }, []);
  return (
    <dialog ref={ref} onClose={onClose} aria-label={title}>
      <div class="modal-head">
        <h2>{title}</h2>
        <button class="icon-button" onClick={() => ref.current?.close()} aria-label={t("Close")}>
          <X />
        </button>
      </div>
      {children}
    </dialog>
  );
}
function CameraView({ robot, compact = false }: { robot: Robot; compact?: boolean }) {
  const { state, online, image } = robot;
  const live = online && state?.camera.available;
  return (
    <div class={`camera ${compact ? "compact" : ""}`}>
      <div class="camera-head">
        <span>
          <span class={`dot ${live ? "live" : ""}`} /> ROBOT VIEW
        </span>
        <span>{state?.mode === "synthetic" ? "SYNTHETIC" : "RGB CAMERA"}</span>
      </div>
      <div class="camera-image">
        {image && live ? (
          <img
            src={image.url}
            alt={t("Robot camera view")}
            onLoad={() => robot.imageLoaded(image.id)}
            onError={robot.imageFailed}
          />
        ) : (
          <div class="camera-empty">
            <Camera size={40} />
            <p>{online ? t("Waiting for camera\u2026") : t("Camera disconnected")}</p>
          </div>
        )}
        <span class="reticle" aria-hidden="true" />
        <div class="camera-caption">
          <span>
            <ScanLine size={16} /> {live ? t("Front view") : t("No live image")}
          </span>
          <span>{state?.camera.fresh && live ? t("Fresh frame") : t("Freshness unverified")}</span>
        </div>
      </div>
      <div class="frame-strip">
        <span>
          <Fingerprint size={14} /> {state?.camera.frame_id?.slice(-12) || "—"}
        </span>
        <span>
          {live && state?.camera.age_s != null
            ? t("{age} ms · estimated frame age", { age: Math.round(state.camera.age_s * 1000) })
            : t("No timestamp available")}
        </span>
      </div>
    </div>
  );
}

function LanguagePicker({ value, onChange }: { value: Locale; onChange: (value: Locale) => void }) {
  return (
    <select
      class="language-picker"
      aria-label={t("Language")}
      value={value}
      onChange={(event) => onChange(event.currentTarget.value === "vi" ? "vi" : "en")}
    >
      <option value="en">English</option>
      <option value="vi">VI</option>
    </select>
  );
}

function App() {
  const [locale, updateLocale] = useState<Locale>(getLocale);
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);
  const [auth, setAuth] = useState<"loading" | "paired" | "unpaired">("loading");
  const [token, setToken] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<Tab>("monitor");
  const [monitorView, setMonitorView] = useState<"live" | "room">("live");
  const [objects, setObjects] = useState<ObjectRecord[]>([]);
  const [checklists, setChecklists] = useState<Checklist[]>([]);
  const [reports, setReports] = useState<Report[]>([]);
  const [modal, setModal] = useState<"teach" | "checklist" | null>(null);
  const [selected, setSelected] = useState<ObjectRecord | null>(null);
  const [history, setHistory] = useState<History | null>(null);
  const robot = useRobot(auth === "paired", setNotice, () => {
    setAuth("unpaired");
    setNotice(t("Your session expired. Enter the host pairing code again."));
  });
  const changeLanguage = (value: Locale) => {
    if (auth === "paired") robot.stop();
    setLocale(value);
    updateLocale(value);
    setNotice("");
  };
  const languagePicker = <LanguagePicker value={locale} onChange={changeLanguage} />;
  const refresh = async () => {
    const [o, c, r] = await Promise.all([
      api<ObjectRecord[]>("/objects"),
      api<Checklist[]>("/checklists"),
      api<Report[]>("/reports"),
    ]);
    setObjects(o);
    setChecklists(c);
    setReports(r);
  };
  const act = async (work: () => Promise<unknown>, success?: string) => {
    setBusy(true);
    setNotice("");
    try {
      await work();
      if (success) setNotice(success);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : t("Unable to complete the action."));
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    void api("/state")
      .then(() => setAuth("paired"))
      .catch(() => setAuth("unpaired"));
  }, []);
  useEffect(() => {
    if (auth === "paired") void refresh().catch((error) => setNotice(error.message));
  }, [auth]);
  const switchTab = (next: Tab) => {
    if (next !== tab && (robot.armed || tab === "control")) robot.stop();
    setTab(next);
  };
  const openHistory = async (obj: ObjectRecord) => {
    setHistory(null);
    setSelected(obj);
    try {
      setHistory(await api<History>(`/objects/${obj.id}/history`));
    } catch (error) {
      setNotice(String(error));
    }
  };
  const navigation = getNavigation();
  const selectedNav = navigation.find((n) => n.id === tab)!;

  if (auth !== "paired")
    return (
      <main class="pair-page">
        <div class="pair-art">
          <img src="/icon.svg" alt="" />
          <span class="eyebrow">PUPPYPI / FIELD CONSOLE</span>
          <h1>
            A little robot.
            <br />A closer look.
          </h1>
          <p>{t("Observe. Control. Verify.")}</p>
          <div class="pair-orbit" aria-hidden="true">
            <ScanLine size={120} />
          </div>
          <span class="pair-footer">One workspace for every discovery.</span>
        </div>
        <section class="pair-form">
          <div class="pair-language">{languagePicker}</div>
          <Badge tone="green">
            <LockKeyhole size={14} />
            {t("Private host connection")}
          </Badge>
          <h2>{t("Welcome, operator.")}</h2>
          <p>
            {t("Enter the pairing code shown in the PuppyPi host terminal to open the console.")}
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void act(async () => {
                await post("/session", { token });
                setAuth("paired");
                setToken("");
              });
            }}
          >
            <label>
              {t("Pairing code")}
              <input
                autoComplete="off"
                type="password"
                value={token}
                onInput={(e) => setToken(e.currentTarget.value)}
                required
                placeholder={t("Enter the host code")}
              />
            </label>
            <button class="button primary wide" disabled={busy || auth === "loading"}>
              {auth === "loading" ? t("Connecting\u2026") : t("Open Field Console")}
              <ArrowUpRight size={18} />
            </button>
          </form>
          <p class="hint">
            {t(
              "Your phone must be able to reach the host. A new code is generated when the host starts.",
            )}
          </p>
          {notice && (
            <p role="alert" class="notice-inline">
              {notice}
            </p>
          )}
        </section>
      </main>
    );

  return (
    <div class="shell">
      <aside class="sidebar">
        <a class="brand" href="/" aria-label="PuppyPi home">
          <img src="/icon.svg" alt="" />
          <span>
            PuppyPi<small>FIELD CONSOLE</small>
          </span>
        </a>
        <span class="nav-label">WORKSPACE</span>
        <nav aria-label={t("Main navigation")}>
          {navigation.map((n) => (
            <button
              key={n.id}
              class={tab === n.id ? "active" : ""}
              onClick={() => switchTab(n.id)}
              aria-current={tab === n.id ? "page" : undefined}
            >
              <n.icon size={20} />
              <span>{n.label}</span>
              {tab === n.id && <ChevronRight class="nav-chevron" size={16} />}
            </button>
          ))}
        </nav>
        <div class="sidebar-bottom">
          <div class="robot-mark">
            <img src="/icon.svg" alt="" />
            <div>
              <strong>PuppyPi Standard</strong>
              <small>
                {robot.state?.mode === "synthetic" ? "Synthetic workspace" : "Selected robot relay"}
              </small>
            </div>
          </div>
          <button
            class="text-button"
            onClick={() =>
              void act(async () => {
                robot.stop();
                await api("/session", { method: "DELETE" });
                setAuth("unpaired");
              })
            }
          >
            <LogOut size={16} />
            {t("Sign out this device")}
          </button>
        </div>
      </aside>
      <div class="workspace">
        <header class="topbar">
          <div class="breadcrumb">
            Workspace <ChevronRight size={14} />
            <strong>{selectedNav.label}</strong>
          </div>
          <div class="topbar-actions">
            {languagePicker}
            <span class={`connection ${robot.online ? "" : "offline"}`}>
              {robot.online ? <Wifi size={16} /> : <WifiOff size={16} />}
              <span>{robot.online ? "Host online" : t("Disconnected")}</span>
            </span>
            <button class="stop-button" onClick={robot.stop}>
              <CircleStop size={18} /> STOP
            </button>
          </div>
        </header>
        <main class="content" data-tab={tab}>
          <div class="page-heading">
            <div>
              <span class="eyebrow">
                {tab === "inspect"
                  ? "EVIDENCE / ASSESSMENT"
                  : tab === "library"
                    ? "VISUAL MEMORY"
                    : "PUPPYPI / OPERATIONS"}
              </span>
              <h1>
                {selectedNav.label}
                <span class="heading-dot">.</span>
              </h1>
              <p>{selectedNav.subtitle}</p>
            </div>
            <Badge tone={robot.state?.mode === "synthetic" ? "amber" : "green"}>
              <span class="dot" />
              {robot.state?.mode === "synthetic"
                ? "Synthetic demo"
                : robot.state
                  ? "Robot relay"
                  : t("Connecting")}
            </Badge>
          </div>
          {!robot.online && (
            <div class="banner">
              <WifiOff size={18} />
              {t("Host disconnected. Controls are locked; reconnecting.")}
            </div>
          )}
          {tab === "monitor" && (
            <div class="monitor-views" aria-label={t("Monitor views")}>
              <button
                class={monitorView === "live" ? "active" : ""}
                aria-pressed={monitorView === "live"}
                onClick={() => setMonitorView("live")}
              >
                <Camera size={16} />
                {t("Live view")}
              </button>
              <button
                class={monitorView === "room" ? "active" : ""}
                aria-pressed={monitorView === "room"}
                onClick={() => setMonitorView("room")}
              >
                <HistoryIcon size={16} />
                {t("Room memory")}
              </button>
            </div>
          )}
          {tab === "monitor" && monitorView === "room" && (
            <RoomConsole robot={robot} objects={objects} onRefresh={refresh} />
          )}
          {((tab === "monitor" && monitorView === "live") || tab === "control") && (
            <div class="operations-grid">
              <section>
                <CameraView robot={robot} />
                <div class="camera-note">
                  <ShieldCheck size={16} />
                  <span>
                    {robot.state?.mode === "synthetic"
                      ? t(
                          "Interactive rendered camera \u00b7 kinematic simulation; physical behavior unverified.",
                        )
                      : t(
                          "ACK confirms adapter receipt. Measured position and motion feedback are unavailable.",
                        )}
                  </span>
                </div>
              </section>
              <aside class="operation-side">
                {tab === "monitor" ? (
                  <>
                    <div class="panel session-panel">
                      <div class="section-title">
                        <h2>{t("Observation session")}</h2>
                        <Radio size={18} />
                      </div>
                      <div class="session-state">
                        <span
                          class={`status-ring ${robot.state?.camera.fresh && robot.online ? "ready" : ""}`}
                        />
                        <div>
                          <strong>
                            {robot.online && robot.state?.camera.fresh
                              ? t("Ready to observe")
                              : t("Waiting for signal")}
                          </strong>
                          <small>{t("Front camera \u00b7 RGB")}</small>
                        </div>
                      </div>
                      <dl class="facts">
                        <div>
                          <dt>{t("Control")}</dt>
                          <dd>
                            {robot.state?.control.armed ? t("Operator in control") : t("Locked")}
                          </dd>
                        </div>
                        <div>
                          <dt>Pin</dt>
                          <dd>{t("Unavailable")}</dd>
                        </div>
                        <div>
                          <dt>{t("Measured position")}</dt>
                          <dd>{t("Unavailable")}</dd>
                        </div>
                      </dl>
                      <button class="button primary wide" onClick={() => switchTab("control")}>
                        {t("Open controls")}
                        <ArrowUpRight size={18} />
                      </button>
                    </div>
                    <div class="notebook-link" onClick={() => switchTab("inspect")}>
                      <span class="eyebrow">FROM CAMERA TO EVIDENCE</span>
                      <h3>
                        {t("Every viewpoint,")}
                        <br />
                        {t("a new discovery.")}
                      </h3>
                      <button class="text-button">
                        {t("Open Inspect")}
                        <ArrowRight size={18} />
                      </button>
                    </div>
                  </>
                ) : (
                  <ControlPanel robot={robot} />
                )}
              </aside>
            </div>
          )}
          {tab === "monitor" && monitorView === "live" && (
            <div class="lower-grid">
              <section class="panel">
                <div class="section-title">
                  <h2>{t("Evidence notebook")}</h2>
                  <FolderOpen size={18} />
                </div>
                <div class="memory-count">
                  <strong>{objects.length.toString().padStart(2, "0")}</strong>
                  <div>
                    {t("taught objects")}
                    <small>
                      {t("{reports} recent reports · {checklists} checklists", {
                        reports: reports.length,
                        checklists: checklists.length,
                      })}
                    </small>
                  </div>
                </div>
                <div class="reference-strip">
                  {objects.slice(0, 5).map((obj) => (
                    <button key={obj.id} onClick={() => void openHistory(obj)} title={obj.name}>
                      <img src={evidence(obj.references[0].image_sha)} alt={obj.name} />
                    </button>
                  ))}
                </div>
                {!objects.length && (
                  <>
                    <p class="muted">
                      {t("Teach your first object from images or load the demo dataset.")}
                    </p>
                    <button class="button secondary" onClick={() => setModal("teach")}>
                      <Plus size={16} />
                      {t("Teach object")}
                    </button>
                    {robot.state?.mode === "synthetic" && (
                      <button
                        class="text-button"
                        disabled={busy}
                        onClick={() =>
                          void act(async () => {
                            await post("/demo");
                            await refresh();
                          }, t("Synthetic demo created: 3 objects and a sample report."))
                        }
                      >
                        <Layers size={16} />
                        {t("Load demo data")}
                      </button>
                    )}
                  </>
                )}
              </section>
              <section class="panel activity-panel">
                <div class="section-title">
                  <h2>{t("Session activity")}</h2>
                  <Activity size={18} />
                </div>
                <div class="event-list">
                  {robot.state?.events.slice(0, 4).map((event) => (
                    <div class="event" key={event.id}>
                      <span class="event-dot" />
                      <div>
                        <strong>{label(event.kind)}</strong>
                        <small>{event.message}</small>
                      </div>
                      <time>{timeOf(event.at)}</time>
                    </div>
                  ))}
                </div>
              </section>
            </div>
          )}
          {tab === "inspect" && (
            <Inspect
              objects={objects}
              checklists={checklists}
              reports={reports}
              robot={robot}
              busy={busy}
              act={act}
              refresh={refresh}
              create={() => setModal("checklist")}
            />
          )}
          {tab === "library" && (
            <>
              <div class="section-toolbar">
                <span>{t("{count} objects · shared with the CLI", { count: objects.length })}</span>
                <button class="button primary" onClick={() => setModal("teach")}>
                  <Plus size={18} />
                  {t("Teach object")}
                </button>
              </div>
              {objects.length ? (
                <div class="object-grid">
                  {objects.map((obj, i) => (
                    <button class="object-card" key={obj.id} onClick={() => void openHistory(obj)}>
                      <div class="object-picture">
                        <img src={evidence(obj.references[0].image_sha)} alt={obj.name} />
                        <span class="object-number">{String(i + 1).padStart(2, "0")}</span>
                      </div>
                      <div class="object-details">
                        <div>
                          <h3>{obj.name}</h3>
                          <p>{t("{count} reference images", { count: obj.references.length })}</p>
                        </div>
                        <ArrowUpRight size={20} />
                      </div>
                    </button>
                  ))}
                </div>
              ) : (
                <Empty title={t("Start with an object")}>
                  {t(
                    "Choose Teach object and upload tightly cropped images. Multiple viewpoints make the library more useful.",
                  )}
                </Empty>
              )}
            </>
          )}
          <footer class="content-footer">
            <span>PUPPYPI FIELD CONSOLE</span>
            <span>Evidence first. Every step.</span>
          </footer>
        </main>
      </div>
      {notice && (
        <div class="toast" role="status">
          <span>{notice}</span>
          <button aria-label={t("Dismiss notification")} onClick={() => setNotice("")}>
            <X size={18} />
          </button>
        </div>
      )}
      {modal === "teach" && (
        <Modal title={t("Teach an object")} onClose={() => setModal(null)}>
          <p class="muted">
            {t(
              "Use 1\u20138 tightly cropped views. PNG/JPEG, up to 4 MB each and 6 MB per request.",
            )}
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const form = new FormData(e.currentTarget);
              void act(async () => {
                await api("/objects", { method: "POST", body: form });
                await refresh();
                setModal(null);
              }, t("Object saved to the library."));
            }}
          >
            <label>
              {t("Object name")}
              <input
                name="name"
                required
                maxLength={120}
                placeholder={t("For example: Blue tool case")}
              />
            </label>
            <label class="upload-field">
              <Upload size={24} />
              <span>{t("Choose reference images")}</span>
              <input name="files" type="file" accept="image/png,image/jpeg" multiple required />
            </label>
            <button class="button primary wide" disabled={busy}>
              {busy ? <LoaderCircle class="spin" size={18} /> : <Check size={18} />}{" "}
              {t("Save to library")}
            </button>
          </form>
        </Modal>
      )}
      {modal === "checklist" && (
        <Modal title={t("Create checklist")} onClose={() => setModal(null)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const form = new FormData(e.currentTarget);
              void act(async () => {
                await post("/checklists", {
                  name: form.get("name"),
                  items: form
                    .getAll("objects")
                    .map((id) => ({ object_id: id, station: form.get("station") })),
                });
                await refresh();
                setModal(null);
              });
            }}
          >
            <label>
              {t("Checklist name")}
              <input name="name" required placeholder={t("Workbench readiness")} />
            </label>
            <label>
              {t("Expected station")}
              <input name="station" defaultValue="Station_A" required />
            </label>
            <fieldset>
              <legend>{t("Expected objects")}</legend>
              {objects.map((obj) => (
                <label class="check-row" key={obj.id}>
                  <input type="checkbox" name="objects" value={obj.id} />
                  <img src={evidence(obj.references[0].image_sha)} alt="" />
                  {obj.name}
                </label>
              ))}
            </fieldset>
            <button class="button primary wide" disabled={busy || !objects.length}>
              {t("Create checklist")}
              <Plus size={16} />
            </button>
          </form>
        </Modal>
      )}
      {selected && (
        <Modal
          title={selected.name}
          onClose={() => {
            setSelected(null);
            setHistory(null);
          }}
        >
          <div class="history-refs">
            {selected.references.map((ref) => (
              <img key={ref.image_sha} src={evidence(ref.image_sha)} alt={t("Reference image")} />
            ))}
          </div>
          <form
            class="rename-row"
            onSubmit={(e) => {
              e.preventDefault();
              const name = new FormData(e.currentTarget).get("name");
              void act(async () => {
                const obj = await api<ObjectRecord>(`/objects/${selected.id}`, {
                  method: "PATCH",
                  body: JSON.stringify({ name }),
                });
                setSelected(obj);
                await refresh();
              });
            }}
          >
            <label>
              {t("Object name")}
              <input name="name" value={selected.name} required />
            </label>
            <button class="button secondary" disabled={busy}>
              {t("Rename")}
            </button>
          </form>
          <h3>
            <HistoryIcon size={18} />
            {t("Observation history")}
          </h3>
          <p class="hint">{t("A past sighting does not establish the current location.")}</p>
          {!history ? (
            <p>{t("Loading evidence\u2026")}</p>
          ) : history.observations.length ? (
            history.observations.map((obs) => (
              <div class="observation-row" key={obs.id}>
                <a href={evidence(obs.image_sha)} target="_blank" rel="noreferrer">
                  <img
                    src={evidence(obs.image_sha)}
                    alt={t("Evidence: {name}", { name: label(obs.assertion) })}
                  />
                </a>
                <div>
                  <strong>
                    {label(obs.assertion)} · {obs.station}
                  </strong>
                  <small>
                    {when(obs.captured_at)} · {obs.mode} · {obs.source}
                  </small>
                  <small>
                    {String(
                      obs.provenance.capture_time_basis ||
                        obs.provenance.source ||
                        "No capture metadata",
                    )}
                  </small>
                </div>
              </div>
            ))
          ) : (
            <Empty title={t("No observations yet")}>
              {t("Record camera evidence in Inspect to build a history.")}
            </Empty>
          )}
          <button
            class="button danger-outline wide"
            disabled={busy}
            onClick={() => {
              if (
                confirm(
                  t("Archive {name}? Existing evidence will be preserved.", {
                    name: selected.name,
                  }),
                )
              )
                void act(async () => {
                  await api(`/objects/${selected.id}`, { method: "DELETE" });
                  setSelected(null);
                  await refresh();
                });
            }}
          >
            {t("Archive object")}
          </button>
        </Modal>
      )}
    </div>
  );
}

function ControlPanel({ robot }: { robot: Robot }) {
  const directions = [
    { key: "up", f: 0.6, t: 0, icon: ArrowUp, title: t("Forward") },
    { key: "left", f: 0, t: 0.6, icon: ArrowLeft, title: t("Turn left") },
    { key: "down", f: -0.6, t: 0, icon: ArrowDown, title: t("Reverse") },
    { key: "right", f: 0, t: -0.6, icon: ArrowRight, title: t("Turn right") },
  ];
  return (
    <div class="panel control-panel">
      <div class="section-title">
        <h2>{t("Manual control")}</h2>
        <SlidersHorizontal size={18} />
      </div>
      <Badge tone={robot.armed ? "green" : ""}>
        {robot.armed ? t("Control armed") : t("Controls locked")}
      </Badge>
      <p class="muted">
        {t("Hold to move, release to request zero. Leaving this view locks the session.")}
      </p>
      <div class={`dpad ${robot.moving ? "moving" : ""}`}>
        <div class="dpad-center">
          <span class="dot" />
        </div>
        {directions.map((d) => (
          <button
            class={`direction ${d.key}`}
            key={d.key}
            aria-label={d.title}
            disabled={!robot.armed || !robot.online}
            onPointerDown={(e) => {
              e.preventDefault();
              e.currentTarget.setPointerCapture(e.pointerId);
              robot.hold(d.f, d.t);
            }}
            onPointerUp={() => robot.hold(0, 0)}
            onPointerCancel={() => robot.hold(0, 0)}
            onLostPointerCapture={() => robot.hold(0, 0)}
            onKeyDown={(e) => {
              if ((e.key === " " || e.key === "Enter") && !e.repeat) {
                e.preventDefault();
                robot.hold(d.f, d.t);
              }
            }}
            onKeyUp={(e) => {
              if (e.key === " " || e.key === "Enter") {
                e.preventDefault();
                robot.hold(0, 0);
              }
            }}
            onBlur={() => robot.hold(0, 0)}
          >
            <d.icon size={24} />
          </button>
        ))}
      </div>
      <div class="command-readout">
        <span>{t("COMMAND")}</span>
        <strong>
          {robot.state?.control.command.vx_cm_s.toFixed(1) || "0.0"} <small>cm/s</small>
        </strong>
        <span>{robot.moving ? t("Direction held") : t("No movement requested")}</span>
      </div>
      <button
        class="button primary wide"
        onClick={robot.armed ? robot.stop : robot.arm}
        disabled={
          !robot.online ||
          (!robot.armed && (!robot.state?.control.ready || robot.state.control.armed))
        }
      >
        {robot.armed ? <Square size={16} /> : <LockKeyhole size={16} />}
        {robot.armed ? t("Disarm and stop") : t("Arm controls")}
      </button>
      <p class="hint">
        {t(
          "Lease {seconds}s · stale frames or a lost session revoke control. Keep the physical stop available.",
          { seconds: robot.state?.control.lease_s || 0.45 },
        )}
      </p>
      {robot.state && !robot.state.control.enabled && (
        <p class="notice-inline">{t("The host is in monitor-only mode.")}</p>
      )}
    </div>
  );
}

function Inspect({
  objects,
  checklists,
  reports,
  robot,
  busy,
  act,
  refresh,
  create,
}: {
  objects: ObjectRecord[];
  checklists: Checklist[];
  reports: Report[];
  robot: Robot;
  busy: boolean;
  act: (work: () => Promise<unknown>, success?: string) => Promise<void>;
  refresh: () => Promise<void>;
  create: () => void;
}) {
  const [selectedId, setSelectedId] = useState("");
  const [reportId, setReportId] = useState("");
  const report = reports.find((r) => r.id === reportId) || reports[0];
  return (
    <div class="inspect-grid">
      <section>
        <div class="panel">
          <div class="section-title">
            <h2>{t("Checklist assessment")}</h2>
            <button class="text-button" onClick={create} disabled={!objects.length}>
              <Plus size={16} />
              {t("Create new")}
            </button>
          </div>
          <p class="muted">
            {t(
              "Assess recorded evidence. This action does not move the robot or recognize objects automatically.",
            )}
          </p>
          <div class="run-row">
            <label class="grow">
              Checklist
              <select
                value={selectedId || checklists[0]?.id || ""}
                onChange={(e) => setSelectedId(e.currentTarget.value)}
              >
                <option value="" disabled>
                  {t("Choose a checklist")}
                </option>
                {checklists.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <button
              class="button primary"
              disabled={busy || !checklists.length}
              onClick={() =>
                void act(async () => {
                  const r = await post<Report>(
                    `/checklists/${selectedId || checklists[0].id}/inspect`,
                  );
                  setReportId(r.id);
                  await refresh();
                })
              }
            >
              <ClipboardCheck size={18} />
              {t("Assess")}
            </button>
          </div>
        </div>
        {report ? (
          <section class="panel report-panel">
            <div class="section-title">
              <div>
                <span class="eyebrow">INSPECTION REPORT</span>
                <h2>{report.checklist.name}</h2>
              </div>
              <a
                class="icon-button"
                aria-label={t("Download report ZIP")}
                href={`/api/reports/${report.id}/download`}
              >
                <Download size={20} />
              </a>
            </div>
            <div class="report-meta">
              <span>{when(report.created_at)}</span>
              <Badge tone="amber">{report.mode}</Badge>
            </div>
            <div class="result-counts">
              {(["pass", "fail", "unknown"] as const).map((s) => (
                <div class={s} key={s}>
                  <strong>{report.summary[s]}</strong>
                  <span>{label(s)}</span>
                </div>
              ))}
            </div>
            <div class="findings">
              {report.findings.map((f, i) => (
                <div class="finding" key={i}>
                  <img
                    src={evidence(f.evidence[0]?.image_sha || f.reference_image_sha)}
                    alt={t("Evidence: {name}", { name: f.object_name })}
                  />
                  <div>
                    <strong>{f.object_name}</strong>
                    <small>
                      {f.expected_station} · {label(f.reason)}
                    </small>
                  </div>
                  <Badge
                    tone={f.status === "pass" ? "green" : f.status === "fail" ? "red" : "amber"}
                  >
                    {label(f.status)}
                  </Badge>
                </div>
              ))}
            </div>
            <p class="hint">
              {t("Findings reflect evidence at assessment time. Unknown does not mean absent.")}
            </p>
            {reports.length > 1 && (
              <label>
                {t("Saved reports")}
                <select value={report.id} onChange={(e) => setReportId(e.currentTarget.value)}>
                  {reports.map((r) => (
                    <option key={r.id} value={r.id}>
                      {when(r.created_at)} · {r.checklist.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </section>
        ) : (
          <Empty title={t("No reports yet")}>
            {t("Create a checklist, record evidence, then run an assessment.")}
          </Empty>
        )}
      </section>
      <aside class="panel capture-panel">
        <div class="section-title">
          <h2>{t("Capture evidence")}</h2>
          <Camera size={18} />
        </div>
        <CameraView robot={robot} compact />
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            const frame_id = robot.displayed.current;
            void act(async () => {
              await post("/observations", {
                object_id: f.get("object"),
                station: f.get("station"),
                assertion: f.get("assertion"),
                visibility: Number(f.get("visibility")),
                frame_id,
              });
              await refresh();
            }, t("Image and operator assertion saved."));
          }}
        >
          <label>
            {t("Object")}
            <select name="object" required>
              <option value="">{t("Choose an object")}</option>
              {objects.map((o) => (
                <option value={o.id} key={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t("Observed station")}
            <input name="station" required defaultValue="Station_A" />
          </label>
          <div class="form-split">
            <label>
              {t("Assertion")}
              <select name="assertion">
                <option value="present">{t("Present")}</option>
                <option value="absent">{t("Absent")}</option>
                <option value="unknown">{t("Unknown")}</option>
              </select>
            </label>
            <label>
              {t("Visibility")}
              <select name="visibility">
                <option value="1">{t("Clear view")}</option>
                <option value="0.3">{t("Obstructed")}</option>
              </select>
            </label>
          </div>
          <button
            class="button primary wide"
            disabled={busy || !robot.online || !robot.state?.camera.fresh || !objects.length}
          >
            <Camera size={18} />
            {t("Capture & record")}
          </button>
          <p class="hint">
            {t(
              "Your assertion is linked to the displayed frame and capture time. Stale frames are rejected.",
            )}
          </p>
        </form>
      </aside>
    </div>
  );
}

render(<App />, document.getElementById("app")!);
if ("serviceWorker" in navigator && import.meta.env.PROD) {
  window.addEventListener("load", () => {
    void navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}
