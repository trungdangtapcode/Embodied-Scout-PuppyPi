import { chromium, expect } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
const [base, output] = process.argv.slice(2);
const token = process.env.PUPPYPI_OPERATOR_TOKEN;
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(base);
  await page.getByLabel("Pairing code").fill(token);
  await page.getByRole("button", { name: "Open Field Console" }).click();
  await expect(page.getByRole("heading", { name: "Monitor." })).toBeVisible();
  await page.getByRole("button", { name: "Library", exact: true }).click();
  const enrollment = JSON.parse(
    await fs.readFile(path.join(output, "references", "enrollment.json"), "utf8"),
  );
  for (const { name, files } of enrollment) {
    await page.getByRole("button", { name: "Teach object", exact: true }).click();
    await page.getByLabel("Object name", { exact: true }).fill(name);
    await page
      .locator("input[type=file]")
      .setInputFiles(files.map((file) => path.join(output, "references", file)));
    await page.getByRole("button", { name: "Save to library" }).click();
    await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
  }
  await page.getByRole("button", { name: "Monitor", exact: true }).click();
  await page.getByRole("button", { name: "Station search", exact: true }).click();
  if (await page.getByRole("button", { name: "Dismiss notification", exact: true }).count())
    await page.getByRole("button", { name: "Dismiss notification", exact: true }).click();
  const objects = await (await page.request.get(base + "/api/objects")).json();
  await page
    .getByRole("combobox", { name: "Search target" })
    .selectOption(objects.find((o) => o.name === "secret_box_1").id);
  await expect(page.getByRole("button", { name: "Start station search" })).toBeEnabled({
    timeout: 15000,
  });
  await page.getByRole("button", { name: "Start station search" }).click();
  await expect(page.getByRole("combobox", { name: "Search run" })).toBeVisible();
  await page.screenshot({ path: path.join(output, "desktop-started.png"), fullPage: true });
  const action = process.env.PUPPYPI_SEARCH_EVAL_ACTION;
  if (action) {
    await expect
      .poll(
        async () => {
          const state = await (await page.request.get(base + "/api/state")).json();
          return (
            Math.abs(state.control.command.vx_cm_s) + Math.abs(state.control.command.yaw_rate_rad_s)
          );
        },
        { timeout: 30000 },
      )
      .toBeGreaterThan(0);
    const sentAt = Date.now();
    await page
      .getByRole("button", { name: action === "cancel" ? "Cancel and stop" : "STOP", exact: true })
      .click();
    await expect
      .poll(async () => (await (await page.request.get(base + "/api/state")).json()).control.armed)
      .toBe(false);
    const after = await (await page.request.get(base + "/api/state")).json();
    await fs.writeFile(
      path.join(output, "stop-action.json"),
      JSON.stringify({ action, sentAt, observedStoppedAt: Date.now(), after }, null, 2),
    );
  }
  let overview;
  const deadline = Date.now() + 900000;
  while (Date.now() < deadline) {
    overview = await (await page.request.get(base + "/api/search")).json();
    if (overview.runs.length && !["queued", "running"].includes(overview.runs[0].status)) break;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  if (!overview?.runs.length || ["queued", "running"].includes(overview.runs[0].status))
    throw new Error("Search did not terminate within the evaluation budget.");
  const exported = await page.request.get(base + `/api/search/${overview.runs[0].id}?export=true`);
  if (!exported.ok()) throw new Error("Complete run evidence export failed.");
  overview.runs[0] = await exported.json();
  await page.waitForTimeout(1700);
  await page.screenshot({ path: path.join(output, "desktop-result.png"), fullPage: true });
  await page.setViewportSize({ width: 844, height: 390 });
  await page.screenshot({ path: path.join(output, "phone-landscape-result.png"), fullPage: true });
  await page.getByRole("heading", { name: "Search evidence", exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(output, "phone-landscape-evidence.png") });
  await page.setViewportSize({ width: 390, height: 844 });
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth))
    throw new Error("Phone search viewport has page overflow.");
  await page.screenshot({ path: path.join(output, "phone-result.png"), fullPage: true });
  if (overview.sightings.length && overview.runs[0].status === "completed") {
    const target = objects.find((o) => o.name === "secret_box_1");
    const history = await (
      await page.request.get(base + `/api/objects/${target.id}/history`)
    ).json();
    if (!history.automatic_sightings.some((s) => s.search_id === overview.runs[0].id))
      throw new Error("Confirmed model sighting missing from Library history.");
    await page.reload();
    await page.getByRole("button", { name: "Library", exact: true }).click();
    await page.locator(".object-card").filter({ hasText: "secret_box_1" }).click();
    await expect(
      page.getByRole("heading", { name: "Automatic model sightings", exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: path.join(output, "phone-automatic-history.png"),
      fullPage: true,
    });
    await fs.writeFile(path.join(output, "library-history.json"), JSON.stringify(history, null, 2));
    const room = await (await page.request.get(base + "/api/room")).json();
    if (
      !room.timeline.some((row) => row.source === "model_inference" && row.object_id === target.id)
    )
      throw new Error("Model observation missing from shared Room timeline.");
    const questionResponse = await page.request.post(base + "/api/room/queries", {
      data: { kind: "last_seen", object_id: target.id },
    });
    if (!questionResponse.ok()) throw new Error("Historical question failed.");
    const answer = await questionResponse.json();
    if (
      answer.status !== "supported" ||
      !answer.evidence.some((row) => row.source === "model_inference")
    )
      throw new Error("Historical answer did not use actual model evidence.");
    await fs.writeFile(
      path.join(output, "room-model-answer.json"),
      JSON.stringify({ room, answer }, null, 2),
    );
  }
  await fs.writeFile(
    path.join(output, "app-result.json"),
    JSON.stringify({ overview, browserErrors: errors }, null, 2),
  );
  if (errors.length) throw new Error(errors.join("\n"));
  console.log(
    JSON.stringify({
      status: overview.runs[0].status,
      result: overview.runs[0].result,
      error: overview.runs[0].error,
    }),
  );
} finally {
  await browser.close();
}
