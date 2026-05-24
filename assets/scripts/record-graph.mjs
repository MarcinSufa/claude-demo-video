// Records graph.html as a 15s 1280x720 video using Playwright.
// Output: ./videos/graph.webm  →  converted to graph.mp4 via ffmpeg.
//
// Setup (once):
//   cd /c/tmp/exovault-demo
//   npm init -y
//   npm install playwright
//   npx playwright install chromium
//
// Run:
//   1) python -m http.server 8765   (in another terminal, in this folder)
//   2) node record-graph.mjs

import { chromium } from 'playwright';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readdirSync, renameSync, unlinkSync, statSync } from 'node:fs';
import { join } from 'node:path';

const W = 1280, H = 720;
const DURATION_MS = 15000;
const URL = 'http://localhost:8765/graph.html';
const OUT_DIR = './videos';

if (!existsSync(OUT_DIR)) mkdirSync(OUT_DIR, { recursive: true });

// Clean stale outputs so we don't accidentally pick endcards.webm or another stale file
for (const stale of ['graph.webm', 'graph.mp4']) {
  const p = join(OUT_DIR, stale);
  if (existsSync(p)) unlinkSync(p);
}

console.log('Launching Chromium...');
const browser = await chromium.launch({
  headless: true,
  args: ['--disable-web-security', '--disable-blink-features=AutomationControlled'],
});
const context = await browser.newContext({
  viewport: { width: W, height: H },
  deviceScaleFactor: 2, // crisp 2x rendering
  recordVideo: { dir: OUT_DIR, size: { width: W, height: H } },
});
const page = await context.newPage();

console.log(`Navigating to ${URL}`);
await page.goto(URL, { waitUntil: 'networkidle' });

console.log(`Recording ${DURATION_MS}ms...`);
await page.waitForTimeout(DURATION_MS);

console.log('Stopping recording...');
await context.close();
await browser.close();

// Pick most recently created .webm (excluding any already-named fixed artifacts)
const files = readdirSync(OUT_DIR)
  .filter(f => f.endsWith('.webm') && !['graph.webm', 'endcards.webm', 'frame.webm'].includes(f))
  .map(f => ({ f, mtime: statSync(join(OUT_DIR, f)).mtimeMs }))
  .sort((a, b) => b.mtime - a.mtime);
if (!files.length) {
  console.error('No video produced — Playwright recording failed.');
  process.exit(1);
}
const src = join(OUT_DIR, files[0].f);
const webm = join(OUT_DIR, 'graph.webm');
renameSync(src, webm);
console.log(`WebM saved → ${webm}`);

// Convert to MP4 — trim first 500ms to drop Playwright's white-blank pre-CSS frames
console.log('Converting to MP4 with ffmpeg (trim white-blank intro)...');
const mp4 = join(OUT_DIR, 'graph.mp4');
const res = spawnSync('ffmpeg', [
  '-y',
  '-ss', '0.5',
  '-i', webm,
  '-c:v', 'libx264',
  '-preset', 'slow',
  '-crf', '18',
  '-pix_fmt', 'yuv420p',
  '-movflags', '+faststart',
  mp4,
], { stdio: 'inherit' });

if (res.status !== 0) {
  console.error('ffmpeg failed — keep the .webm and convert manually.');
  process.exit(1);
}
console.log(`Done → ${mp4}`);
