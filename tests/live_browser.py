"""Shared prerequisites for live browser tests."""
import functools
import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "assets" / "scripts"
_PROBE = """\
import { launchOptions } from './chromium_launch.mjs';
let chromium;
try {
  ({ chromium } = await import('playwright'));
} catch (error) {
  console.error(`PLAYWRIGHT_IMPORT_ERROR: ${error.message}`);
  process.exit(10);
}
try {
  const browser = await chromium.launch(launchOptions({ headless: true }));
  await browser.close();
} catch (error) {
  console.error(`CHROMIUM_LAUNCH_ERROR:\n${error.message}`);
  process.exit(11);
}
"""


def _launch_failure_reason(output):
    if "CHROMIUM_LAUNCH_ERROR:" in output:
        output = output.split("CHROMIUM_LAUNCH_ERROR:", 1)[1].lstrip()
    if "error while loading shared libraries" in output:
        match = re.search(r"error while loading shared libraries:\s*([^:]+):", output)
        library = match.group(1).strip() if match else "a required library"
        return (f"Chromium failed to launch: missing {library}; see references/troubleshooting.md, "
                "'Chromium: error while loading shared libraries'.")
    first_line = next((line.strip() for line in output.splitlines() if line.strip()),
                      "unknown launch error")
    return f"Chromium failed to launch: {first_line}"


def _probe_live_browser():
    node = shutil.which("node")
    if not node:
        return "missing node"
    if not shutil.which("ffmpeg"):
        return "missing ffmpeg"
    try:
        result = subprocess.run([node, "--input-type=module", "-e", _PROBE], cwd=SCRIPTS,
                                capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return "Chromium failed to launch: probe timed out after 60 seconds"
    output = result.stderr + "\n" + result.stdout
    if result.returncode == 10 and "PLAYWRIGHT_IMPORT_ERROR:" in output:
        return "missing playwright"
    if result.returncode:
        return _launch_failure_reason(output)
    return None


@functools.lru_cache(maxsize=1)
def live_browser_reason():
    """Return why live tests cannot run, or None when their prerequisites work."""
    return _probe_live_browser()


def requires_live_browser(test_case):
    """Skip a live test class unless the environment requires it."""
    reason = live_browser_reason()
    if reason is None:
        return test_case
    if os.environ.get("DEMO_REQUIRE_LIVE") == "1":
        @classmethod
        def setUpClass(cls):
            raise RuntimeError(reason)

        test_case.setUpClass = setUpClass
        return test_case
    return unittest.skip(reason)(test_case)
