// chromium_launch.mjs: Chromium launch options shared by every Playwright script.
//
// Playwright pins one browser build per release (e.g. chromium_headless_shell-1208).
// When the machine has a different build installed, chromium.launch() fails with
// "Executable doesn't exist". Set DEMO_CHROMIUM_PATH (or Playwright's
// PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH) to any installed Chromium/Chrome binary
// instead of patching executablePath into the scripts by hand.
import { existsSync } from 'node:fs';

export const CHROMIUM_ENV_VARS = ['DEMO_CHROMIUM_PATH', 'PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH'];

// { name, path } of the first override that is set, or null.
export function chromiumOverride(env = process.env) {
  for (const name of CHROMIUM_ENV_VARS) {
    if (env[name]) return { name, path: env[name] };
  }
  return null;
}

// Launch options with executablePath added when an override is set. A path that
// does not exist is an error here, so the message names the variable to fix.
export function launchOptions(options = {}, env = process.env, exists = existsSync) {
  const override = chromiumOverride(env);
  if (!override) return options;
  if (!exists(override.path)) {
    throw new Error(`${override.name} points to a missing file: ${override.path}`);
  }
  return { ...options, executablePath: override.path };
}
