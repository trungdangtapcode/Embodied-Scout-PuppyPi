import { chromium } from "../web/node_modules/@playwright/test/index.mjs";
import { writeFile } from "node:fs/promises";
if (process.env.PUPPYPI_ALLOW_PAID_API !== "1")
  throw Error("Explicit paid acceptance opt-in is required");
const base = process.env.PUPPYPI_MEMORY_ACCEPTANCE_DIR + "/";
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.setDefaultTimeout(20000);
  await page.goto("http://127.0.0.1:18767");
  await page.getByLabel("Pairing code").fill("synthetic-memory-acceptance");
  await page.getByRole("button", { name: "Open Field Console" }).click();
  await page.getByRole("button", { name: "Room memory", exact: true }).click();
  const initial = await (await page.request.get("http://127.0.0.1:18767/api/memory")).json();
  if (initial.episodes.length && !process.argv.includes("--screenshots-only"))
    throw Error("Use a new disposable acceptance directory");
  if (process.argv.includes("--screenshots-only")) {
    const panel = page.getByRole("region", { name: "Mind Palace memory", exact: true });
    await panel
      .locator(".memory-run")
      .filter({ hasText: "Compare only the visible colored objects in the Desk captures" })
      .first()
      .click();
    await panel.locator(".memory-answer-text").waitFor();
    await panel.screenshot({
      path: base + "desktop-memory.png",
      style: ".topbar, .sidebar, .mobile-nav, .bottom-nav { visibility: hidden !important; }",
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page
      .getByRole("region", { name: "Mind Palace result", exact: true })
      .screenshot({
        path: base + "phone-memory-answer.png",
        style: ".topbar, .sidebar, .mobile-nav, .bottom-nav { visibility: hidden !important; }",
      });
    await page.screenshot({ path: base + "phone-memory-full.png", fullPage: true });
    if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth))
      throw Error("Phone layout overflow");
    await writeFile(
      base + "final-state.json",
      JSON.stringify(
        await (await page.request.get("http://127.0.0.1:18767/api/memory")).json(),
        null,
        2,
      ),
    );
    process.exitCode = 0;
  } else {
    await page.getByText("Register a viewpoint", { exact: true }).click();
    for (const region of ["Desk", "Shelf"]) {
      await page.getByLabel("Region name", { exact: true }).fill(region);
      await page.getByLabel("Viewpoint name", { exact: true }).fill("Front");
      await page.getByRole("button", { name: "Save viewpoint", exact: true }).click();
      await page.waitForTimeout(500);
    }
    const state = async () =>
      await (await page.request.get("http://127.0.0.1:18767/api/memory")).json();
    for (let episode = 0; episode < 3; episode++) {
      await page
        .getByLabel("New episode name", { exact: true })
        .fill(["Early", "Middle", "Late"][episode]);
      await page.getByRole("button", { name: "Create episode", exact: true }).click();
      await page.waitForTimeout(500);
      for (let view = 0; view < 2; view++) {
        await writeFile(base + "current-scene.txt", String(episode * 2 + view));
        await page
          .getByLabel("Memory viewpoint", { exact: true })
          .selectOption({ label: ["Desk · Front", "Shelf · Front"][view] });
        await page.waitForTimeout(1000);
        await page.getByRole("button", { name: "Capture displayed frame", exact: true }).click();
        let memory;
        for (let i = 0; i < 180; i++) {
          await page.waitForTimeout(500);
          memory = await state();
          const job = memory.jobs[0];
          if (!["queued", "running"].includes(job.status)) break;
        }
        const job = memory.jobs[0];
        console.log(
          JSON.stringify({
            capture: episode * 2 + view,
            status: job.status,
            error: job.error_code,
            description: job.result?.description,
          }),
        );
        if (job.status !== "succeeded") throw Error("Capture failed " + job.error_code);
      }
    }
    await page.screenshot({ path: base + "desktop-captures.png", fullPage: true });
    await writeFile(base + "capture-state.json", JSON.stringify(await state(), null, 2));
  }
} finally {
  await browser.close();
}
