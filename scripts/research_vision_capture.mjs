import { chromium } from "../web/node_modules/@playwright/test/index.mjs";
import { readFile, writeFile } from "node:fs/promises";

const base = process.env.PUPPYPI_VISION_ACCEPTANCE_DIR;
if (!base) throw Error("Run through the disposable vision acceptance launcher");
const browser = await chromium.launch({ headless: true });
const results = [];
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const errors = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.goto("http://127.0.0.1:18768");
  await page.getByLabel("Pairing code").fill("synthetic-vision-acceptance");
  await page.getByRole("button", { name: "Open Field Console" }).click();
  const manifest = JSON.parse(await readFile(base + "/truth.json", "utf8"));
  // Enroll through the real Library UI. These names/images are explicit inputs.
  await page.getByRole("button", { name: "Library", exact: true }).click();
  for (const key of manifest.reference_keys) {
    await page.getByRole("button", { name: "Teach object", exact: true }).click();
    await page.getByLabel("Object name", { exact: true }).fill(key);
    await page.locator("input[type=file]").setInputFiles([0, 1, 2].map(i => `${base}/reference-${key}-${i}.png`));
    await page.getByRole("button", { name: "Save to library" }).click();
    await page.getByRole("heading", { name: key, exact: true }).waitFor();
  }
  await page.getByRole("button", { name: "Monitor", exact: true }).click();
  await page.getByRole("button", { name: "Room memory", exact: true }).click();
  const panel = page.getByRole("region", { name: "Learned visual perception", exact: true });
  await panel.getByRole("checkbox").first().waitFor();
  for (const checkbox of await panel.getByRole("checkbox").all()) await checkbox.check();
  const get = async path => {
    const response = await page.request.get("http://127.0.0.1:18768/api" + path);
    if (!response.ok()) throw Error(await response.text());
    return response.json();
  };
  for (const scene of Object.keys(manifest.scenes)) {
    await writeFile(base + "/scene.txt", scene);
    await page.waitForTimeout(2800);
    const created = page.waitForResponse(r => r.url().endsWith("/api/vision/jobs") && r.request().method() === "POST");
    await panel.getByRole("button", { name: "Analyze camera window" }).click();
    const admission = await created;
    if (!admission.ok()) throw Error(await admission.text());
    const admitted = await admission.json();
    let job;
    for (let i = 0; i < 240; i++) {
      job = await get("/vision/jobs/" + admitted.id);
      if (job && !["queued", "running"].includes(job.status)) break;
      await page.waitForTimeout(250);
    }
    if (job?.status !== "succeeded") throw Error(`Actual model execution failed: ${JSON.stringify(job)}`);
    results.push({ scene, job });
    await writeFile(base + "/app-runs.json", JSON.stringify(results, null, 2));
    console.log(scene, job.status, job.result.frames.length, "frames");
    if (scene === "moving") {
      await panel.getByText("Run status: Executed / quality unverified", { exact: true }).waitFor();
      const dismiss = page.getByLabel("Dismiss notification");
      if (await dismiss.count()) await dismiss.click();
      await panel.getByRole("img", { name: "Model detections on saved camera image" }).waitFor();
      await panel.screenshot({ path: base + "/desktop-vision.png", style: ".topbar, .sidebar, .mobile-nav, .bottom-nav { visibility: hidden !important; }" });
      await page.setViewportSize({ width: 390, height: 844 });
      await panel.screenshot({ path: base + "/phone-vision.png", style: ".topbar, .sidebar, .mobile-nav, .bottom-nav { visibility: hidden !important; }" });
      if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw Error("Phone overflow");
      await page.setViewportSize({ width: 1440, height: 1100 });
    }
  }
  if (errors.length) throw Error(errors.join("\n"));
} finally {
  await browser.close();
}
