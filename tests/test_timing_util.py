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


class SolveSpeedup(unittest.TestCase):
    # autofit (P0-1, opt-in): pick the speedup that makes video >= vo_target.
    # video = sum(raw)/speedup - (N-1)*crossfade ; speedup* = sum(raw)/(vo_target+(N-1)*xf)
    def test_normal_case_in_clamp(self):
        sp, fits = timing_util.solve_speedup(51.44, vo_target=45.8, n=4, crossfade=0.6)
        self.assertTrue(fits)
        self.assertAlmostEqual(sp, 51.44 / (45.8 + 3 * 0.6), places=3)
        self.assertGreaterEqual(sp, 0.8)
        self.assertLessEqual(sp, 1.4)

    def test_footage_much_longer_clamps_high_still_fits(self):
        # VO short vs scenes -> ideal speedup > 1.4; clamp to 1.4, video longer but VO not cut
        sp, fits = timing_util.solve_speedup(100.0, vo_target=20.0, n=2, crossfade=0.6)
        self.assertEqual(sp, 1.4)
        self.assertTrue(fits)

    def test_vo_too_long_cannot_fit(self):
        # VO longer than scenes even at slowest -> can't fit; clamp low, fits=False (warn)
        sp, fits = timing_util.solve_speedup(20.0, vo_target=40.0, n=2, crossfade=0.6)
        self.assertEqual(sp, 0.8)
        self.assertFalse(fits)


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

    def test_leading_offset_and_per_line_overhead_are_additive(self):
        # New calibration kwargs (CON-9725 slice); default 0.0 preserves the two
        # tests above unchanged.
        voiceover = [{"text": "one two", "pause_after": 0.0},
                     {"text": "three", "pause_after": 0.0}]
        base = timing_util.estimate_vo_seconds(voiceover, wpm=120)
        with_offset = timing_util.estimate_vo_seconds(voiceover, wpm=120, leading_offset=1.0)
        with_overhead = timing_util.estimate_vo_seconds(voiceover, wpm=120, per_line_overhead=0.5)
        self.assertAlmostEqual(with_offset, base + 1.0, places=3)
        self.assertAlmostEqual(with_overhead, base + 0.5 * 2, places=3)  # 2 lines


class SceneSpans(unittest.TestCase):
    # Mirrors assemble.sh's chained xfade: each scene plays raw/speedup seconds,
    # consecutive scenes overlap by `crossfade`.
    def test_matches_predict_video_seconds_for_final_span(self):
        for raw in ([10.0], [8.0, 28.0, 12.0], [1.0, 2.5, 7.0, 0.75]):
            spans = timing_util.scene_spans(raw, 1.15, 0.6)
            self.assertAlmostEqual(
                spans[-1][1], timing_util.predict_video_seconds(raw, 1.15, 0.6), places=9)

    def test_empty_is_empty(self):
        self.assertEqual(timing_util.scene_spans([], 1.0, 0.6), [])

    def test_three_scene_spans_match_the_reference_build(self):
        # Real CON-9725 arc: c1 html_mockup 0->8, c2 before_after 7.4->35.4,
        # c3 endcards 34.8->46.8 (brief-timing.md).
        spans = timing_util.scene_spans([8.0, 28.0, 12.0], 1.0, 0.6)
        starts_ends = [(round(s, 2), round(e, 2)) for s, e, *_ in spans]
        self.assertEqual(starts_ends, [(0.0, 8.0), (7.4, 35.4), (34.8, 46.8)])

    def test_composite_before_after_emits_an_internal_sub_boundary(self):
        # This is the whole point of the feature: a naive scene-plan-boundary
        # check sees only 7.4 and 34.8 and misses the cut INSIDE c2.
        scenes = [{"type": "html_mockup"},
                  {"type": "before_after", "layout": "sequential", "cut_at": 14.0},
                  {"type": "endcards"}]
        spans = timing_util.scene_spans([8.0, 28.0, 12.0], 1.0, 0.6, scenes)
        # c2 (7.4->35.4) must have split into two sub-spans around the cut.
        self.assertEqual(len(spans), 4)
        self.assertAlmostEqual(spans[-1][1], 46.8, places=6)


class SceneOwnership(unittest.TestCase):
    def test_short_scene_gets_degeneracy_warning(self):
        spans = timing_util.scene_spans([1.0, 10.0], 1.0, 0.6)
        ownership = timing_util.scene_ownership(spans, 0.6)
        self.assertTrue(ownership[0]["warning"], "1.0s span < 2*0.6 crossfade must warn")
        self.assertFalse(ownership[1]["warning"])

    def test_normal_scene_no_warning(self):
        spans = timing_util.scene_spans([8.0, 28.0, 12.0], 1.0, 0.6)
        ownership = timing_util.scene_ownership(spans, 0.6)
        self.assertTrue(all(not w["warning"] for w in ownership))


class CheckSceneAlignment(unittest.TestCase):
    def test_reference_defect_is_flagged_with_correct_overrun(self):
        scenes = [{"type": "html_mockup"},
                  {"type": "before_after", "layout": "sequential", "cut_at": 14.0},
                  {"type": "endcards"}]
        spans = timing_util.scene_spans([8.0, 28.0, 12.0], 1.0, 0.6, scenes)
        ownership = timing_util.scene_ownership(spans, 0.6)
        bad = timing_util.check_scene_alignment(
            [{"line_start": 21.2, "line_end": 23.6}], ownership)
        self.assertFalse(bad["ok"])
        self.assertEqual(len(bad["violations"]), 1)
        self.assertAlmostEqual(bad["violations"][0]["overrun"], 1.6, places=1)

    def test_tuned_line_within_tolerance_is_not_flagged(self):
        scenes = [{"type": "html_mockup"},
                  {"type": "before_after", "layout": "sequential", "cut_at": 14.0},
                  {"type": "endcards"}]
        spans = timing_util.scene_spans([8.0, 28.0, 12.0], 1.0, 0.6, scenes)
        ownership = timing_util.scene_ownership(spans, 0.6)
        good = timing_util.check_scene_alignment(
            [{"line_start": 21.9, "line_end": 22.1}], ownership)
        self.assertTrue(good["ok"])

    def test_no_lines_is_ok(self):
        spans = timing_util.scene_spans([8.0, 28.0, 12.0], 1.0, 0.6)
        ownership = timing_util.scene_ownership(spans, 0.6)
        result = timing_util.check_scene_alignment([], ownership)
        self.assertTrue(result["ok"])


class MeasureVoiceRate(unittest.TestCase):
    def test_matches_the_briefs_measured_rate(self):
        # 100 words, 7.8s internal pauses, 1.2s leading offset, 43.9s speech-end
        # -> effective rate ~172 wpm (brief-timing.md Problem A).
        words = {"lines": [{"line_start": 1.2, "line_end": 43.9, "words": ["x"] * 100}]}
        result = timing_util.measure_voice_rate(words, [7.8])
        self.assertAlmostEqual(result["wpm"], 172.0, delta=2.0)

    def test_empty_is_zero_not_an_error(self):
        result = timing_util.measure_voice_rate({"lines": []}, [])
        self.assertEqual(result["wpm"], 0.0)

    def test_per_line_overhead_needs_at_least_two_lines(self):
        words = {"lines": [{"line_start": 1.2, "line_end": 43.9, "words": ["x"] * 100}]}
        result = timing_util.measure_voice_rate(words, [7.8])
        self.assertEqual(result["per_line_overhead"], 0.0)


if __name__ == "__main__":
    unittest.main()
