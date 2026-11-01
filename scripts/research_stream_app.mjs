// Explicit synthetic input; real app, upstream workers, browser and API calls.
import { chromium } from "../web/node_modules/@playwright/test/index.mjs";
import { writeFile } from "node:fs/promises";
if (process.env.PUPPYPI_ALLOW_PAID_API !== "1") throw Error("Paid opt-in required");
const base = process.env.PUPPYPI_STREAM_RUN;
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  baseURL: "http://127.0.0.1:18770",
  viewport: { width: 390, height: 844 },
  isMobile: true,
  hasTouch: true,
  deviceScaleFactor: 1,
});
const page = await context.newPage();
page.setDefaultTimeout(20000);
const events = [],
  phases = [],
  errors = [],
  jobs = [];
let phase = "startup";
const record = async (value) => {
  events.push({ ...value, phase });
};
await page.exposeFunction("recordBenchmark", record);
await page.addInitScript(() => {
  for (const name of ["puppypi-camera-painted", "puppypi-tracking-painted"])
    window.addEventListener(name, (e) => window.recordBenchmark({ type: name, ...e.detail }));
});
page.on("pageerror", (e) => errors.push(e.message));
async function api(path, body) {
  return page.evaluate(
    async ({ path, body }) => {
      const response = await fetch("/api" + path, {
        method: body === undefined ? "GET" : "POST",
        headers: { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const result = await response.json();
      if (!response.ok) throw Error(path + ": " + JSON.stringify(result));
      return result;
    },
    { path, body },
  );
}
async function waitJob(job, path) {
  const started = Date.now();
  while (Date.now() - started < 310000) {
    const result = await api(path + "/" + job.id);
    if (!["queued", "running"].includes(result.status)) {
      jobs.push(result);
      await writeFile(base + "/jobs.json", JSON.stringify(jobs, null, 2));
      return result;
    }
    await page.waitForTimeout(500);
  }
  throw Error("Job timeout " + job.id);
}
async function interval(name, ms) {
  phase = name;
  phases.push({ name, start_unix_ms: Date.now(), duration_ms: ms });
  await page.waitForTimeout(ms);
}
async function selectTrack() {
  await page.getByRole("button", { name: "Select target", exact: true }).click();
  const svg = page.getByRole("img", { name: "Frozen target selection image" });
  await svg.waitFor();
  await svg.scrollIntoViewIfNeeded();
  // Authored foreground click, not an inferred identity or success label.
  const bounds = await svg.boundingBox();
  await page.touchscreen.tap(
    bounds.x + (bounds.width * 150) / 640,
    bounds.y + (bounds.height * 200) / 480,
  );
  await page.getByRole("button", { name: "Preview model mask", exact: true }).click();
  const start = Date.now();
  await page.getByRole("button", { name: "Track this object", exact: true }).waitFor();
  while (
    !(await page.getByRole("button", { name: "Track this object", exact: true }).isEnabled())
  ) {
    if (Date.now() - start > 12000) throw Error("SAM preview failed");
    await page.waitForTimeout(100);
  }
  await page.getByRole("button", { name: "Track this object", exact: true }).click();
}
try {
  await page.goto("http://127.0.0.1:18770");
  await page.getByLabel("Pairing code").fill("synthetic-stream-acceptance");
  await page.getByRole("button", { name: "Open Field Console" }).click();
  for (let i = 0; i < 180; i++) {
    const state = await api("/tracking");
    if (state.worker?.alive) break;
    if (i === 179) throw Error("Tracking model failed");
    await page.waitForTimeout(500);
  }
  const clock = [];
  for (let i = 0; i < 8; i++) {
    const start = Date.now(),
      server = await api("/timing"),
      end = Date.now();
    clock.push({
      start,
      end,
      ...server,
      offset_server_minus_client_ms: server.host_unix_ms - (start + end) / 2,
      uncertainty_ms: (end - start) / 2,
    });
  }
  await writeFile(base + "/clock.json", JSON.stringify(clock, null, 2));
  await interval("camera_loopback", 15000);
  const cdp = await context.newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.emulateNetworkConditions", {
    offline: false,
    latency: 40,
    downloadThroughput: 1250000,
    uploadThroughput: 625000,
  });
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: 2 });
  await interval("camera_emulated_network", 15000);
  if (process.env.PUPPYPI_STREAM_SCENARIO === "tracking-diagnostic") {
    phase = "box_selection";
    await page.getByRole("button", { name: "Select target", exact: true }).click();
    await page.getByText("Keyboard box input", { exact: true }).click();
    for (const [name, value] of [
      ["left", 105],
      ["top", 155],
      ["right", 215],
      ["bottom", 250],
    ])
      await page.getByLabel("Target box " + name, { exact: true }).fill(String(value));
    await page.getByRole("button", { name: "Preview model mask", exact: true }).click();
    for (let i = 0; i < 100; i++) {
      if (await page.getByRole("button", { name: "Track this object", exact: true }).isEnabled())
        break;
      await page.waitForTimeout(100);
    }
    await page.getByRole("button", { name: "Track this object", exact: true }).click();
    await page
      .getByRole("region", { name: "Interactive target tracking" })
      .scrollIntoViewIfNeeded();
    await interval("tracking_diagnostic_3hz", 60000);
    await page
      .getByRole("region", { name: "Interactive target tracking" })
      .screenshot({ path: base + "/phone-tracking.png" });
    await writeFile(
      base + "/tracking-after-load.json",
      JSON.stringify(await api("/tracking"), null, 2),
    );
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.screenshot({ path: base + "/desktop-monitor.png", fullPage: true });
    const session = (await api("/tracking")).sessions[0];
    const started = performance.now();
    await api("/tracking/sessions/" + session.id + "/stop", {});
    await writeFile(
      base + "/stop.json",
      JSON.stringify({ http_roundtrip_ms: performance.now() - started }),
    );
  } else {
    phase = "tracking_selection";
    await selectTrack();
    await interval("tracking_cpu", 20000);
    await page
      .getByRole("region", { name: "Interactive target tracking" })
      .screenshot({ path: base + "/phone-tracking.png" });
    const before = await api("/tracking");
    await writeFile(base + "/tracking-before-load.json", JSON.stringify(before, null, 2));
    if (before.sessions[0] && !["running", "start_pending"].includes(before.sessions[0].status)) {
      // New explicitly selected target after the recorded failure; never conceal it.
      phase = "tracking_reselection";
      await selectTrack();
    }
    phase = "concurrent";
    phases.push({ name: phase, start_unix_ms: Date.now() });
    const [view, episode, objects] = await Promise.all([
      api("/memory/views", { region_name: "Rendered desk", viewpoint_name: "Front" }),
      api("/memory/episodes", { name: "Concurrent CPU benchmark" }),
      api("/objects"),
    ]);
    const frame_id = await page.evaluate(async () => {
      const r = await fetch("/api/frame.jpg");
      await r.blob();
      return r.headers.get("X-Frame-Id");
    });
    const capture = await api("/memory/captures", {
      episode_id: episode.id,
      view_id: view.id,
      frame_id,
      request_key: "benchmark-capture",
    });
    const vision = await api("/vision/jobs", {
      object_ids: [objects[0].id],
      frame_id,
      request_key: "benchmark-vision",
    });
    const visionWait = waitJob(vision, "/vision/jobs");
    const described = await waitJob(capture, "/memory/jobs");
    if (described.status === "succeeded") {
      const question = await api("/memory/questions", {
        question:
          "Describe the visible colors and symbols of the three boxes in the recorded capture. Use only recorded evidence.",
        episode_ids: [episode.id],
        request_key: "benchmark-question",
        scope: "recorded_memory",
      });
      await waitJob(question, "/memory/jobs");
    }
    await visionWait;
    await page.waitForTimeout(10000);
    await writeFile(
      base + "/tracking-after-load.json",
      JSON.stringify(await api("/tracking"), null, 2),
    );
    // View screenshots on both sizes while the same real app remains hosted.
    await page.screenshot({ path: base + "/phone-monitor.png", fullPage: true });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.waitForTimeout(1000);
    await page.screenshot({ path: base + "/desktop-monitor.png", fullPage: true });
    const session = (await api("/tracking")).sessions[0];
    if (session) {
      const start = performance.now();
      const stopped = await api("/tracking/sessions/" + session.id + "/stop", {});
      await writeFile(
        base + "/stop.json",
        JSON.stringify({ http_roundtrip_ms: performance.now() - start, stopped }, null, 2),
      );
    }
    await page.getByRole("button", { name: "Room memory", exact: true }).click();
    await page.waitForTimeout(1000);
    const cited = page.getByAltText("Inspected capture at Rendered desk", { exact: true });
    await cited.scrollIntoViewIfNeeded();
    await cited.evaluate((img) => img.decode());
    await page.screenshot({ path: base + "/desktop-memory.png", fullPage: true });
    await writeFile(base + "/memory.json", JSON.stringify(await api("/memory"), null, 2));
    await writeFile(base + "/vision.json", JSON.stringify(await api("/vision"), null, 2));
  }
} catch (e) {
  errors.push(String(e));
  await page.screenshot({ path: base + "/failure.png", fullPage: true }).catch(() => {});
  process.exitCode = 1;
} finally {
  await writeFile(
    base + "/browser.json",
    JSON.stringify(
      {
        input: "authored rendered camera, no physical phone/robot",
        network: {
          http_latency_parameter_ms: 40,
          download_bytes_s: 1250000,
          upload_bytes_s: 625000,
          cpu_throttle: 2,
        },
        phases,
        events,
        errors,
      },
      null,
      2,
    ),
  );
  console.log(
    JSON.stringify({
      events: events.length,
      errors,
      jobs: jobs.map((j) => ({ kind: j.kind, status: j.status, error: j.error_code })),
    }),
  );
  await browser.close();
}
