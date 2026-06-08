// record-browser.mjs — capture a REAL app/UI as a demo scene.
//
// Drives a real URL with Playwright (click/type/scroll/hover), records video,
// injects a smooth fake cursor (headless Chrome has none), trims the pre-paint
// white frame, and emits an mp4 ready for assemble.sh.
//
// Usage:  node record-browser.mjs <scene.json>
//
// scene.json shape:
// {
//   "url": "http://localhost:3000/dashboard",
//   "output": "videos/scene_dashboard.mp4",
//   "viewport": { "width": 1920, "height": 1080 },
//   "deviceScaleFactor": 1,
//   "cursor": true,
//   "warmup": true,               // P2-2: warm the route first (non-recording pass)
//   "bg": "#0a0705",              // P2-3: paint this before first paint (anti white-flash)
//   "settle_ms": 1200,            // wait after load before acting
//   "tail_ms": 1500,              // hold at end
//   "clip": ".schedules-dialog",  // SHOW THE PART YOU'RE CHANGING: crop+zoom the output
//                                 //   to this element so the viewer sees the control the
//                                 //   change touches, not the whole page. Measured at the
//                                 //   END of the scene (so a dialog opened mid-scene is on
//                                 //   screen). Also accepts { "selector": "…", "pad": 40 }
//                                 //   or an explicit { "x":.., "y":.., "width":.., "height":.. }.
//   "actions": [
//     { "hover": ".sidebar-item" },
//     { "click": "button.new" },
//     { "fill": { "selector": "input[name=title]", "text": "My note" } },
//     { "type": "hello world" },
//     { "press": "Enter" },
//     { "scroll": 500 },
//     { "scroll_into_view": ".load-row" },   // bring an off-screen element into view
//     { "wait": 1.5 }
//   ]
// }

import { chromium } from 'playwright';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, readdirSync, renameSync, unlinkSync, statSync } from 'node:fs';
import { dirname, join, basename } from 'node:path';

const sceneFile = process.argv[2];
if (!sceneFile || !existsSync(sceneFile)) {
  console.error('Usage: node record-browser.mjs <scene.json>');
  process.exit(1);
}
const scene = JSON.parse(readFileSync(sceneFile, 'utf-8'));

const W = scene.viewport?.width ?? 1920;
const H = scene.viewport?.height ?? 1080;
const OUTPUT = scene.output ?? 'videos/scene_browser.mp4';
const OUT_DIR = dirname(OUTPUT);
const VID_DIR = join(OUT_DIR, '.webm-tmp');
const SETTLE = scene.settle_ms ?? 1200;
const TAIL = scene.tail_ms ?? 1500;
const WANT_CURSOR = scene.cursor !== false;
const CLIP = scene.clip ?? null;   // crop+zoom the output to the changed UI region

mkdirSync(OUT_DIR, { recursive: true });
mkdirSync(VID_DIR, { recursive: true });
for (const f of readdirSync(VID_DIR)) unlinkSync(join(VID_DIR, f));

// Fake-cursor init script — a soft dot that follows real mousemove events.
// Playwright's click/hover dispatch mousemove, so the dot tracks interactions.
const CURSOR_JS = `
  (() => {
    const dot = document.createElement('div');
    dot.id = '__demo_cursor';
    dot.style.cssText = [
      'position:fixed','top:0','left:0','width:22px','height:22px',
      'margin:-11px 0 0 -11px','border-radius:50%','pointer-events:none',
      'z-index:2147483647','background:rgba(255,255,255,0.9)',
      'box-shadow:0 0 0 2px rgba(0,0,0,0.25), 0 2px 8px rgba(0,0,0,0.35)',
      'transition:transform 0.08s ease-out','transform:translate(-100px,-100px)'
    ].join(';');
    const click = document.createElement('div');
    click.style.cssText = 'position:fixed;top:0;left:0;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;pointer-events:none;z-index:2147483646;background:transparent;';
    document.documentElement.appendChild(dot);
    document.documentElement.appendChild(click);
    let x = -100, y = -100;
    window.addEventListener('mousemove', e => { x = e.clientX; y = e.clientY; dot.style.transform = 'translate(' + x + 'px,' + y + 'px)'; }, true);
    window.addEventListener('mousedown', () => {
      click.style.transition='none'; click.style.transform='translate('+x+'px,'+y+'px) scale(0.4)';
      click.style.background='rgba(255,255,255,0.35)';
      requestAnimationFrame(()=>{ click.style.transition='transform 0.4s ease-out, background 0.4s ease-out'; click.style.transform='translate('+x+'px,'+y+'px) scale(2.2)'; click.style.background='rgba(255,255,255,0)'; });
    }, true);
  })();
`;

// Move the mouse smoothly to an element's center before interacting (so the
// fake cursor glides instead of teleporting).
async function glideTo(page, selector) {
  const el = await page.waitForSelector(selector, { timeout: 8000 });
  const box = await el.boundingBox();
  if (!box) return;
  const tx = box.x + box.width / 2;
  const ty = box.y + box.height / 2;
  await page.mouse.move(tx, ty, { steps: 25 });
  await page.waitForTimeout(150);
  return { tx, ty };
}

console.log(`Launching Chromium for ${scene.url}`);
const browser = await chromium.launch({ headless: true });

// P2-1: reuse the saved login session for authed scenes (make-auth.mjs wrote auth.json).
const storageState = (scene.auth && existsSync('auth.json')) ? 'auth.json' : undefined;
if (scene.auth && !storageState) {
  console.warn('  scene wants auth but auth.json is missing — recording unauthenticated');
}

// P2-2: warm the route FIRST in a throwaway (non-recording) context. Dev servers
// (Next etc.) compile routes on first hit, so without this the recorded pass can
// catch a "Rendering..." / compile overlay. recordVideo starts at context creation,
// so the warmup MUST be a separate context or its frames land in the tape.
if (scene.warmup) {
  console.log('  warming route (non-recording pass)...');
  const warm = await browser.newContext({ viewport: { width: W, height: H }, storageState });
  const wp = await warm.newPage();
  await wp.goto(scene.url, { waitUntil: 'networkidle' }).catch(() => {});
  await wp.waitForTimeout(500);
  await warm.close();
}

const recStart = Date.now();   // recording starts at context creation
const context = await browser.newContext({
  viewport: { width: W, height: H },
  deviceScaleFactor: scene.deviceScaleFactor ?? 1,
  recordVideo: { dir: VID_DIR, size: { width: W, height: H } },
  storageState,
});
// P2-3: paint the palette bg before first paint so an html_mockup that forgets an
// inline <html> background never records as a white flash.
if (scene.bg) {
  await context.addInitScript((bg) => { document.documentElement.style.background = bg; }, scene.bg);
}
if (WANT_CURSOR) await context.addInitScript(CURSOR_JS);

const page = await context.newPage();
let navOk = true;
await page.goto(scene.url, { waitUntil: 'networkidle' }).catch(e => {
  navOk = false;   // timeout/error → readyAt is unreliable (≈ the goto timeout)
  console.warn('navigation warning:', e.message);
});
// networkidle ≈ the app finished its boot/auth splash and rendered. Remember how long
// that took (only meaningful when nav succeeded) so we can trim most of the splash.
const readyAt = (Date.now() - recStart) / 1000;
await page.waitForTimeout(SETTLE);

for (const action of scene.actions ?? []) {
  try {
    if (action.hover) { await glideTo(page, action.hover); await page.hover(action.hover); }
    else if (action.click) { await glideTo(page, action.click); await page.click(action.click); }
    else if (action.fill) { await glideTo(page, action.fill.selector); await page.fill(action.fill.selector, action.fill.text); }
    else if (action.type) { await page.keyboard.type(action.type, { delay: 55 }); }
    else if (action.press) { await page.keyboard.press(action.press); }
    else if (typeof action.scroll === 'number') { await page.mouse.wheel(0, action.scroll); }
    else if (action.scroll_into_view) { await page.locator(action.scroll_into_view).first().scrollIntoViewIfNeeded().catch(() => {}); }
    else if (action.wait) { await page.waitForTimeout(action.wait * 1000); }
    await page.waitForTimeout(250);
  } catch (e) {
    console.warn(`action failed (${JSON.stringify(action)}): ${e.message}`);
  }
}

// `clip` — resolve the crop-to-region NOW (after actions), so the element you're
// changing (e.g. a dialog opened mid-scene) is on screen when we measure it.
let cropFilter = '';
if (CLIP) {
  const even = (n) => Math.max(2, Math.round(n / 2) * 2);
  let rect = null;
  if (typeof CLIP === 'string' || CLIP.selector) {
    const sel = typeof CLIP === 'string' ? CLIP : CLIP.selector;
    const pad = (typeof CLIP === 'object' && CLIP.pad != null) ? CLIP.pad : 32;
    const box = await page.locator(sel).first().boundingBox().catch(() => null);
    if (box) rect = { x: box.x - pad, y: box.y - pad, width: box.width + pad * 2, height: box.height + pad * 2 };
    else console.warn(`  clip selector "${sel}" not found — recording the full frame`);
  } else if (CLIP.width && CLIP.height) {
    rect = { x: CLIP.x ?? 0, y: CLIP.y ?? 0, width: CLIP.width, height: CLIP.height };
  }
  if (rect) {
    const cx = Math.max(0, Math.min(W - 2, Math.round(rect.x)));
    const cy = Math.max(0, Math.min(H - 2, Math.round(rect.y)));
    const cw = even(Math.min(rect.width, W - cx));
    const ch = even(Math.min(rect.height, H - cy));
    // Crop to the region, then upscale back to the scene size so every scene keeps
    // identical dimensions for assemble.sh's crossfade/concat.
    cropFilter = `crop=${cw}:${ch}:${cx}:${cy},scale=${W}:${H}:flags=lanczos`;
    console.log(`  clip -> crop ${cw}x${ch}+${cx}+${cy}, rescaled to ${W}x${H}`);
  }
}

await page.waitForTimeout(TAIL);
await context.close();
await browser.close();

// webm → mp4. Trim the head: 300ms by default (pre-paint white), or `trim_start_ms`
// to skip a slow app boot/auth splash so the loading reads as ~1-2s instead of ~5s.
const webms = readdirSync(VID_DIR).filter(f => f.endsWith('.webm'))
  .map(f => ({ f, m: statSync(join(VID_DIR, f)).mtimeMs })).sort((a, b) => b.m - a.m);
if (!webms.length) { console.error('No video recorded'); process.exit(1); }
const webm = join(VID_DIR, webms[0].f);

// Default: auto-trim to ~1s before the app was ready (skips a slow boot/auth splash).
// Override with an explicit trim_start_ms. If navigation failed/timed out, readyAt is
// unreliable (≈ the goto timeout), so fall back to a tiny trim and never over-trim.
const KEEP_LOADING_S = 1.0;
const MAX_AUTO_TRIM_S = 12;   // guard: never cut into real content on a slow/timed-out load
let trimStart = 0.3;          // safe default (just the pre-paint frame)
if (scene.trim_start_ms != null) {
  trimStart = scene.trim_start_ms / 1000;
} else if (navOk && Number.isFinite(readyAt) && readyAt > KEEP_LOADING_S) {
  trimStart = Math.min(MAX_AUTO_TRIM_S, readyAt - KEEP_LOADING_S);
}
const readyLabel = (navOk && Number.isFinite(readyAt)) ? `~${readyAt.toFixed(1)}s` : '(nav incomplete)';
console.log(`  ready ${readyLabel} · trimming first ${trimStart.toFixed(1)}s`);
const res = spawnSync('ffmpeg', [
  '-y', '-hide_banner', '-loglevel', 'error',
  '-ss', String(trimStart), '-i', webm,
  ...(cropFilter ? ['-vf', cropFilter] : []),
  '-c:v', 'libx264', '-preset', 'slow', '-crf', '18',
  '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
  OUTPUT,
], { stdio: 'inherit' });
if (res.status !== 0) { console.error('ffmpeg failed'); process.exit(1); }
console.log(`Done -> ${OUTPUT}`);
