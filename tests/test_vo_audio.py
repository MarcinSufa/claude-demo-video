"""Tests for vo_audio.concat_with_pauses — sample-rate-matched VO concat.
Needs ffmpeg/ffprobe; skipped when absent. Run: python -m unittest discover -s tests
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "assets", "scripts"))
import vo_audio  # noqa: E402

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


@unittest.skipUnless(FFMPEG and FFPROBE, "needs ffmpeg + ffprobe")
class ConcatWithPauses(unittest.TestCase):
    def _tone(self, path, sample_rate, duration):
        subprocess.run([
            FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
            "-ar", str(sample_rate), "-ac", "1", "-c:a", "libmp3lame", "-b:a", "128k", path,
        ], check=True)

    def _duration(self, path):
        out = subprocess.check_output([
            FFPROBE, "-v", "error", "-show_entries", "format=duration",
            "-of", "csv=p=0", path])
        return float(out.decode().strip())

    def test_preserves_total_duration_across_sample_rates(self):
        with tempfile.TemporaryDirectory() as d:
            a = str(Path(d, "a.mp3"))
            b = str(Path(d, "b.mp3"))
            self._tone(a, 24000, 0.5)
            self._tone(b, 44100, 0.5)
            out = str(Path(d, "out.mp3"))
            vo_audio.concat_with_pauses([(a, 0.3), (b, 0.0)], out, sample_rate=44100)
            self.assertAlmostEqual(self._duration(out), 0.5 + 0.3 + 0.5, delta=0.1)

    def test_no_pause_still_concatenates(self):
        with tempfile.TemporaryDirectory() as d:
            a = str(Path(d, "a.mp3"))
            self._tone(a, 44100, 0.4)
            out = str(Path(d, "out.mp3"))
            vo_audio.concat_with_pauses([(a, 0.0)], out)
            self.assertAlmostEqual(self._duration(out), 0.4, delta=0.1)


if __name__ == "__main__":
    unittest.main()
