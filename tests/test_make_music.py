"""Tests for make-music.sh: the bed follows the video length in every mode.

Runs the real script against tiny lavfi fixtures, so ffmpeg and bash are
required; the class is skipped when either is missing. No network: the library
case points at an unreachable manifest and must fall back to procedural.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts")
BASH = shutil.which("bash")
HAVE_TOOLS = BASH and all(shutil.which(t) for t in ("ffmpeg", "ffprobe"))

UNREACHABLE = """calm:
  primary:
    url: "http://127.0.0.1:1/unreachable.mp3"
    sha256: "0000000000000000000000000000000000000000000000000000000000000000"
    licence: CC0
    source_page: "fixture"
    title: "Unavailable"
    artist: "fixture"
    duration_s: 1
"""


def _duration(path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path])
    return float(out.decode().strip())


@unittest.skipUnless(HAVE_TOOLS, "needs ffmpeg, ffprobe and bash")
class MakeMusic(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.build = os.path.join(self._tmp.name, ".build")
        os.makedirs(os.path.join(self.build, "videos"))
        shutil.copy(os.path.join(SCRIPTS, "make-music.sh"), self.build)
        shutil.copy(os.path.join(SCRIPTS, "fetch-music.py"), self.build)
        shutil.copy(os.path.join(SCRIPTS, "timing_util.py"), self.build)

    def tearDown(self):
        self._tmp.cleanup()

    def _video(self, seconds):
        subprocess.run([
            "ffmpeg", "-y", "-v", "error", "-f", "lavfi",
            "-i", f"color=c=black:s=64x36:r=5:d={seconds}", "-an",
            os.path.join(self.build, "videos", "final-rough.mp4")], check=True)

    def _run(self, music, env=None, subs=None):
        with open(os.path.join(self.build, "config.json"), "w", encoding="utf-8") as f:
            json.dump({"music": music, "subs": subs or {}}, f)
        full_env = dict(os.environ, DEMO_CONFIG="config.json",
                        DEMO_MUSIC_CACHE=os.path.join(self._tmp.name, "cache"),
                        PATH=os.pathsep.join([os.path.dirname(sys.executable), os.environ["PATH"]]))
        full_env.update(env or {})
        return subprocess.run([BASH, "make-music.sh"], cwd=self.build, env=full_env,
                              capture_output=True, text=True)

    def _music_duration(self):
        return _duration(os.path.join(self.build, "music.mp3"))

    def test_procedural_bed_matches_video_length(self):
        self._video(12)
        res = self._run({"mode": "procedural", "style": "tech"})
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertAlmostEqual(self._music_duration(), 12, delta=1)

    def test_short_file_loops_to_video_length(self):
        self._video(12)
        subprocess.run([
            "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-c:a", "libmp3lame", os.path.join(self.build, "short.mp3")], check=True)
        res = self._run({"mode": "file", "file": "short.mp3"})
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertAlmostEqual(self._music_duration(), 12, delta=1)

    def test_library_fetch_failure_warns_and_falls_back(self):
        self._video(8)
        manifest = os.path.join(self._tmp.name, "unreachable.yaml")
        with open(manifest, "w", encoding="utf-8") as f:
            f.write(UNREACHABLE)
        res = self._run({"mode": "library", "style": "calm"}, {"DEMO_MUSIC_MANIFEST": manifest})
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("WARNING", res.stdout + res.stderr)
        self.assertAlmostEqual(self._music_duration(), 8, delta=1)

    def test_missing_video_uses_predicted_length(self):
        with open(os.path.join(self.build, "scene-plan.json"), "w", encoding="utf-8") as f:
            json.dump({"scenes": [{"id": "a", "type": "title", "duration": 6},
                                  {"id": "b", "type": "title", "duration": 6}]}, f)
        res = self._run({"mode": "procedural", "style": "bugfix"},
                        subs={"speedup": 1.0, "crossfade": 0.6})
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertAlmostEqual(self._music_duration(), 12 - 0.6, delta=1)

    def test_missing_file_still_hard_fails(self):
        self._video(5)
        res = self._run({"mode": "file", "file": "nope.mp3"})
        self.assertNotEqual(res.returncode, 0)


if __name__ == "__main__":
    unittest.main()
