// make-auth.mjs — P2-1: establish a login session ONCE, save it for authed scenes.
//
// Each browser_capture scene runs in its own Playwright context, so authenticated
// apps would otherwise need to log in inside every scene. This writes Playwright
// storageState to auth.json; record-browser.mjs loads it for any scene with
// `auth: true` — so those scenes start already logged in, no login UI on camera.
//
// Two modes (config.json `auth.mode`):
//   scripted (default): replay `auth.actions` headlessly with credentials.
//     auth:
//       login_url: "http://localhost:3000/login"
//       actions: [ { fill: { selector: "#email", text: "..." } },
//                  { fill: { selector: "#password", text: "..." } },
//                  { click: "button[type=submit]" } ]
//       wait_for: "**/dashboard"      # URL glob OR a selector confirming login landed
//
//   manual: open a HEADED browser and let a human log in (SSO / OIDC / 2FA — anything
//     that can't be scripted, and no credentials in any file). Reuses an existing
//     auth.json if present (delete it to log in again).
//     auth:
//       mode: manual
//       login_url: "https://app.example.com/"
//       wait_for: 'role=link[name="Dashboard"]'   # a post-login signal (selector preferred)
//
// No auth block → no-op (exits 0).

import { chromium } from 'playwright';
import { readFileSync, existsSync } from 'node:fs';

const cfg = existsSync('config.json') ? JSON.parse(readFileSync('config.json', 'utf-8')) : {};
const auth = cfg.auth || {};

if (!auth.login_url) {
  console.log('  no auth block — skipping login (auth.json not created)');
  process.exit(0);
}

const mode = auth.mode || 'scripted';
const isUrlMatcher = (wf) => wf.includes('/') || wf.includes('*');

async function confirmLogin(page, wf, timeout) {
  if (!wf) { await page.waitForTimeout(1500); return true; }
  try {
    if (isUrlMatcher(wf)) await page.waitForURL(wf, { timeout });
    else await page.waitForSelector(wf, { state: 'visible', timeout });
    await page.waitForLoadState('networkidle').catch(() => {});
    return true;
  } catch (e) {
    console.error(`  login wait_for "${wf}" not satisfied: ${e.message}`);
    return false;
  }
}

async function failLoud(page, browser, hint) {
  await page.screenshot({ path: 'auth-fail.png' }).catch(() => {});
  const snippet = await page
    .evaluate(() => (document.body?.innerText || '').replace(/\s+/g, ' ').slice(0, 160))
    .catch(() => '');
  console.error('\n[X] LOGIN DID NOT COMPLETE — not saving auth.json.');
  console.error(`    final URL: ${page.url()}`);
  if (snippet) console.error(`    page says: "${snippet}"`);
  console.error(`    ${hint}`);
  console.error('    Screenshot: .build/auth-fail.png\n');
  await browser.close();
  process.exit(1);
}

// ── manual mode ─────────────────────────────────────────────────────────
if (mode === 'manual') {
  if (existsSync('auth.json')) {
    console.log('  manual auth: reusing existing auth.json (delete it to log in again)');
    process.exit(0);
  }
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  console.log('\n  >>> A browser window is opening — LOG IN to the app there.');
  console.log('  >>> When the app finishes loading, leave it; the session saves automatically.\n');
  await page.goto(auth.login_url).catch(e => console.warn('  nav warning:', e.message));
  await page.waitForTimeout(1500);
  const ok = await confirmLogin(page, auth.wait_for, 270000);  // ~4.5 min for a human
  if (!ok) await failLoud(page, browser, 'Set auth.wait_for to a post-login selector (e.g. a nav link).');
  await page.waitForTimeout(1200);
  await context.storageState({ path: 'auth.json' });
  await browser.close();
  console.log('  saved login session -> auth.json');
  process.exit(0);
}

// ── scripted mode (default) ─────────────────────────────────────────────
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
const page = await context.newPage();

console.log(`  logging in at ${auth.login_url}`);
await page.goto(auth.login_url, { waitUntil: 'networkidle' }).catch(e => console.warn('  nav warning:', e.message));

for (const action of auth.actions ?? []) {
  try {
    if (action.fill) { await page.fill(action.fill.selector, action.fill.text); }
    else if (action.type) { await page.keyboard.type(action.type, { delay: 40 }); }
    else if (action.click) { await page.click(action.click); }
    else if (action.press) { await page.keyboard.press(action.press); }
    else if (action.check) { await page.check(action.check); }
    else if (action.wait) { await page.waitForTimeout(action.wait * 1000); }
    await page.waitForTimeout(200);
  } catch (e) {
    console.warn(`  auth action failed (${JSON.stringify(action)}): ${e.message}`);
  }
}

// Fail LOUDLY on incomplete login — don't silently save a useless session that would
// make authed scenes record a login screen.
if (!(await confirmLogin(page, auth.wait_for, 20000))) {
  await failLoud(page, browser, 'Check the auth.actions selectors + credentials (and any extra login step).');
}

await context.storageState({ path: 'auth.json' });
await browser.close();
console.log('  saved login session -> auth.json');
