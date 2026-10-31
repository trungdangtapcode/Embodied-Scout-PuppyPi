// Rasterize the project-owned vector mark for home-screen platform compatibility.
import { chromium } from '@playwright/test';
import { readFile } from 'node:fs/promises';
const browser = await chromium.launch();
try {
  const svg = await readFile(new URL('../public/icon.svg', import.meta.url), 'utf8');
  for (const size of [180, 192, 512]) {
    const page = await browser.newPage({ viewport: { width: size, height: size } });
    await page.setContent(`<style>body{margin:0}svg{display:block;width:100%;height:100%}</style>${svg}`);
    await page.screenshot({ path: new URL(`../public/icon-${size}.png`, import.meta.url).pathname });
    await page.close();
  }
} finally { await browser.close(); }
