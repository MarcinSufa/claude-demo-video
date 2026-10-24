"""Paint keepalive and blank-white retry against a local static HTTP page."""
import http.server
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts")
NODE = shutil.which("node")


def _playwright_available():
    if not NODE or not shutil.which("ffmpeg"):
        return False
    probe = subprocess.run([NODE, "-e", "require.resolve('playwright')"], cwd=SCRIPTS,
                           capture_output=True)
    return probe.returncode == 0


DARK = """<!doctype html><html style="background:#0a0705"><body><p>static page</p></body></html>"""
WHITE = """<!doctype html><html style="background:#ffffff"><body>white page</body></html>"""


@unittest.skipUnless(_playwright_available(), "needs node + playwright + ffmpeg")
class RecordBrowserPaint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        for name, html in (("dark.html", DARK), ("white.html", WHITE)):
            with open(os.path.join(cls.tmp.name, name), "w", encoding="utf-8") as f:
                f.write(html)
        handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(
            *a, directory=cls.tmp.name, **k)
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.tmp.cleanup()

    def _record(self, page, settle=800, tail=800):
        output = os.path.join(self.tmp.name, page + ".mp4")
        scene = {"url": f"http://127.0.0.1:{self.port}/{page}", "output": output,
                 "viewport": {"width": 320, "height": 180}, "bg": "#0a0705",
                 "cursor": False, "settle_ms": settle, "tail_ms": tail, "actions": []}
        scene_file = os.path.join(self.tmp.name, page + ".json")
        with open(scene_file, "w", encoding="utf-8") as f:
            json.dump(scene, f)
        result = subprocess.run([NODE, os.path.join(SCRIPTS, "record-browser.mjs"), scene_file],
                                capture_output=True, text=True)
        return result, output

    def _first_yavg(self, video):
        result = subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", video,
            "-vf", "select=eq(n\\,0),signalstats,metadata=print:file=-",
            "-frames:v", "1", "-f", "null", "-",
        ], capture_output=True, text=True)
        match = re.search(r"lavfi\.signalstats\.YAVG=([\d.]+)", result.stdout + result.stderr)
        self.assertIsNotNone(match, result.stdout + result.stderr)
        return float(match.group(1))

    def test_keepalive_keeps_screencast_frames_flowing(self):
        script = f'''\
import {{ chromium }} from 'playwright';
import {{ launchOptions }} from {json.dumps(Path(SCRIPTS, "chromium_launch.mjs").as_uri())};
import {{ KEEPALIVE_JS }} from {json.dumps(Path(SCRIPTS, "paint_guard.mjs").as_uri())};

const browser = await chromium.launch(launchOptions({{ headless: true }}));
try {{
  const context = await browser.newContext();
  await context.addInitScript(KEEPALIVE_JS);
  const page = await context.newPage();
  await page.goto({json.dumps(f"http://127.0.0.1:{self.port}/dark.html")}, {{ waitUntil: 'networkidle' }});
  const cdp = await context.newCDPSession(page);
  let frames = 0;
  cdp.on('Page.screencastFrame', async (event) => {{
    frames += 1;
    await cdp.send('Page.screencastFrameAck', {{ sessionId: event.sessionId }});
  }});
  await cdp.send('Page.startScreencast');
  await new Promise((resolve) => setTimeout(resolve, 1000));
  await cdp.send('Page.stopScreencast');
  console.log(frames);
  await cdp.detach();
}} finally {{
  await browser.close();
}}
'''
        script_path = os.path.join(SCRIPTS, f".keepalive_screencast_{os.getpid()}.mjs")
        try:
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(script)
            result = subprocess.run([NODE, script_path], cwd=SCRIPTS,
                                    capture_output=True, text=True, timeout=30)
        finally:
            if os.path.exists(script_path):
                os.unlink(script_path)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        frame_count = int(result.stdout.strip().splitlines()[-1])
        self.assertGreaterEqual(frame_count, 20, f"only received {frame_count} screencast frames")

    def test_static_dark_page_records_dark_first_frame(self):
        result, output = self._record("dark.html")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertLess(self._first_yavg(output), 60)

    def test_white_page_retries_once_then_fails(self):
        result, output = self._record("white.html", settle=300, tail=300)
        combined = result.stdout + result.stderr
        self.assertEqual(result.returncode, 3, combined)
        self.assertEqual(combined.count("first frame is blank white"), 2, combined)
        self.assertIn("re-recording once", combined)
        self.assertIn("http://127.0.0.1:", combined)
        self.assertIn(output, combined)


if __name__ == "__main__":
    unittest.main()
