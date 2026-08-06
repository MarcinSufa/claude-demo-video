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
        # half_duration, not cut_at, is what plan-scenes.py actually emits
        # (plan-scenes.py:214) -- cut_at only ever existed in tests.
        scenes = [{"type": "html_mockup"},
                  {"type": "before_after", "layout": "sequential", "half_duration": 14.0},
                  {"type": "endcards"}]
        spans = timing_util.scene_spans([8.0, 28.0, 12.0], 1.0, 0.6, scenes)
        # c2 (7.4->35.4) must have split into two sub-spans around the cut.
        self.assertEqual(len(spans), 4)
        self.assertAlmostEqual(spans[-1][1], 46.8, places=6)

    def test_internal_cut_is_crossfade_shifted_not_naive_cumulative(self):
        # The internal BEFORE->AFTER cut must be measured from c2's own
        # crossfade-shifted start (7.4), not a naive unshifted cumulative
        # start (8.0). 7.4 + 14.0 = 21.4, confirmed against the real
        # rendered mp4 (BEFORE banner at 21.3s, AFTER banner at 21.5s).
        # 8.0 + 14.0 = 22.0 is the bug this test guards against regressing to.
        scenes = [{"type": "html_mockup"},
                  {"type": "before_after", "layout": "sequential", "half_duration": 14.0},
                  {"type": "endcards"}]
        spans = timing_util.scene_spans([8.0, 28.0, 12.0], 1.0, 0.6, scenes)
        # spans: c1, c2-before (7.4->cut), c2-after (cut->35.4), c3.
        self.assertAlmostEqual(spans[1][1], 21.4, places=6)
        self.assertAlmostEqual(spans[2][0], 21.4, places=6)

    def test_composite_cut_matches_check_timing_call_shape_with_real_speedup(self):
        # Mirrors PRODUCTION check-timing.py exactly: raw_durations there are
        # probed from .normalized/s{i}.mp4, which assemble.sh already divided
        # by speedup (setpts=PTS/SPEEDUP) -- so the call passes speedup=1.0 for
        # the duration scaling. But half_duration in scene-plan.json is always
        # authored in PRE-speedup source-footage seconds (plan-scenes.py just
        # copies the authored brand.yaml value through). Mixing those units
        # without a conversion is FATAL finding 1: at the default project
        # speedup 1.20 with half_duration 14, the cut lands 2.33s late (start
        # + 14.0 instead of start + 14/1.2 = start + 11.67).
        real_speedup = 1.2
        raw = [8.0, 28.0, 12.0]
        probed = [r / real_speedup for r in raw]  # what ffprobe measures post-normalize
        scenes = [{"type": "html_mockup"},
                  {"type": "before_after", "layout": "sequential", "half_duration": 14.0},
                  {"type": "endcards"}]
        spans = timing_util.scene_spans(probed, speedup=1.0, crossfade=0.6,
                                         scene_plan=scenes, composite_speedup=real_speedup)
        start_1 = raw[0] / real_speedup - 0.6
        expected_cut = start_1 + 14.0 / real_speedup  # start + 11.667, not start + 14.0
        edges = [e for s in spans for e in (float(s[0]), float(s[1]))]
        self.assertTrue(
            any(abs(e - expected_cut) < 1e-6 for e in edges),
            f"expected a boundary at {expected_cut:.3f}s; got edges "
            f"{sorted(set(round(e, 3) for e in edges))}")
        # The old (broken) contract would have placed it at start_1 + 14.0 --
        # prove that number is NOT present as a hard-cut boundary.
        wrong_cut = start_1 + 14.0
        self.assertFalse(any(abs(e - wrong_cut) < 1e-6 for e in edges))

    def test_out_of_range_composite_cut_is_dropped_with_a_warning_not_silently(self):
        # finding 3 + finding 5: at a high project speedup, an authored
        # half_duration (always pre-speedup seconds) can convert to a
        # local_cut that no longer fits inside the scene's own (post-speedup)
        # probed length -- the composite_cut_matches_check_timing_call_shape
        # case above, taken past the point where it still fits. The internal
        # sub-boundary must be silently dropped (0.0 < local_cut < raw still
        # guards scene_spans from emitting a nonsensical negative-length
        # sub-span) but NOT silently -- meta must carry a warning so the
        # caller can surface it instead of the check quietly doing nothing.
        real_speedup = 2.5
        raw = [8.0, 28.0, 12.0]
        probed = [r / real_speedup for r in raw]
        scenes = [{"type": "html_mockup"},
                  # 30.0 pre-speedup exceeds c2's own 28.0 raw footage --
                  # local_cut = 30.0/2.5 = 12.0s >= probed[1] (11.2s).
                  {"type": "before_after", "layout": "sequential", "half_duration": 30.0},
                  {"type": "endcards"}]
        spans = timing_util.scene_spans(probed, speedup=1.0, crossfade=0.6,
                                         scene_plan=scenes, composite_speedup=real_speedup)
        # No split -- still exactly one span per scene.
        self.assertEqual(len(spans), 3)
        meta = spans[1][2]
        self.assertTrue(meta.get("warning"), "dropped composite cut must carry a warning")
        self.assertIn("cut", meta["warning"].lower())


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

    def test_dropped_composite_cut_warning_propagates_into_ownership_window(self):
        # finding 3: scene_spans() attaches a warning to the span meta when a
        # composite sub-boundary is dropped as out-of-range; scene_ownership
        # (what check-timing.py actually iterates and prints) must not lose
        # that warning on the way through.
        real_speedup = 2.5
        raw = [8.0, 28.0, 12.0]
        probed = [r / real_speedup for r in raw]
        scenes = [{"type": "html_mockup"},
                  {"type": "before_after", "layout": "sequential", "half_duration": 30.0},
                  {"type": "endcards"}]
        spans = timing_util.scene_spans(probed, speedup=1.0, crossfade=0.6,
                                         scene_plan=scenes, composite_speedup=real_speedup)
        ownership = timing_util.scene_ownership(spans, 0.6)
        self.assertTrue(ownership[1]["warning"])
        self.assertIn("cut", ownership[1]["warning"].lower())


class CheckSceneAlignment(unittest.TestCase):
    def test_reference_defect_is_flagged_with_correct_overrun(self):
        # The internal cut of c2 (before_after, sequential, cut_at=14.0) sits
        # at start_1 + 14.0 = 7.4 + 14.0 = 21.4 -- confirmed by sampling the
        # real rendered mp4 frame by frame (BEFORE banner still on screen at
        # 21.3s, AFTER banner on screen at 21.5s). An unshifted cumulative
        # start (8.0 + 14.0 = 22.0) ignores the preceding crossfade overlap
        # and is the bug this test used to encode. 23.6 - 21.4 = 2.2s overrun.
        scenes = [{"type": "html_mockup"},
                  {"type": "before_after", "layout": "sequential", "half_duration": 14.0},
                  {"type": "endcards"}]
        spans = timing_util.scene_spans([8.0, 28.0, 12.0], 1.0, 0.6, scenes)
        ownership = timing_util.scene_ownership(spans, 0.6)
        bad = timing_util.check_scene_alignment(
            [{"line_start": 21.2, "line_end": 23.6}], ownership)
        self.assertFalse(bad["ok"])
        self.assertEqual(len(bad["violations"]), 1)
        self.assertAlmostEqual(bad["violations"][0]["overrun"], 2.2, places=1)

    def test_tuned_line_within_tolerance_is_not_flagged(self):
        # Straddles the true 21.4 cut by ~0.1s each side, within tolerance.
        scenes = [{"type": "html_mockup"},
                  {"type": "before_after", "layout": "sequential", "half_duration": 14.0},
                  {"type": "endcards"}]
        spans = timing_util.scene_spans([8.0, 28.0, 12.0], 1.0, 0.6, scenes)
        ownership = timing_util.scene_ownership(spans, 0.6)
        good = timing_util.check_scene_alignment(
            [{"line_start": 21.3, "line_end": 21.5}], ownership)
        self.assertTrue(good["ok"])

    def test_no_lines_is_ok(self):
        spans = timing_util.scene_spans([8.0, 28.0, 12.0], 1.0, 0.6)
        ownership = timing_util.scene_ownership(spans, 0.6)
        result = timing_util.check_scene_alignment([], ownership)
        self.assertTrue(result["ok"])


class MeasureVoiceRateTokenization(unittest.TestCase):
    """Pins the finding-2 tokenizer mismatch: measure_voice_rate used to count
    words as len(ln["words"]) (edge-tts WordBoundary tokens), while
    estimate_vo_seconds counts len(text.split()). Hyphenated words and
    contractions tokenize differently under the two rules -- edge-tts emits
    a separate WordBoundary for "well-known" (well / - / known) and for
    "can't" (can / 't) where split() sees one token each. That inflates the
    WordBoundary token count relative to the split()-word count, so a
    words-token-based wpm reads artificially HIGH.

    Direction of the error matters: a high measured wpm, fed back into
    estimate_vo_seconds (which divides by wpm), produces a LOW estimate --
    i.e. the estimator predicts the narration is SHORTER than it really is,
    which is exactly the silent-truncation risk this subsystem exists to
    prevent.
    """

    def test_hyphen_and_contraction_line_measures_split_word_rate_not_token_rate(self):
        # text.split() == 5 words: "top-notch", "can't", "miss", "it's", "great".
        # edge-tts WordBoundary tokens for the same line split hyphens and
        # contraction suffixes into their own events -- 9 tokens here (a
        # realistic over-count, not an exact model of edge-tts internals).
        text = "top-notch can't miss it's great"
        words_data = {"lines": [{
            "line_start": 0.0, "line_end": 10.8, "text": text,
            "words": ["top", "-", "notch", "can", "'t", "miss", "it", "'s", "great"],
        }]}
        result = timing_util.measure_voice_rate(words_data, [])

        # The tokenizer-mismatch bug reports total_words=9 (the WordBoundary
        # count) and wpm = 9/10.8*60 = 50.0 -- both wrong for a caller that
        # will divide SPLIT-word counts by this wpm.
        self.assertEqual(result["total_words"], 5,
                          "total_words must use the same split()-word rule "
                          "estimate_vo_seconds uses, not the raw WordBoundary "
                          "token count")
        self.assertAlmostEqual(result["wpm"], 5 / 10.8 * 60, places=2)
        self.assertNotAlmostEqual(result["wpm"], 50.0, places=1)

    def test_inflated_token_wpm_would_under_predict_real_duration(self):
        # Concrete demonstration of the under-prediction: reapply the
        # measured wpm to the SAME split()-word count estimate_vo_seconds
        # would use for this line, and it must reconstruct the real 10.8s
        # speaking time -- not the ~6.0s the token-count-inflated wpm (50.0)
        # would have produced (5 words / 50.0 wpm * 60 = 6.0s, a 4.8s /
        # 44% under-prediction of the real 10.8s).
        text = "top-notch can't miss it's great"
        words_data = {"lines": [{
            "line_start": 0.0, "line_end": 10.8, "text": text,
            "words": ["top", "-", "notch", "can", "'t", "miss", "it", "'s", "great"],
        }]}
        result = timing_util.measure_voice_rate(words_data, [])
        voiceover = [{"text": text, "pause_after": 0.0}]
        estimate = timing_util.estimate_vo_seconds(voiceover, wpm=result["wpm"])
        self.assertAlmostEqual(estimate, 10.8, delta=0.05)
        # The buggy (token-based) reconstruction would have landed here --
        # prove the fixed estimate is NOT this under-prediction.
        buggy_estimate = 5 / 50.0 * 60
        self.assertGreater(estimate, buggy_estimate + 1.0)


class MeasureVoiceRate(unittest.TestCase):
    def test_matches_the_briefs_measured_rate(self):
        # 100 words, 7.8s internal pauses, 1.2s leading offset, 43.9s speech-end
        # -> effective rate ~172 wpm (brief-timing.md Problem A).
        text = " ".join(["x"] * 100)
        words = {"lines": [{"line_start": 1.2, "line_end": 43.9, "text": text,
                             "words": ["x"] * 100}]}
        result = timing_util.measure_voice_rate(words, [7.8])
        self.assertAlmostEqual(result["wpm"], 172.0, delta=2.0)

    def test_empty_is_zero_not_an_error(self):
        result = timing_util.measure_voice_rate({"lines": []}, [])
        self.assertEqual(result["wpm"], 0.0)

    def test_per_line_overhead_is_zero_without_seg_durs(self):
        # No independent measurement supplied -> report "not measured" (0.0),
        # never a tautological identity (see below).
        text = " ".join(["x"] * 100)
        words = {"lines": [{"line_start": 1.2, "line_end": 43.9, "text": text,
                             "words": ["x"] * 100}]}
        result = timing_util.measure_voice_rate(words, [7.8])
        self.assertEqual(result["per_line_overhead"], 0.0)

    def test_per_line_overhead_is_not_a_tautology(self):
        # FATAL/MAJOR finding 3 (grok-review.md #3): the OLD implementation fit
        # wpm so total speaking time == sum(line durations), then computed
        # per-line residuals against that SAME fit -- residuals sum to zero by
        # construction, so mean residual was always ~0 regardless of the real
        # data. Prove the fix answers the real question instead: two lines
        # with equal word counts but very different real mp3 segment lengths
        # (make-vo.py's seg_dur, independent of the word-timing fit) must
        # produce a large, non-zero measured overhead -- not an identity.
        words = {"lines": [
            {"line_start": 0.0, "line_end": 2.0, "text": " ".join(["x"] * 10), "words": ["x"] * 10},
            {"line_start": 2.5, "line_end": 4.5, "text": " ".join(["x"] * 10), "words": ["x"] * 10},
        ]}
        # Real segment mp3s are each 1.0s longer than their word span (edge-tts
        # padding) -- an INDEPENDENT measurement, not derived from the wpm fit.
        seg_durs = [3.0, 3.0]
        result = timing_util.measure_voice_rate(words, [0.5], seg_durs=seg_durs)
        self.assertAlmostEqual(result["per_line_overhead"], 1.0, places=3)

    def test_per_line_overhead_measures_real_segment_padding_per_line(self):
        # Different padding per line -> different (non-averaged-to-zero) result;
        # this is the actual thing D4 asked to measure (fusion-timing.md D4:
        # edge-tts segment padding that scales with line count, not word count).
        words = {"lines": [
            {"line_start": 0.0, "line_end": 2.0, "text": " ".join(["x"] * 10), "words": ["x"] * 10},
            {"line_start": 2.5, "line_end": 4.5, "text": " ".join(["x"] * 10), "words": ["x"] * 10},
        ]}
        seg_durs = [2.2, 2.8]  # paddings: 0.2s and 0.8s -> mean 0.5s
        result = timing_util.measure_voice_rate(words, [0.5], seg_durs=seg_durs)
        self.assertAlmostEqual(result["per_line_overhead"], 0.5, places=3)

    def test_wpm_refit_from_pure_word_spans_when_seg_durs_present(self):
        # grok-review2.md finding A: without seg_durs, wpm is fit from
        # speech_end - leading - pauses, which already absorbs segment
        # padding -- so adding per_line_overhead on top double-counts it.
        # With seg_durs, wpm must instead be fit from the sum of pure word
        # spans (excluding padding). Fixture (segment layout, not just word
        # timestamps, so the gap between lines includes real overhead the
        # OLD fit would have silently folded into "speaking time"):
        #   line1: seg_dur=3.0, leading pad 0.2, word_span 2.0 -> line 1.2-3.2
        #   pause_after 0.5
        #   line2: seg_dur=2.5, leading pad 0.3, word_span 2.0 -> line 4.8-6.8
        # speech_end=6.8. OLD fit: (6.8-1.0-0.5)=5.3s -> 20/5.3*60=226.4wpm.
        # NEW fit: pure word spans 2.0+2.0=4.0s -> 20/4.0*60=300wpm.
        words = {"leading_offset": 1.0, "lines": [
            {"line_start": 1.2, "line_end": 3.2, "text": " ".join(["x"] * 10), "words": ["x"] * 10},
            {"line_start": 4.8, "line_end": 6.8, "text": " ".join(["x"] * 10), "words": ["x"] * 10},
        ]}
        result = timing_util.measure_voice_rate(words, [0.5], seg_durs=[3.0, 2.5])
        self.assertAlmostEqual(result["wpm"], 300.0, places=3)
        self.assertNotAlmostEqual(result["wpm"], 226.4, places=1)

    def test_wpm_refit_unaffected_by_asymmetric_padding(self):
        # Same 20 words / 4.0s of pure word spans, but the 1.7s of segment
        # overhead is split unevenly (0.2s on line1, 1.5s on line2) instead
        # of evenly. wpm must still land on 300 -- it must depend only on
        # word spans, not on how the padding happens to be distributed.
        #   line1: seg_dur=2.2, leading pad 0.1, word_span 2.0 -> line 1.1-3.1
        #   pause_after 0.5
        #   line2: seg_dur=3.5, leading pad 0.5, word_span 2.0 -> line 4.2-6.2
        words = {"leading_offset": 1.0, "lines": [
            {"line_start": 1.1, "line_end": 3.1, "text": " ".join(["x"] * 10), "words": ["x"] * 10},
            {"line_start": 4.2, "line_end": 6.2, "text": " ".join(["x"] * 10), "words": ["x"] * 10},
        ]}
        result = timing_util.measure_voice_rate(words, [0.5], seg_durs=[2.2, 3.5])
        self.assertAlmostEqual(result["wpm"], 300.0, places=3)

    def test_wpm_unchanged_without_seg_durs(self):
        # No independent measurement supplied -> keep the old (speech_end
        # based) fit; this is the path production already relies on when
        # make-vo hasn't run yet (dry-run-plan.py --plan before any build).
        text = " ".join(["x"] * 100)
        words = {"lines": [{"line_start": 1.2, "line_end": 43.9, "text": text,
                             "words": ["x"] * 100}]}
        result = timing_util.measure_voice_rate(words, [7.8])
        self.assertAlmostEqual(result["wpm"], 172.0, delta=2.0)


class RoundTripEstimateMatchesMeasurement(unittest.TestCase):
    def test_estimate_vo_seconds_recovers_measure_voice_rate_speech_end(self):
        # The acceptance test grok-review2.md finding A calls out as missing:
        # feed measure_voice_rate a realistic multi-line fixture with
        # non-zero padding, then feed ITS OUTPUTS into estimate_vo_seconds,
        # and the result must come back to the original speech-end -- i.e.
        # the calibration terms measure_voice_rate reports must be exactly
        # the terms estimate_vo_seconds needs, with nothing double-counted.
        #
        # Fixture mirrors make-vo.py's real construction: cursor advances by
        # each segment's full mp3 duration (leading-silence-in-segment +
        # words + trailing-silence-in-segment) + pause_after; line_start/
        # line_end are the actual first/last WORD times within that segment.
        # leading_offset = 1.2s (mix delay).
        # line1: seg_dur=3.0s, offset(leading pad)=0.2s, word_span=2.5s
        #        -> line_start=1.4, line_end=3.9, overhead=0.2+0.3(trail)=0.5
        # pause_after after line1 = 0.5s
        # line2: seg_dur=2.8s, offset=0.1s, word_span=2.2s
        #        -> cursor=1.2+3.0+0.5=4.7 -> line_start=4.8, line_end=7.0,
        #           overhead=0.1+0.5(trail)=0.6
        # pause_after after line2 = 0.7s
        # line3 (LAST): seg_dur=2.3s, offset=0.0s, word_span=2.0s, trailing
        #        silence=0.3s (edge-tts pads the LAST segment too -- the
        #        common real case; the segment mp3 keeps playing 0.3s after
        #        the last word, same as every other line's segment)
        #        -> cursor=4.7+2.8+0.7=8.2 -> line_start=8.2, line_end=10.2,
        #           overhead=0.3
        # That trailing 0.3s is real audio duration speech_end_seconds()
        # deliberately excludes (it's measuring last-WORD end, not segment
        # end -- see its docstring) but estimate_vo_seconds's
        # `sum(seg_dur)`-equivalent reconstruction has no way to know only
        # the LAST segment's padding should be dropped from the total, so it
        # comes back trailing_pad_n seconds OVER speech_end. See
        # estimate_vo_seconds's docstring for why this is accepted.
        words_data = {"leading_offset": 1.2, "lines": [
            {"line_start": 1.4, "line_end": 3.9, "text": " ".join(["w"] * 8),
             "words": ["w"] * 8},
            {"line_start": 4.8, "line_end": 7.0, "text": " ".join(["w"] * 7),
             "words": ["w"] * 7},
            {"line_start": 8.2, "line_end": 10.2, "text": " ".join(["w"] * 6),
             "words": ["w"] * 6},
        ]}
        pause_afters = [0.5, 0.7]
        seg_durs = [3.0, 2.8, 2.3]
        last_line_trailing_pad = 0.3

        measured = timing_util.measure_voice_rate(words_data, pause_afters, seg_durs)
        original_speech_end = timing_util.speech_end_seconds(words_data)
        self.assertAlmostEqual(original_speech_end, 10.2, places=3)

        # voiceover shape estimate_vo_seconds expects: total word count and
        # internal pause_afters must match what was actually spoken.
        voiceover = [
            {"text": " ".join(["w"] * 8), "pause_after": 0.5},
            {"text": " ".join(["w"] * 7), "pause_after": 0.7},
            {"text": " ".join(["w"] * 6), "pause_after": 0.0},  # trailing, excluded
        ]
        estimate = timing_util.estimate_vo_seconds(
            voiceover, wpm=measured["wpm"],
            leading_offset=measured["leading_offset"],
            per_line_overhead=measured["per_line_overhead"])

        # estimate_vo_seconds cannot know that ONLY the last segment's
        # padding should be dropped (it never sees seg_durs, only the
        # averaged per_line_overhead) so it comes back over speech_end by
        # exactly that last segment's trailing pad -- a conservative
        # over-estimate, never an under-estimate that could reproduce the
        # truncation bug this whole calibration exists to prevent.
        self.assertAlmostEqual(
            estimate, original_speech_end + last_line_trailing_pad, delta=0.01)
        self.assertGreater(estimate, original_speech_end)


class CalibrationPasteLines(unittest.TestCase):
    def test_includes_wpm_and_notes_cache_only_offsets(self):
        # residual 1 (grok-review2.md C): make-vo.py's paste hint used to
        # print only `wpm:`, silently dropping leading_offset/per_line_overhead
        # for an author who pastes it into a fresh checkout with no cache
        # file on disk. Print (or clearly document) the full calibration.
        measured = {"wpm": 183.0, "leading_offset": 1.2, "per_line_overhead": 0.42}
        lines = timing_util.calibration_paste_lines(measured)
        text = "\n".join(lines)
        self.assertIn("wpm: 183", text)
        self.assertIn("1.2", text)
        self.assertIn("0.42", text)

    def test_leading_offset_is_pasted_as_a_real_brand_yaml_key(self):
        # voice.leading_silence IS a documented brand.yaml key (unlike
        # per_line_overhead, which has none) -- the hint must paste it as
        # an actual key resolve_wpm can read back, not just mention the
        # number in a parenthetical, and must not claim it has no key.
        measured = {"wpm": 183.0, "leading_offset": 1.2, "per_line_overhead": 0.42}
        lines = timing_util.calibration_paste_lines(measured)
        text = "\n".join(lines)
        self.assertIn("leading_silence: 1.20", text)
        self.assertNotIn("leading offset", text.lower())


if __name__ == "__main__":
    unittest.main()
