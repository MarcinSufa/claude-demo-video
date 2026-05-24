// make-auth.mjs — P2-1: log in ONCE, save the session for authed scenes.
//
// Each browser_capture scene runs in its own Playwright context, so authenticated
// apps would otherwise need to log in inside every scene. This runs the brand.yaml
// `auth:` flow once and writes Playwright storageState to auth.json; record-browser.mjs
// then loads it for any scene with `auth: true` — so those scenes start already
// logged in, with no login UI on camera.
//
// Reads config.json's `auth` block:
//   auth:
//     login_url: "http://localhost:3000/login"
//     actions: [ { fill: { selector: "#email", text: "..." } },
//                { fill: { selector: "#password", text: "..." } },
//                { click: "button[type=submit]" } ]
//     wait_for: "**/dashboard"     # URL glob OR a selector to confirm login landed
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

// Confirm the login landed. wait_for can be a URL glob ("**/dashboard") or a selector.
let loginOk = true;
if (auth.wait_for) {
  const wf = auth.wait_for;
  const isUrl = wf.includes('/') || wf.includes('*');
  try {
    if (isUrl) await page.waitForURL(wf, { timeout: 20000 });
    else await page.waitForSelector(wf, { timeout: 20000 });
  } catch (e) {
    loginOk = false;
    console.error(`  login wait_for "${wf}" not satisfied: ${e.message}`);
  }
} else {
  await page.waitForTimeout(1500);
}

// Fail LOUDLY on incomplete login — don't silently save a useless session that would
// make authed scenes record a login screen. Saves a screenshot so you can see why
// (wrong credentials, a selector that missed, an extra login step, etc.).
if (!loginOk) {
  await page.screenshot({ path: 'auth-fail.png' }).catch(() => {});
  const snippet = await page
    .evaluate(() => (document.body?.innerText || '').replace(/\s+/g, ' ').slice(0, 160))
    .catch(() => '');
  console.error('\n[X] LOGIN DID NOT COMPLETE — not saving auth.json.');
  console.error(`    final URL: ${page.url()}`);
  if (snippet) console.error(`    page says: "${snippet}"`);
  console.error('    Check the auth.actions selectors + credentials (and any extra login step).');
  console.error('    Screenshot: .build/auth-fail.png\n');
  await browser.close();
  process.exit(1);
}

await context.storageState({ path: 'auth.json' });
await browser.close();
console.log('  saved login session -> auth.json');
