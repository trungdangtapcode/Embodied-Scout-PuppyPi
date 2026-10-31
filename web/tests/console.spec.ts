import { test, expect, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";

async function enter(page: Page) {
  await page.goto("/");
  await page.getByLabel("Mã ghép nối").fill("synthetic-browser-test");
  await page.getByRole("button", { name: "Mở Field Console" }).click();
  await expect(page.getByRole("heading", { name: "Monitor." })).toBeVisible();
  await expect(page.getByAltText("Góc nhìn camera robot")).toBeVisible();
  await expect(page.getByText("Sẵn sàng quan sát")).toBeVisible();
}

test("desktop library, evidence assessment, portable export and screenshots", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await enter(page);
  await page.getByRole("button", { name: "Nạp dữ liệu demo" }).click();
  await expect(page.getByText("03", { exact: true })).toBeVisible();
  await mkdir("../runs/mobile-preview", { recursive: true });
  await page.getByLabel("Đóng thông báo").click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: "../runs/mobile-preview/desktop-monitor.png", fullPage: true });
  await page.getByRole("button", { name: "Inspect", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Workbench readiness" })).toBeVisible();
  const downloaded = page.waitForEvent("download");
  await page.getByLabel("Tải báo cáo ZIP").click();
  expect((await downloaded).suggestedFilename()).toMatch(/puppypi-report-.*\.zip/);
  await page.getByRole("combobox", { name: "Vật thể", exact: true }).selectOption({ index: 1 });
  await page.getByRole("button", { name: "Chụp & ghi nhận" }).click();
  await expect(page.getByRole("status")).toContainText("Đã lưu ảnh");
  await page.getByRole("button", { name: "Đánh giá", exact: true }).click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: "../runs/mobile-preview/desktop-inspect.png", fullPage: true });
  await page.getByRole("button", { name: "Thư viện", exact: true }).click();
  await page.locator(".object-card").first().click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByText("Lịch sử quan sát", { exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "Dạy vật thể", exact: true }).click();
  await page.getByLabel("Tên vật thể", { exact: true }).fill("Browser taught crop");
  const objects = await (await page.request.get("/api/objects")).json();
  const crop = await (
    await page.request.get("/api/evidence/" + objects[0].references[0].image_sha)
  ).body();
  await page
    .locator("input[type=file]")
    .setInputFiles({ name: "crop.png", mimeType: "image/png", buffer: crop });
  await page.getByRole("button", { name: "Lưu vào thư viện" }).click();
  await expect(page.getByRole("heading", { name: "Browser taught crop" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("hold to drive, release to zero, blur disarms and reconnect stays locked", async ({
  page,
}) => {
  await enter(page);
  await page.getByRole("button", { name: "Điều khiển", exact: true }).click();
  await page.getByRole("button", { name: "Mở quyền điều khiển" }).click();
  const forward = page.getByRole("button", { name: "Tiến", exact: true });
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
  await page.getByRole("button", { name: "Mở quyền điều khiển" }).click();
  await expect(forward).toBeEnabled();
  await page.getByRole("button", { name: "STOP", exact: true }).click();
  await expect(forward).toBeDisabled();
  await page.context().setOffline(true);
  await expect(page.getByText("Mất kết nối host.", { exact: false })).toBeVisible();
  await page.context().setOffline(false);
  await expect(page.getByRole("button", { name: "Mở quyền điều khiển" })).toBeEnabled();
  await expect(forward).toBeDisabled();
});

test("phone layout, camera, inspector and static-only offline cache", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await enter(page);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: "../runs/mobile-preview/phone-monitor.png" });
  for (const name of ["Điều khiển", "Inspect", "Thư viện"]) {
    await page.getByRole("button", { name, exact: true }).click();
    await page.evaluate(() => window.scrollTo(0, 0));
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await expect(page.getByRole("button", { name: "STOP", exact: true })).toBeInViewport();
    if (name === "Inspect")
      await page.screenshot({ path: "../runs/mobile-preview/phone-inspect.png" });
    if (name === "Điều khiển") {
      await expect(page.getByRole("button", { name: "Tiến", exact: true })).toBeInViewport();
      await expect(page.getByAltText("Góc nhìn camera robot")).toBeInViewport();
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
