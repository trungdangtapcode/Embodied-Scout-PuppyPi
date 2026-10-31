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
import { api, evidence, post, timeOf, when } from "./api";
import type { Checklist, History, ObjectRecord, Report } from "./types";
import { type Robot, useRobot } from "./useRobot";

type Tab = "monitor" | "control" | "inspect" | "library";
const navigation = [
  { id: "monitor", label: "Monitor", icon: Activity, subtitle: "Góc nhìn hiện tại" },
  { id: "control", label: "Điều khiển", icon: SlidersHorizontal, subtitle: "Chủ động từng bước" },
  { id: "inspect", label: "Inspect", icon: ScanLine, subtitle: "Mỗi kết luận, một bằng chứng" },
  { id: "library", label: "Thư viện", icon: Layers, subtitle: "Những vật thể đã học" },
] as const;
const labels: Record<string, string> = {
  pass: "Đạt",
  fail: "Cần kiểm tra",
  unknown: "Chưa rõ",
  present: "Có mặt",
  absent: "Vắng mặt",
  correct_location: "Đúng vị trí",
  missing: "Thiếu vật thể",
  wrong_location: "Sai vị trí",
  no_fresh_evidence: "Chưa có bằng chứng mới",
  insufficient_visibility: "Tầm nhìn hạn chế",
  uncertain_evidence: "Bằng chứng chưa rõ",
  archived_object: "Vật thể đã lưu trữ",
  present_at_expected_station: "Đúng vị trí",
  misplaced: "Sai vị trí",
  insufficient_or_conflicting_view: "Ảnh chưa rõ hoặc mâu thuẫn",
  console_ready: "Console sẵn sàng",
  camera_connected: "Camera đã kết nối",
  camera_disconnected: "Camera mất kết nối",
  control_armed: "Đã mở quyền điều khiển",
  control_stopped: "Đã khóa điều khiển",
  demo_loaded: "Đã nạp dữ liệu demo",
  observation_saved: "Đã ghi nhận bằng chứng",
  object_taught: "Đã học vật thể",
  inspection_completed: "Đã hoàn tất đánh giá",
};
const label = (key: string) => labels[key] || key.replaceAll("_", " ");

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
        <button class="icon-button" onClick={() => ref.current?.close()} aria-label="Đóng">
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
            alt="Góc nhìn camera robot"
            onLoad={() => robot.imageLoaded(image.id)}
            onError={robot.imageFailed}
          />
        ) : (
          <div class="camera-empty">
            <Camera size={40} />
            <p>{online ? "Đang chờ camera…" : "Camera chưa kết nối"}</p>
          </div>
        )}
        <span class="reticle" aria-hidden="true" />
        <div class="camera-caption">
          <span>
            <ScanLine size={16} /> {live ? "Góc nhìn phía trước" : "Không có ảnh trực tiếp"}
          </span>
          <span>{state?.camera.fresh && live ? "Ảnh mới" : "Chưa xác minh độ mới"}</span>
        </div>
      </div>
      <div class="frame-strip">
        <span>
          <Fingerprint size={14} /> {state?.camera.frame_id?.slice(-12) || "—"}
        </span>
        <span>
          {live && state?.camera.age_s != null
            ? `${Math.round(state.camera.age_s * 1000)} ms · tuổi ảnh ước tính`
            : "Chưa có timestamp"}
        </span>
      </div>
    </div>
  );
}

function App() {
  const [auth, setAuth] = useState<"loading" | "paired" | "unpaired">("loading");
  const [token, setToken] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<Tab>("monitor");
  const [objects, setObjects] = useState<ObjectRecord[]>([]);
  const [checklists, setChecklists] = useState<Checklist[]>([]);
  const [reports, setReports] = useState<Report[]>([]);
  const [modal, setModal] = useState<"teach" | "checklist" | null>(null);
  const [selected, setSelected] = useState<ObjectRecord | null>(null);
  const [history, setHistory] = useState<History | null>(null);
  const robot = useRobot(auth === "paired", setNotice, () => {
    setAuth("unpaired");
    setNotice("Phiên đã hết hạn. Nhập lại mã ghép nối của host.");
  });
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
      setNotice(error instanceof Error ? error.message : "Không thể hoàn tất thao tác.");
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
          <p>Quan sát. Điều khiển. Kiểm chứng.</p>
          <div class="pair-orbit" aria-hidden="true">
            <ScanLine size={120} />
          </div>
          <span class="pair-footer">One workspace for every discovery.</span>
        </div>
        <section class="pair-form">
          <Badge tone="green">
            <LockKeyhole size={14} /> Kết nối riêng với host
          </Badge>
          <h2>Chào người điều khiển.</h2>
          <p>Nhập mã ghép nối hiển thị trong terminal của PuppyPi host để mở bàn điều khiển.</p>
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
              Mã ghép nối
              <input
                autoComplete="off"
                type="password"
                value={token}
                onInput={(e) => setToken(e.currentTarget.value)}
                required
                placeholder="Nhập mã từ host"
              />
            </label>
            <button class="button primary wide" disabled={busy || auth === "loading"}>
              {auth === "loading" ? "Đang kết nối…" : "Mở Field Console"}
              <ArrowUpRight size={18} />
            </button>
          </form>
          <p class="hint">
            Điện thoại và host cần truy cập được cùng địa chỉ mạng. Mã mới được tạo khi host khởi
            động.
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
        <nav aria-label="Điều hướng chính">
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
            <LogOut size={16} /> Ngắt phiên thiết bị
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
            <span class={`connection ${robot.online ? "" : "offline"}`}>
              {robot.online ? <Wifi size={16} /> : <WifiOff size={16} />}
              <span>{robot.online ? "Host online" : "Mất kết nối"}</span>
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
                  : "Đang kết nối"}
            </Badge>
          </div>
          {!robot.online && (
            <div class="banner">
              <WifiOff size={18} /> Mất kết nối host. Điều khiển đã khóa; đang thử kết nối lại.
            </div>
          )}
          {(tab === "monitor" || tab === "control") && (
            <div class="operations-grid">
              <section>
                <CameraView robot={robot} />
                <div class="camera-note">
                  <ShieldCheck size={16} />
                  <span>
                    {robot.state?.mode === "synthetic"
                      ? "Camera render tương tác · mô phỏng động học, chưa phải kết quả robot thật."
                      : "ACK xác nhận adapter nhận lệnh. Chưa có phản hồi vị trí hoặc xác nhận chuyển động."}
                  </span>
                </div>
              </section>
              <aside class="operation-side">
                {tab === "monitor" ? (
                  <>
                    <div class="panel session-panel">
                      <div class="section-title">
                        <h2>Phiên quan sát</h2>
                        <Radio size={18} />
                      </div>
                      <div class="session-state">
                        <span
                          class={`status-ring ${robot.state?.camera.fresh && robot.online ? "ready" : ""}`}
                        />
                        <div>
                          <strong>
                            {robot.online && robot.state?.camera.fresh
                              ? "Sẵn sàng quan sát"
                              : "Đang chờ tín hiệu"}
                          </strong>
                          <small>Camera phía trước · RGB</small>
                        </div>
                      </div>
                      <dl class="facts">
                        <div>
                          <dt>Điều khiển</dt>
                          <dd>
                            {robot.state?.control.armed ? "Đang có người giữ quyền" : "Đã khóa"}
                          </dd>
                        </div>
                        <div>
                          <dt>Pin</dt>
                          <dd>Chưa có dữ liệu</dd>
                        </div>
                        <div>
                          <dt>Vị trí đo được</dt>
                          <dd>Chưa có dữ liệu</dd>
                        </div>
                      </dl>
                      <button class="button primary wide" onClick={() => switchTab("control")}>
                        Mở điều khiển
                        <ArrowUpRight size={18} />
                      </button>
                    </div>
                    <div class="notebook-link" onClick={() => switchTab("inspect")}>
                      <span class="eyebrow">FROM CAMERA TO EVIDENCE</span>
                      <h3>
                        Mỗi góc nhìn,
                        <br />
                        một phát hiện mới.
                      </h3>
                      <button class="text-button">
                        Mở Inspect <ArrowRight size={18} />
                      </button>
                    </div>
                  </>
                ) : (
                  <ControlPanel robot={robot} />
                )}
              </aside>
            </div>
          )}
          {tab === "monitor" && (
            <div class="lower-grid">
              <section class="panel">
                <div class="section-title">
                  <h2>Sổ bằng chứng</h2>
                  <FolderOpen size={18} />
                </div>
                <div class="memory-count">
                  <strong>{objects.length.toString().padStart(2, "0")}</strong>
                  <div>
                    vật thể đã học
                    <small>
                      {reports.length} báo cáo gần đây · {checklists.length} checklist
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
                    <p class="muted">Dạy vật thể đầu tiên từ ảnh hoặc mở bộ dữ liệu demo.</p>
                    <button class="button secondary" onClick={() => setModal("teach")}>
                      <Plus size={16} /> Dạy vật thể
                    </button>
                    {robot.state?.mode === "synthetic" && (
                      <button
                        class="text-button"
                        disabled={busy}
                        onClick={() =>
                          void act(async () => {
                            await post("/demo");
                            await refresh();
                          }, "Đã tạo dữ liệu synthetic: 3 vật thể và một báo cáo mẫu.")
                        }
                      >
                        <Layers size={16} /> Nạp dữ liệu demo
                      </button>
                    )}
                  </>
                )}
              </section>
              <section class="panel activity-panel">
                <div class="section-title">
                  <h2>Nhật ký phiên</h2>
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
                <span>{objects.length} vật thể · thư viện dùng chung với CLI</span>
                <button class="button primary" onClick={() => setModal("teach")}>
                  <Plus size={18} /> Dạy vật thể
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
                          <p>{obj.references.length} ảnh tham chiếu</p>
                        </div>
                        <ArrowUpRight size={20} />
                      </div>
                    </button>
                  ))}
                </div>
              ) : (
                <Empty title="Bắt đầu bằng một vật thể">
                  Chọn Dạy vật thể và tải lên ảnh đã crop sát vật thể. Nhiều góc nhìn giúp thư viện
                  hữu ích hơn.
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
          <button aria-label="Đóng thông báo" onClick={() => setNotice("")}>
            <X size={18} />
          </button>
        </div>
      )}
      {modal === "teach" && (
        <Modal title="Dạy một vật thể" onClose={() => setModal(null)}>
          <p class="muted">
            Dùng 1–8 ảnh crop sát vật thể, ở nhiều góc nhìn. PNG/JPEG, tối đa 4 MB mỗi ảnh và 6 MB
            tổng yêu cầu.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const form = new FormData(e.currentTarget);
              void act(async () => {
                await api("/objects", { method: "POST", body: form });
                await refresh();
                setModal(null);
              }, "Đã lưu vật thể vào thư viện.");
            }}
          >
            <label>
              Tên vật thể
              <input name="name" required maxLength={120} placeholder="Ví dụ: Hộp dụng cụ xanh" />
            </label>
            <label class="upload-field">
              <Upload size={24} />
              <span>Chọn ảnh tham chiếu</span>
              <input name="files" type="file" accept="image/png,image/jpeg" multiple required />
            </label>
            <button class="button primary wide" disabled={busy}>
              {busy ? <LoaderCircle class="spin" size={18} /> : <Check size={18} />} Lưu vào thư
              viện
            </button>
          </form>
        </Modal>
      )}
      {modal === "checklist" && (
        <Modal title="Tạo checklist" onClose={() => setModal(null)}>
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
              Tên checklist
              <input name="name" required placeholder="Kiểm tra bàn làm việc" />
            </label>
            <label>
              Vị trí mong đợi
              <input name="station" defaultValue="Station_A" required />
            </label>
            <fieldset>
              <legend>Vật thể cần có</legend>
              {objects.map((obj) => (
                <label class="check-row" key={obj.id}>
                  <input type="checkbox" name="objects" value={obj.id} />
                  <img src={evidence(obj.references[0].image_sha)} alt="" />
                  {obj.name}
                </label>
              ))}
            </fieldset>
            <button class="button primary wide" disabled={busy || !objects.length}>
              Tạo checklist <Plus size={16} />
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
              <img key={ref.image_sha} src={evidence(ref.image_sha)} alt="Ảnh tham chiếu" />
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
              Tên vật thể
              <input name="name" value={selected.name} required />
            </label>
            <button class="button secondary" disabled={busy}>
              Đổi tên
            </button>
          </form>
          <h3>
            <HistoryIcon size={18} /> Lịch sử quan sát
          </h3>
          <p class="hint">Lần thấy trước đây không khẳng định vị trí hiện tại.</p>
          {!history ? (
            <p>Đang tải bằng chứng…</p>
          ) : history.observations.length ? (
            history.observations.map((obs) => (
              <div class="observation-row" key={obs.id}>
                <a href={evidence(obs.image_sha)} target="_blank" rel="noreferrer">
                  <img src={evidence(obs.image_sha)} alt={`Bằng chứng ${label(obs.assertion)}`} />
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
            <Empty title="Chưa có quan sát">
              Ghi nhận ảnh camera trong Inspect để tạo lịch sử.
            </Empty>
          )}
          <button
            class="button danger-outline wide"
            disabled={busy}
            onClick={() => {
              if (confirm(`Lưu trữ “${selected.name}”? Bằng chứng cũ vẫn được giữ.`))
                void act(async () => {
                  await api(`/objects/${selected.id}`, { method: "DELETE" });
                  setSelected(null);
                  await refresh();
                });
            }}
          >
            Lưu trữ vật thể
          </button>
        </Modal>
      )}
    </div>
  );
}

function ControlPanel({ robot }: { robot: Robot }) {
  const directions = [
    { key: "up", f: 0.6, t: 0, icon: ArrowUp, title: "Tiến" },
    { key: "left", f: 0, t: 0.6, icon: ArrowLeft, title: "Quay trái" },
    { key: "down", f: -0.6, t: 0, icon: ArrowDown, title: "Lùi" },
    { key: "right", f: 0, t: -0.6, icon: ArrowRight, title: "Quay phải" },
  ];
  return (
    <div class="panel control-panel">
      <div class="section-title">
        <h2>Điều khiển thủ công</h2>
        <SlidersHorizontal size={18} />
      </div>
      <Badge tone={robot.armed ? "green" : ""}>
        {robot.armed ? "Đã mở quyền điều khiển" : "Điều khiển đang khóa"}
      </Badge>
      <p class="muted">Giữ nút để di chuyển, nhả để gửi lệnh dừng. Rời màn hình sẽ khóa phiên.</p>
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
        <span>LỆNH GỬI</span>
        <strong>
          {robot.state?.control.command.vx_cm_s.toFixed(1) || "0.0"} <small>cm/s</small>
        </strong>
        <span>{robot.moving ? "Đang giữ nút" : "Không yêu cầu di chuyển"}</span>
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
        {robot.armed ? "Khóa và dừng" : "Mở quyền điều khiển"}
      </button>
      <p class="hint">
        Lease {robot.state?.control.lease_s || 0.45}s · ảnh cũ hoặc mất phiên sẽ ngắt lệnh. Chưa
        thay thế nút dừng vật lý.
      </p>
      {robot.state && !robot.state.control.enabled && (
        <p class="notice-inline">Host đang ở chế độ chỉ quan sát.</p>
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
            <h2>Kiểm tra theo checklist</h2>
            <button class="text-button" onClick={create} disabled={!objects.length}>
              <Plus size={16} /> Tạo mới
            </button>
          </div>
          <p class="muted">
            Đánh giá bằng chứng đã ghi nhận. Không tự di chuyển hay tự nhận diện vật thể.
          </p>
          <div class="run-row">
            <label class="grow">
              Checklist
              <select
                value={selectedId || checklists[0]?.id || ""}
                onChange={(e) => setSelectedId(e.currentTarget.value)}
              >
                <option value="" disabled>
                  Chọn checklist
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
              <ClipboardCheck size={18} /> Đánh giá
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
                aria-label="Tải báo cáo ZIP"
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
                    alt={`Bằng chứng: ${f.object_name}`}
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
              Kết luận theo evidence tại thời điểm đánh giá. “Chưa rõ” không đồng nghĩa vật thể vắng
              mặt.
            </p>
            {reports.length > 1 && (
              <label>
                Báo cáo đã lưu
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
          <Empty title="Chưa có báo cáo">
            Tạo checklist, ghi nhận bằng chứng, rồi chạy đánh giá.
          </Empty>
        )}
      </section>
      <aside class="panel capture-panel">
        <div class="section-title">
          <h2>Ghi nhận tại hiện trường</h2>
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
            }, "Đã lưu ảnh và nhận định của người vận hành.");
          }}
        >
          <label>
            Vật thể
            <select name="object" required>
              <option value="">Chọn vật thể</option>
              {objects.map((o) => (
                <option value={o.id} key={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Vị trí quan sát
            <input name="station" required defaultValue="Station_A" />
          </label>
          <div class="form-split">
            <label>
              Nhận định
              <select name="assertion">
                <option value="present">Có mặt</option>
                <option value="absent">Vắng mặt</option>
                <option value="unknown">Chưa rõ</option>
              </select>
            </label>
            <label>
              Tầm nhìn
              <select name="visibility">
                <option value="1">Rõ toàn cảnh</option>
                <option value="0.3">Bị che khuất</option>
              </select>
            </label>
          </div>
          <button
            class="button primary wide"
            disabled={busy || !robot.online || !robot.state?.camera.fresh || !objects.length}
          >
            <Camera size={18} /> Chụp & ghi nhận
          </button>
          <p class="hint">
            Nhận định do bạn cung cấp, gắn với ảnh đang hiển thị và thời gian chụp. Ảnh quá cũ sẽ bị
            từ chối.
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
