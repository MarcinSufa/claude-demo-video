"""record-browser.mjs glow validation against a live page: a target that appears
after page load must still record, a target matching two nodes must stop the
recording. Needs node, Playwright and ffmpeg; skipped otherwise."""
import http.server
import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts")
NODE = shutil.which("node")


def _playwright_available():
    if not NODE or not shutil.which("ffmpeg"):
        return False
    probe = subprocess.run([NODE, "-e", "require.resolve('playwright')"], cwd=SCRIPTS,
                           capture_output=True)
    return probe.returncode == 0


LATE = """<!doctype html><html><body style="background:#100c0a">
<script>setTimeout(() => { const b = document.createElement('button');
b.className = 'late'; b.textContent = 'late'; document.body.appendChild(b); }, 800);</script>
</body></html>"""
TWO = """<!doctype html><html><body style="background:#100c0a">
<button class="target">one</button><button class="target">two</button></body></html>"""


@unittest.skipUnless(_playwright_available(), "needs node + playwright + ffmpeg")
class GlowValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        for name, html in (("late.html", LATE), ("two.html", TWO)):
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

    def _record(self, page, selector):
        scene = {"url": f"http://127.0.0.1:{self.port}/{page}",
                 "output": os.path.join(self.tmp.name, page + ".mp4"),
                 "viewport": {"width": 320, "height": 180}, "settle_ms": 0, "tail_ms": 0,
                 "actions": [{"click": selector, "glow": True, "label": "press"}]}
        path = os.path.join(self.tmp.name, page + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(scene, f)
        return subprocess.run([NODE, os.path.join(SCRIPTS, "record-browser.mjs"), path],
                              capture_output=True, text=True)

    def test_target_that_appears_after_load_records(self):
        res = self._record("late.html", ".late")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_two_matches_stop_the_recording(self):
        res = self._record("two.html", ".target")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn(".target", res.stderr)
        self.assertIn("matches 2", res.stderr)
        self.assertIn("press", res.stderr)


if __name__ == "__main__":
    unittest.main()
