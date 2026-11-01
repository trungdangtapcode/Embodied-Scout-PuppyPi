import { test, expect, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import vietnamese from "../src/locales/vi.json" with { type: "json" };
import type { SceneAnalysis } from "../src/roomTypes";

async function enter(page: Page) {
  await page.goto("/");
  await page.getByLabel("Pairing code").fill("synthetic-browser-test");
  await page.getByRole("button", { name: "Open Field Console" }).click();
  await expect(page.getByRole("heading", { name: "Monitor." })).toBeVisible();
  await expect(page.getByAltText("Robot camera view")).toBeVisible();
  await expect(page.getByText("Ready to observe")).toBeVisible();
}

test("English default ignores browser locale; explicit localization persists and disarms control", async ({
  browser,
}) => {
  const context = await browser.newContext({
    locale: "vi-VN",
    viewport: { width: 390, height: 844 },
  });
  try {
    const page = await context.newPage();
    await page.goto("/");
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    await expect(page.getByRole("heading", { name: "Welcome, operator." })).toBeVisible();
    await page.getByRole("combobox", { name: "Language" }).selectOption("vi");
    await expect(page.locator("html")).toHaveAttribute("lang", "vi");
    await page.getByLabel(vietnamese["Pairing code"]).fill("synthetic-browser-test");
    await page.getByRole("button", { name: vietnamese["Open Field Console"] }).click();
    await expect(page.getByRole("button", { name: vietnamese.Library, exact: true })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("button", { name: vietnamese.Library, exact: true })).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("lang", "vi");
    await page.getByRole("combobox", { name: vietnamese.Language }).selectOption("en");
    await page.getByRole("button", { name: "Control", exact: true }).click();
    await page.getByRole("button", { name: "Arm controls" }).click();
    await expect(page.getByRole("button", { name: "Forward", exact: true })).toBeEnabled();
    await page.getByRole("combobox", { name: "Language" }).selectOption("vi");
    await expect(
      page.getByRole("button", { name: vietnamese.Forward, exact: true }),
    ).toBeDisabled();
    await expect
      .poll(async () => (await (await page.request.get("/api/state")).json()).control.armed)
      .toBe(false);
    await page.getByRole("combobox", { name: vietnamese.Language }).selectOption("en");
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    await page.reload();
    await expect(page.getByRole("button", { name: "Library", exact: true })).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
  } finally {
    await context.close();
  }
});

test("desktop library, evidence assessment, portable export and screenshots", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await enter(page);
  await page.getByRole("button", { name: "Load demo data" }).click();
  await expect(page.getByText("03", { exact: true })).toBeVisible();
  await mkdir("../runs/mobile-preview", { recursive: true });
  await page.getByLabel("Dismiss notification").click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: "../runs/mobile-preview/desktop-monitor.png", fullPage: true });
  await page.getByRole("button", { name: "Inspect", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Workbench readiness" })).toBeVisible();
  const downloaded = page.waitForEvent("download");
  await page.getByLabel("Download report ZIP").click();
  expect((await downloaded).suggestedFilename()).toMatch(/puppypi-report-.*\.zip/);
  await page.getByRole("combobox", { name: "Object", exact: true }).selectOption({ index: 1 });
  await page.getByRole("button", { name: "Capture & record" }).click();
  await expect(page.getByRole("status")).toContainText("Image and operator assertion saved.");
  await page.getByRole("button", { name: "Assess", exact: true }).click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: "../runs/mobile-preview/desktop-inspect.png", fullPage: true });
  await page.getByRole("button", { name: "Library", exact: true }).click();
  await page.locator(".object-card").first().click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByText("Observation history", { exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "Teach object", exact: true }).click();
  await page.getByLabel("Object name", { exact: true }).fill("Browser taught crop");
  const objects = await (await page.request.get("/api/objects")).json();
  const crop = await (
    await page.request.get("/api/evidence/" + objects[0].references[0].image_sha)
  ).body();
  await page
    .locator("input[type=file]")
    .setInputFiles({ name: "crop.png", mimeType: "image/png", buffer: crop });
  await page.getByRole("button", { name: "Save to library" }).click();
  await expect(page.getByRole("heading", { name: "Browser taught crop" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("hold to drive, release to zero, blur disarms and reconnect stays locked", async ({
  page,
}) => {
  await enter(page);
  await page.getByRole("button", { name: "Control", exact: true }).click();
  await page.getByRole("button", { name: "Arm controls" }).click();
  const forward = page.getByRole("button", { name: "Forward", exact: true });
  await expect(forward).toBeEnabled();
  await forward.hover();
  await page.mouse.down();
  await expect
    .poll(async () => (await (await page.request.get("/api/state")).json()).control.command.vx_cm_s)
    .toBeGreaterThan(0);
  await page.mouse.up();
  await expect
    .poll(async () => (await (await page.request.get("/api/state")).json()).control.command.vx_cm_s)
    .toBe(0);
  await page.evaluate(() => window.dispatchEvent(new Event("blur")));
  await expect(forward).toBeDisabled();
  await expect
    .poll(async () => (await (await page.request.get("/api/state")).json()).control.armed)
    .toBe(false);
  await page.getByRole("button", { name: "Arm controls" }).click();
  await expect(forward).toBeEnabled();
  await page.getByRole("button", { name: "STOP", exact: true }).click();
  await expect(forward).toBeDisabled();
  await page.context().setOffline(true);
  await expect(page.getByText("Host disconnected.", { exact: false })).toBeVisible();
  await page.context().setOffline(false);
  await expect(page.getByRole("button", { name: "Arm controls" })).toBeEnabled();
  await expect(forward).toBeDisabled();
});

test("phone layout, camera, inspector and static-only offline cache", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await enter(page);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: "../runs/mobile-preview/phone-monitor.png" });
  for (const name of ["Control", "Inspect", "Library"]) {
    await page.getByRole("button", { name, exact: true }).click();
    await page.evaluate(() => window.scrollTo(0, 0));
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await expect(page.getByRole("button", { name: "STOP", exact: true })).toBeInViewport();
    if (name === "Inspect")
      await page.screenshot({ path: "../runs/mobile-preview/phone-inspect.png" });
    if (name === "Control") {
      await expect(page.getByRole("button", { name: "Forward", exact: true })).toBeInViewport();
      await expect(page.getByAltText("Robot camera view")).toBeInViewport();
      await page.screenshot({ path: "../runs/mobile-preview/phone-control.png" });
    }
  }
  await page.evaluate(() => navigator.serviceWorker.ready);
  const cached = await page.evaluate(async () => {
    const keys = await caches.keys();
    return (
      await Promise.all(
        keys.map(async (key) => (await (await caches.open(key)).keys()).map((r) => r.url)),
      )
    ).flat();
  });
  expect(cached.length).toBeGreaterThan(0);
  expect(cached.some((path) => path.includes("/api/"))).toBe(false);
});

test("room memory links suggestions, confirmed sightings and conservative temporal answers", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await enter(page);
  await page.request.post("/api/demo");
  await page.reload();
  await page.getByRole("button", { name: "Room memory", exact: true }).click();
  await page.getByText("Operator assertions and appearance baseline", { exact: true }).click();
  await expect(page.getByRole("heading", { name: "Room memory", exact: true })).toBeVisible();
  const firstResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/room/analyses") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Analyze current view" }).click();
  const first: SceneAnalysis = await (await firstResponse).json();
  expect(first.candidates.length).toBeGreaterThan(0);
  const crop = await page.request.get(`/api/evidence/${first.candidates[0].crop_image_sha}`);
  const enrollment = await page.request.post("/api/objects", {
    multipart: {
      name: "Temporal browser case",
      files: { name: "reference.png", mimeType: "image/png", buffer: await crop.body() },
    },
  });
  expect(enrollment.ok()).toBe(true);
  const object = await enrollment.json();
  await page.reload();
  await page.getByRole("button", { name: "Room memory", exact: true }).click();
  await page.getByText("Operator assertions and appearance baseline", { exact: true }).click();
  const analysisResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/room/analyses") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Analyze current view" }).click();
  const analysis: SceneAnalysis = await (await analysisResponse).json();
  await page.getByLabel("Observed region", { exact: true }).fill("Browser shelf");
  await page.getByLabel("Candidate object 1", { exact: true }).selectOption(object.id);
  await page.getByRole("button", { name: "Confirm sighting", exact: true }).first().click();
  await expect(page.getByRole("button", { name: "Sighting recorded", exact: true })).toBeVisible();
  await page.getByRole("combobox", { name: "Object", exact: true }).selectOption(object.id);
  await page.getByRole("button", { name: "Ask from evidence" }).click();
  await expect(
    page.getByLabel("Room answer").getByText("Supported", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByLabel("Room answer").getByText("Browser shelf", { exact: true }),
  ).toBeVisible();
  await page.getByRole("combobox", { name: "Question", exact: true }).selectOption("stayed_at");
  await page.getByLabel("Region", { exact: true }).fill("Browser shelf");
  await expect.poll(() => Date.now() - Date.parse(analysis.captured_at)).toBeGreaterThan(1100);
  await page.getByRole("button", { name: "Use latest hour" }).click();
  await page.getByRole("button", { name: "Ask from evidence" }).click();
  await expect(page.getByLabel("Room answer").getByText("Unknown", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Room answer")).toContainText(
    "Separate observations cannot establish",
  );
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download answer" }).click();
  expect((await download).suggestedFilename()).toMatch(/^room-answer-/);
  await mkdir("../runs/room-preview", { recursive: true });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: "../runs/room-preview/desktop-room.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "../runs/room-preview/phone-room.png", fullPage: false });
  await page.locator(".room-answer").scrollIntoViewIfNeeded();
  await page.screenshot({ path: "../runs/room-preview/phone-answer.png" });
  await page.reload();
  await page.getByRole("button", { name: "Room memory", exact: true }).click();
  await page.getByText("Operator assertions and appearance baseline", { exact: true }).click();
  await page.getByText("Saved answers", { exact: true }).click();
  await page
    .getByRole("button", { name: "Temporal browser case Stayed throughout a time range" })
    .first()
    .click();
  await expect(page.getByLabel("Room answer").getByText("Unknown", { exact: true })).toBeVisible();
  expect(errors).toEqual([]);
  const memory = await (await page.request.get("/api/room")).json();
  expect(
    memory.timeline.some(
      (row: { provenance: { scene_analysis_id?: string } }) =>
        row.provenance.scene_analysis_id === analysis.id,
    ),
  ).toBe(true);
});

test("recorded-memory captures queue without a worker, cancel and survive reload", async ({
  page,
}) => {
  await enter(page);
  await page.getByRole("button", { name: "Room memory", exact: true }).click();
  const memory = page.getByRole("region", { name: "Mind Palace memory", exact: true });
  await expect(memory.getByText("Worker unavailable", { exact: true })).toBeVisible();
  await memory.getByText("Register a viewpoint", { exact: true }).click();
  await memory.getByLabel("Region name", { exact: true }).fill("Browser region");
  await memory.getByLabel("Viewpoint name", { exact: true }).fill("Front");
  await memory.getByRole("button", { name: "Save viewpoint", exact: true }).click();
  await memory.getByLabel("New episode name", { exact: true }).fill("Browser memory episode");
  await memory.getByRole("button", { name: "Create episode", exact: true }).click();
  await expect(
    memory.getByRole("button", { name: "Capture displayed frame", exact: true }),
  ).toBeEnabled();
  await memory.getByRole("button", { name: "Capture displayed frame", exact: true }).click();
  const result = memory.getByRole("region", { name: "Mind Palace result", exact: true });
  await expect(result.getByText("queued", { exact: true })).toBeVisible();
  await result.getByRole("button", { name: "Cancel job", exact: true }).click();
  await expect(result.getByText("cancelled", { exact: true })).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Room memory", exact: true }).click();
  await expect(page.getByText("Saved memory captures", { exact: false })).toBeVisible();
  await expect(
    page
      .getByRole("region", { name: "Mind Palace result", exact: true })
      .getByText("cancelled", { exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    .toBe(true);
  await page.screenshot({ path: "../runs/mobile-preview/phone-memory-queued.png", fullPage: true });
});
