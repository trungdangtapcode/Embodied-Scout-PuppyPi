import { chromium, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
const [base, output, targetId, existingId] = process.argv.slice(2);
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  await page.goto(base);
  await page.getByLabel('Pairing code').fill(process.env.PUPPYPI_OPERATOR_TOKEN);
  await page.getByRole('button', { name: 'Open Field Console' }).click();
  await page.getByRole('button', { name: 'Station search', exact: true }).click();
  await page.getByRole('combobox', { name: 'Search target' }).selectOption(targetId);
  if (!existingId) {
    await expect(page.getByRole('button', { name: 'Start station search' })).toBeEnabled({ timeout: 15000 });
    await page.getByRole('button', { name: 'Start station search' }).click();
  }
  let overview;
  const deadline = Date.now() + 900000;
  while (Date.now() < deadline) {
    overview = await (await page.request.get(base + '/api/search')).json();
    if (overview.runs.length && !['queued', 'running'].includes(overview.runs[0].status)) break;
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
  const latest = overview?.runs[0];
  if (!latest) throw Error('No actual search result.');
  if (existingId && latest.id !== existingId) throw Error('Recorded sighting ID changed.');
  const response = await page.request.get(`${base}/api/search/${latest.id}?export=true`);
  if (!response.ok()) throw Error('Actual evidence export failed.');
  overview.runs[0] = await response.json();
  await fs.writeFile(path.join(output, 'app-result.json'), JSON.stringify({ overview, browserErrors: errors }, null, 2));
  if (latest.status !== 'completed' || !overview.qualification.qualified) throw Error('Qualified actual search did not complete; no publication substitute.');
  await expect(page.locator('.search-verdict')).toContainText('completed');
  const history = await (await page.request.get(`${base}/api/objects/${targetId}/history`)).json();
  if (!history.automatic_sightings.some(s => s.search_id === latest.id)) throw Error('Actual sighting missing from Library history.');
  await page.screenshot({ path: path.join(output, 'desktop-published.png'), fullPage: true });
  await page.setViewportSize({ width: 844, height: 390 });
  await page.locator('.search-verdict').scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(output, 'phone-published.png') });
  await page.reload();
  await page.getByRole('button', { name: 'Library', exact: true }).click();
  const objects = await (await page.request.get(base + '/api/objects')).json();
  const target = objects.find(o => o.id === targetId);
  await page.locator('.object-card').filter({ hasText: target.name }).click();
  await expect(page.getByRole('heading', { name: 'Automatic model sightings', exact: true })).toBeVisible();
  await page.getByRole('region', { name: 'Automatic model sightings', exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(output, 'phone-library-history.png'), fullPage: true });
  const room = await (await page.request.get(base + '/api/room')).json();
  if (!room.timeline.some(r => r.source === 'model_inference' && r.object_id === targetId)) throw Error('Actual model evidence missing from Room timeline.');
  const queried = await page.request.post(base + '/api/room/queries', { data: { kind: 'last_seen', object_id: targetId } });
  if (!queried.ok()) throw Error('Actual history query failed.');
  const answer = await queried.json();
  if (answer.status !== 'supported' || !answer.evidence.some(r => r.source === 'model_inference')) throw Error('Answer is not supported by model sighting.');
  if (errors.length) throw Error(errors.join('\n'));
  await fs.writeFile(path.join(output, 'history-result.json'), JSON.stringify({ history, room, answer, browserErrors: errors }, null, 2));
  console.log(JSON.stringify({ status: latest.status, search_id: latest.id, qualified: true, actual_history_pass: true, evidence_mode: existingId ? 'recorded_sighting_ui_validation_no_new_inference' : 'fresh_actual_model_search' }));
} finally { await browser.close(); }
