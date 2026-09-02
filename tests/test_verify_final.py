"""Tests for verify-final.py: the post-mux checks that used to surface only
after watching the render."""
import contextlib
import importlib.util
import io
import os
import shutil
import subprocess
import tempfile
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "assets", "scripts"))

_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts", "verify-final.py")
_spec = importlib.util.spec_from_file_location("verify_final", _PATH)
vf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vf)

HAVE_FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")


class PureChecks(unittest.TestCase):
    def test_duration_within_half_second(self):
        self.assertIsNone(vf.duration_problem(50.0, 50.4))
        self.assertIn("duration", vf.duration_problem(50.0, 51.0))

    def test_parse_yavg_lines(self):
        text = ("frame:0 pts:0 pts_time:0\nlavfi.signalstats.YAVG=12.5\n"
                "frame:1 pts:1 pts_time:0.1\nlavfi.signalstats.YAVG=235.0\n")
        self.assertEqual(vf.parse_yavg(text), [(0.0, 12.5), (0.1, 235.0)])

    def test_flash_problem_names_time_and_value(self):
        self.assertIsNone(vf.flash_problem([(0.0, 12.5), (0.1, 90.0)], 120))
        msg = vf.flash_problem([(0.0, 12.5), (3.0, 235.0)], 120)
        self.assertIn("3.0", msg)
        self.assertIn("235", msg)

    def test_flash_is_relative_to_the_file_median(self):
        light_ui = [(t / 10, 200.0) for t in range(20)]
        self.assertIsNone(vf.flash_problem(light_ui, 120))
        light_ui_with_flash = light_ui + [(2.0, 250.0)]
        self.assertIsNone(vf.flash_problem(light_ui_with_flash, 120))
        self.assertIsNotNone(vf.flash_problem(light_ui_with_flash, 120, margin=40))
        dark = [(t / 10, 20.0) for t in range(20)] + [(2.0, 150.0)]
        self.assertIsNotNone(vf.flash_problem(dark, 120))
        self.assertIsNone(vf.flash_problem([], 120))

    def test_audio_problem(self):
        self.assertIn("audio", vf.audio_problem(has_audio=False, tail_db=None, narration_in_tail=False))
        self.assertIsNone(vf.audio_problem(True, tail_db=-60.0, narration_in_tail=False))
        self.assertIn("silent", vf.audio_problem(True, tail_db=-80.0, narration_in_tail=True))
        self.assertIsNone(vf.audio_problem(True, tail_db=-20.0, narration_in_tail=True))

    def test_caption_table_pairs_scenes_with_cues(self):
        srt = "1\n00:00:00,000 --> 00:00:02,000\nHello\n\n2\n00:00:05,000 --> 00:00:07,000\nWorld\n"
        scenes = [{"name": "intro", "type": "title", "duration": 4},
                  {"name": "demo", "type": "html_mockup", "duration": 4}]
        rows = vf.caption_rows(scenes, vf.parse_srt(srt), speedup=1.0, crossfade=0.0)
        self.assertEqual(rows[0][0], "intro")
        self.assertIn("Hello", rows[0][1])
        self.assertIn("World", rows[1][1])


@unittest.skipUnless(HAVE_FFMPEG, "needs ffmpeg")
class RealFiles(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _clip(self, name, extra_vf=None, audio=True):
        out = os.path.join(self.dir, name)
        cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x100c0a:s=64x36:r=10:d=4"]
        if audio:
            cmd += ["-f", "lavfi", "-i", "sine=frequency=220:duration=4", "-c:a", "aac", "-shortest"]
        if extra_vf:
            cmd += ["-vf", extra_vf]
        subprocess.run(cmd + [out], check=True)
        return out

    def _verify(self, clip):
        with contextlib.redirect_stdout(io.StringIO()):
            return vf.main([clip, "--rough", clip])

    def test_dark_clip_passes(self):
        self.assertEqual(self._verify(self._clip("dark.mp4")), 0)

    def test_white_flash_fails(self):
        clip = self._clip("flash.mp4", "drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='between(t,2,2.5)'")
        self.assertNotEqual(self._verify(clip), 0)

    def test_missing_audio_fails(self):
        self.assertNotEqual(self._verify(self._clip("mute.mp4", audio=False)), 0)


if __name__ == "__main__":
    unittest.main()
