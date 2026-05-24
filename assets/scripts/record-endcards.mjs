// Records endcards.html as a 10s 1920x1080 video using Playwright.
// (Higher res than graph.mp4 because end cards are typography-heavy.)
//
// Run: node record-endcards.mjs   (server must be on :8765)

import { chromium } from 'playwright';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readdirSync, renameSync, unlinkSync, statSync } from 'node:fs';
import { join } from 'node:path';

const W = 1920, H = 1080;
const DURATION_MS = 15000;  // extra hold for "exovault dot co" VO line
const URL = 'http://localhost:8765/endcards.html';
const OUT_DIR = './videos';

if (!existsSync(OUT_DIR)) mkdirSync(OUT_DIR, { recursive: true });

// Clean stale outputs so we don't accidentally pick them up later
for (const stale of ['endcards.webm', 'endcards.mp4']) {
  const p = join(OUT_DIR, stale);
  if (existsSync(p)) unlinkSync(p);
}

console.log('Launching Chromium...');
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: W, height: H },
  deviceScaleFactor: 1,
  recordVideo: { dir: OUT_DIR, size: { width: W, height: H } },
});
const page = await context.newPage();
const URL_BUSTED = `${URL}?t=${Date.now()}`;
console.log(`Navigating to ${URL_BUSTED}`);
await page.goto(URL_BUSTED, { waitUntil: 'networkidle' });
console.log(`Recording ${DURATION_MS}ms...`);
await page.waitForTimeout(DURATION_MS);
console.log('Stopping recording...');
await context.close();
await browser.close();

// Pick most recently created .webm (excluding any already-named graph/endcards artifacts)
const files = readdirSync(OUT_DIR)
  .filter(f => f.endsWith('.webm') && f !== 'graph.webm' && f !== 'endcards.webm')
  .map(f => ({ f, mtime: statSync(join(OUT_DIR, f)).mtimeMs }))
  .sort((a, b) => b.mtime - a.mtime);
if (!files.length) { console.error('No video produced.'); process.exit(1); }
const src = join(OUT_DIR, files[0].f);
const webm = join(OUT_DIR, 'endcards.webm');
renameSync(src, webm);
console.log(`WebM saved → ${webm}`);

console.log('Converting to MP4 with ffmpeg (trim white-blank intro)...');
const mp4 = join(OUT_DIR, 'endcards.mp4');
const res = spawnSync('ffmpeg', [
  '-y',
  '-ss', '0.5',
  '-i', webm,
  '-c:v', 'libx264', '-preset', 'slow', '-crf', '18',
  '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
  mp4,
], { stdio: 'inherit' });

if (res.status !== 0) { console.error('ffmpeg failed.'); process.exit(1); }
console.log(`Done → ${mp4}`);
