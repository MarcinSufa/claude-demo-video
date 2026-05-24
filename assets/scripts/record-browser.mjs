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
//   "actions": [
//     { "hover": ".sidebar-item" },
//     { "click": "button.new" },
//     { "fill": { "selector": "input[name=title]", "text": "My note" } },
//     { "type": "hello world" },
//     { "press": "Enter" },
//     { "scroll": 500 },
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
await page.goto(scene.url, { waitUntil: 'networkidle' }).catch(e => {
  console.warn('navigation warning:', e.message);
});
await page.waitForTimeout(SETTLE);

for (const action of scene.actions ?? []) {
  try {
    if (action.hover) { await glideTo(page, action.hover); await page.hover(action.hover); }
    else if (action.click) { await glideTo(page, action.click); await page.click(action.click); }
    else if (action.fill) { await glideTo(page, action.fill.selector); await page.fill(action.fill.selector, action.fill.text); }
    else if (action.type) { await page.keyboard.type(action.type, { delay: 55 }); }
    else if (action.press) { await page.keyboard.press(action.press); }
    else if (typeof action.scroll === 'number') { await page.mouse.wheel(0, action.scroll); }
    else if (action.wait) { await page.waitForTimeout(action.wait * 1000); }
    await page.waitForTimeout(250);
  } catch (e) {
    console.warn(`action failed (${JSON.stringify(action)}): ${e.message}`);
  }
}

await page.waitForTimeout(TAIL);
await context.close();
await browser.close();

// webm → mp4, trim first 300ms (pre-paint white)
const webms = readdirSync(VID_DIR).filter(f => f.endsWith('.webm'))
  .map(f => ({ f, m: statSync(join(VID_DIR, f)).mtimeMs })).sort((a, b) => b.m - a.m);
if (!webms.length) { console.error('No video recorded'); process.exit(1); }
const webm = join(VID_DIR, webms[0].f);

const res = spawnSync('ffmpeg', [
  '-y', '-hide_banner', '-loglevel', 'error',
  '-ss', '0.3', '-i', webm,
  '-c:v', 'libx264', '-preset', 'slow', '-crf', '18',
  '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
  OUTPUT,
], { stdio: 'inherit' });
if (res.status !== 0) { console.error('ffmpeg failed'); process.exit(1); }
console.log(`Done -> ${OUTPUT}`);
