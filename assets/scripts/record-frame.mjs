// Composites final-with-captions.mp4 INTO the framed terminal layout.
// Approach: capture frame.html?bg=1 as a single PNG (terminal chrome + desk),
//           then ffmpeg overlays the actual video at exact rectangle position.
// (Headless Chrome throttled embedded video playback — this avoids it entirely.)
//
// Output: videos/final-framed.mp4

import { chromium } from 'playwright';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, unlinkSync } from 'node:fs';
import { join } from 'node:path';

const W = 1920, H = 1080;
const URL = 'http://localhost:8765/frame.html?bg=1';
const OUT_DIR = './videos';
const BG_PNG = './videos/frame-bg.png';
const SOURCE = './videos/final-with-captions.mp4';
const FINAL = './videos/final-framed.mp4';

// Terminal geometry — MUST match frame.html
// Inset video by 32px horizontally + 22px vertically so the transparent terminal
// borders bleed into the backdrop (instead of being covered by sharp video edges)
const TERM_W = 1400, TERM_H = 825;
const TITLEBAR = 38;
const INSET_X = 32, INSET_Y = 22;
const OVERLAY_W = TERM_W - INSET_X * 2;             // 1336
const OVERLAY_H = TERM_H - TITLEBAR - INSET_Y * 2;  // 743 (~16:9 of 1336)
const OVERLAY_X = (W - TERM_W) / 2 + INSET_X;       // 292
const OVERLAY_Y = (H - TERM_H) / 2 + TITLEBAR + INSET_Y;  // 187.5

if (!existsSync(SOURCE)) { console.error(`Missing ${SOURCE}`); process.exit(1); }
if (!existsSync(OUT_DIR)) mkdirSync(OUT_DIR, { recursive: true });
for (const p of [BG_PNG, FINAL]) if (existsSync(p)) unlinkSync(p);

console.log('[1/2] Capturing static background via Playwright...');
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
const page = await context.newPage();
await page.goto(`${URL}&t=${Date.now()}`, { waitUntil: 'networkidle' });
await page.waitForTimeout(800);  // give layout/glow time to settle
await page.screenshot({ path: BG_PNG, type: 'png' });
await browser.close();
console.log(`  -> ${BG_PNG}`);

console.log('[2/2] ffmpeg overlay (deterministic, no throttling)');
const res = spawnSync('ffmpeg', [
  '-y', '-hide_banner', '-loglevel', 'error',
  '-loop', '1', '-framerate', '30', '-i', BG_PNG,
  '-i', SOURCE,
  '-filter_complex',
  `[1:v]scale=${OVERLAY_W}:${OVERLAY_H}[scaled];` +
  `[0:v][scaled]overlay=x=${Math.round(OVERLAY_X)}:y=${Math.round(OVERLAY_Y)}:format=auto[v]`,
  '-map', '[v]', '-map', '1:a',
  '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-pix_fmt', 'yuv420p',
  '-c:a', 'aac', '-b:a', '192k',
  '-movflags', '+faststart',
  '-shortest',
  FINAL,
], { stdio: 'inherit' });

if (res.status !== 0) { console.error('ffmpeg failed.'); process.exit(1); }
console.log(`Done → ${FINAL}`);
