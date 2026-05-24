"""Tests for timing_util — the shared VO/video alignment logic (P0-1 + P3-1).

Pure functions only; no ffmpeg/TTS. Run: python -m unittest discover tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "assets", "scripts"))
import timing_util  # noqa: E402


class SpeechEndSeconds(unittest.TestCase):
    def test_returns_end_of_last_spoken_word(self):
        # vo-words.json shape from make-vo.py: top-level "lines", each with line_end
        data = {"lines": [
            {"line_start": 0.5, "line_end": 2.6, "words": []},
            {"line_start": 3.2, "line_end": 5.05, "words": []},
        ]}
        self.assertAlmostEqual(timing_util.speech_end_seconds(data), 5.05, places=3)

    def test_zero_when_no_lines(self):
        self.assertEqual(timing_util.speech_end_seconds({"lines": []}), 0.0)


class CheckAlignment(unittest.TestCase):
    def test_flags_overrun_as_not_ok(self):
        # The Asistel bug: 52.8s of speech in a 42.9s video → punchline cut.
        ok, msg = timing_util.check_alignment(52.8, 42.9)
        self.assertFalse(ok)
        self.assertIn("42.9", msg)
        self.assertIn("52.8", msg)

    def test_ok_when_video_longer_than_speech(self):
        ok, _ = timing_util.check_alignment(40.0, 50.0)
        self.assertTrue(ok)

    def test_within_epsilon_is_ok(self):
        # speech ends 0.10s past video, epsilon 0.15 → tolerated
        ok, _ = timing_util.check_alignment(50.10, 50.0, epsilon=0.15)
        self.assertTrue(ok)

    def test_just_past_epsilon_is_not_ok(self):
        ok, _ = timing_util.check_alignment(50.20, 50.0, epsilon=0.15)
        self.assertFalse(ok)


class PredictVideoSeconds(unittest.TestCase):
    def test_matches_validated_asistel_model(self):
        # Appendix fixture: Sigma raw 51.44s, speedup 1.15, 4 scenes (3 crossfades @0.6)
        # -> 51.44/1.15 - 3*0.6 = 42.93s (matched real build output).
        raws = [12.86, 12.86, 12.86, 12.86]  # sums to 51.44
        v = timing_util.predict_video_seconds(raws, speedup=1.15, crossfade=0.6)
        self.assertAlmostEqual(v, 42.93, places=2)

    def test_no_crossfade_subtracted_for_single_scene(self):
        v = timing_util.predict_video_seconds([10.0], speedup=1.0, crossfade=0.6)
        self.assertAlmostEqual(v, 10.0, places=3)


class EstimateVoSeconds(unittest.TestCase):
    def test_word_count_over_wpm_plus_internal_pauses(self):
        # 5 words @115wpm = 5/115*60 = 2.6087s; internal pauses exclude the trailing one.
        voiceover = [
            {"text": "one two three", "pause_after": 1.0},
            {"text": "four five", "pause_after": 0.5},  # trailing pause, excluded
        ]
        est = timing_util.estimate_vo_seconds(voiceover, wpm=115)
        self.assertAlmostEqual(est, 5 / 115 * 60 + 1.0, places=2)

    def test_empty_voiceover_is_zero(self):
        self.assertEqual(timing_util.estimate_vo_seconds([], wpm=115), 0.0)


if __name__ == "__main__":
    unittest.main()
