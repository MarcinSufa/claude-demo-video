"""Tests for chromium_launch.mjs: DEMO_CHROMIUM_PATH, then
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH, override Playwright's pinned browser build.
Runs through node; skipped when node is missing.
"""
import json
import pathlib
import shutil
import subprocess
import sys
import unittest

NODE = shutil.which("node")
SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "assets" / "scripts"
MODULE = SCRIPTS / "chromium_launch.mjs"
REAL_FILE = sys.executable          # any file that exists


def _launch_options(options, env):
    script = (
        f"import({json.dumps(MODULE.as_uri())}).then(m => {{"
        f" try {{ console.log(JSON.stringify(m.launchOptions({json.dumps(options)}, {json.dumps(env)}))); }}"
        f" catch (e) {{ console.log(JSON.stringify({{error: e.message}})); }} }})")
    out = subprocess.check_output([NODE, "--input-type=module", "-e", script], text=True)
    return json.loads(out)


@unittest.skipUnless(NODE, "needs node")
class LaunchOptions(unittest.TestCase):
    def test_no_override_leaves_options_alone(self):
        self.assertEqual(_launch_options({"headless": True}, {}), {"headless": True})

    def test_demo_path_wins(self):
        env = {"DEMO_CHROMIUM_PATH": REAL_FILE, "PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH": "/nope"}
        self.assertEqual(_launch_options({"headless": True}, env),
                         {"headless": True, "executablePath": REAL_FILE})

    def test_playwright_var_is_the_fallback(self):
        env = {"PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH": REAL_FILE}
        self.assertEqual(_launch_options({}, env)["executablePath"], REAL_FILE)

    def test_missing_file_names_the_variable(self):
        res = _launch_options({}, {"DEMO_CHROMIUM_PATH": "/no/such/chrome"})
        self.assertIn("DEMO_CHROMIUM_PATH", res["error"])
        self.assertIn("/no/such/chrome", res["error"])


class EveryLaunchUsesTheHelper(unittest.TestCase):
    def test_no_bare_chromium_launch(self):
        bare = []
        for path in sorted(SCRIPTS.glob("*.mjs")):
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "chromium.launch(" in line and "launchOptions(" not in line \
                        and not line.lstrip().startswith("//"):
                    bare.append(f"{path.name}:{n}: {line.strip()}")
        self.assertEqual(bare, [])


if __name__ == "__main__":
    unittest.main()
