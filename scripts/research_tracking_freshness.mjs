// Actual model execution, authored camera input, no paid API or robot commands.
import { chromium } from "../web/node_modules/@playwright/test/index.mjs";
import { writeFile } from "node:fs/promises";
const output = process.env.PUPPYPI_STREAM_RUN;
const duration = Number(process.env.PUPPYPI_FRESHNESS_DURATION_S || 120);
if (!Number.isFinite(duration) || duration < 5 || duration > 240)
  throw Error("Invalid explicit diagnostic duration");
const browser = await chromium.launch();
const context = await browser.newContext({
  baseURL: "http://127.0.0.1:18770",
  viewport: { width: 390, height: 844 },
  isMobile: true,
  hasTouch: true,
});
const page = await context.newPage();
page.setDefaultTimeout(20000);
const events = [],
  samples = [],
  errors = [];
let vision = null;
await page.exposeFunction("recordTrackingTiming", (value) => events.push(value));
await page.addInitScript(() => {
  for (const type of ["puppypi-camera-painted", "puppypi-tracking-painted"])
    window.addEventListener(type, (e) => window.recordTrackingTiming({ type, ...e.detail }));
});
page.on("pageerror", (error) => errors.push(error.message));
async function api(path, body) {
  return page.evaluate(
    async ({ path, body }) => {
      const r = await fetch("/api" + path, {
        method: body === undefined ? "GET" : "POST",
        headers: { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const d = await r.json();
      if (!r.ok) throw Error(JSON.stringify(d));
      return d;
    },
    { path, body },
  );
}
try {
  await page.goto("/");
  await page.getByLabel("Pairing code").fill("synthetic-stream-acceptance");
  await page.getByRole("button", { name: "Open Field Console" }).click();
  for (let i = 0; i < 180; i++) {
    if ((await api("/tracking")).worker?.alive) break;
    if (i === 179) throw Error("Actual model worker unavailable");
    await page.waitForTimeout(500);
  }
  const cdp = await context.newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.emulateNetworkConditions", {
    offline: false,
    latency: 40,
    downloadThroughput: 1250000,
    uploadThroughput: 625000,
  });
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: 2 });
  const clock = [];
  for (let i = 0; i < 8; i++) {
    const start = Date.now(),
      t = await api("/timing"),
      end = Date.now();
    clock.push({
      start,
      end,
      ...t,
      offset_server_minus_client_ms: t.host_unix_ms - (start + end) / 2,
      uncertainty_ms: (end - start) / 2,
    });
  }
  await writeFile(output + "/clock.json", JSON.stringify(clock, null, 2));
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
  const panel = page.getByRole("region", { name: "Interactive target tracking" });
  await panel.scrollIntoViewIfNeeded();
  const started = Date.now();
  while (Date.now() - started < duration * 1000) {
    const state = (await api("/tracking")).sessions[0];
    samples.push({ sampled_client_unix_ms: Date.now(), ...state });
    if (!["running", "start_pending"].includes(state.status))
      throw Error("Actual tracking failed: " + state.error_code);
    if (!vision && Date.now() - started > 20000) {
      const objects = await api("/objects");
      const frame_id = await page.evaluate(async () => {
        const r = await fetch("/api/frame.jpg");
        await r.blob();
        return r.headers.get("X-Frame-Id");
      });
      vision = await api("/vision/jobs", {
        frame_id,
        object_ids: [objects[0].id],
        request_key: "freshness-concurrent-vision",
      });
    }
    await page.waitForTimeout(500);
  }
  await panel.screenshot({ path: output + "/phone-tracking.png" });
  const before = await api("/tracking");
  await writeFile(output + "/before-stop.json", JSON.stringify(before, null, 2));
  const stopStart = Date.now();
  await page.getByRole("button", { name: "Stop tracking", exact: true }).click();
  let after;
  for (let i = 0; i < 30; i++) {
    after = await api("/tracking");
    if (after.sessions[0].status === "stopped") break;
    await page.waitForTimeout(100);
  }
  await writeFile(
    output + "/stop.json",
    JSON.stringify({ http_and_ui_roundtrip_ms: Date.now() - stopStart, after }, null, 2),
  );
  if (after.sessions[0].status !== "stopped") throw Error("Stop did not commit");
  await panel.locator(".tracking-status strong").filter({ hasText: "Session: stopped" }).waitFor();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await panel.screenshot({
    path: output + "/desktop-tracking.png",
    style: ".topbar, .sidebar, .mobile-nav, .bottom-nav { visibility: hidden !important; }",
  });
  if (vision)
    await writeFile(
      output + "/vision.json",
      JSON.stringify(await api("/vision/jobs/" + vision.id), null, 2),
    );
} catch (error) {
  errors.push(String(error));
  process.exitCode = 1;
  await page.screenshot({ path: output + "/failure.png", fullPage: true }).catch(() => {});
} finally {
  await writeFile(
    output + "/browser.json",
    JSON.stringify(
      {
        schema_version: 2,
        input: "authored_pinhole_renderer_not_physics_or_physical_camera",
        duration_requested_s: duration,
        events,
        samples,
        errors,
      },
      null,
      2,
    ),
  );
  console.log(JSON.stringify({ samples: samples.length, events: events.length, errors }));
  await browser.close();
}
