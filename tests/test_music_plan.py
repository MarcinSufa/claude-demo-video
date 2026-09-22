"""Tests for music_plan.py — spans -> ElevenLabs Music composition_plan.
Pure functions only. Run: python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "assets", "scripts"))
import music_plan  # noqa: E402


class SectionsFromSpans(unittest.TestCase):
    def test_boundaries_round_to_half_second_and_sum_exactly(self):
        sections = music_plan.sections_from_spans(
            [("intro", 0, 4.24), ("middle", 4.24, 10)], 10)
        self.assertEqual([s["duration_ms"] for s in sections], [4000, 6000])
        self.assertEqual(sum(s["duration_ms"] for s in sections), 10000)

    def test_short_first_section_merges_forward_last_is_never_dropped(self):
        sections = music_plan.sections_from_spans(
            [("short", 0, 2), ("main", 2, 8), ("tail", 8, 10)], 10)
        self.assertEqual([s["section_name"] for s in sections], ["main", "tail"])
        self.assertEqual([s["duration_ms"] for s in sections], [8000, 2000])
        self.assertEqual(sum(s["duration_ms"] for s in sections), 10000)

    def test_long_section_splits_evenly_and_keeps_exact_sum(self):
        sections = music_plan.sections_from_spans([("long", 0, 130)], 130)
        self.assertEqual(len(sections), 2)
        self.assertEqual([s["duration_ms"] for s in sections], [65000, 65000])
        self.assertEqual(sum(s["duration_ms"] for s in sections), 130000)

    def test_default_styles_by_position_and_local_override(self):
        sections = music_plan.sections_from_spans(
            [("a", 0, 4), ("b", 4, 8), ("c", 8, 12)], 12, {"b": ["custom"]})
        self.assertEqual(sections[0]["positive_local_styles"], ["sparse intro", "quiet but continuous"])
        self.assertEqual(sections[1]["positive_local_styles"], ["custom"])
        self.assertEqual(sections[2]["positive_local_styles"],
                          ["resolve", "sustained final chord", "clean ending"])
        for s in sections:
            self.assertEqual(s["negative_local_styles"], ["silence", "vocals"])
            self.assertEqual(s["lines"], [])

    def test_single_section_uses_first_position_styles(self):
        sections = music_plan.sections_from_spans([("only", 0, 5)], 5)
        self.assertEqual(sections[0]["positive_local_styles"], ["sparse intro", "quiet but continuous"])

    def test_rejects_total_under_three_seconds(self):
        with self.assertRaises(ValueError):
            music_plan.sections_from_spans([("x", 0, 2.9)], 2.9)


class CompositionPlan(unittest.TestCase):
    def test_deduplicates_negative_styles(self):
        result = music_plan.composition_plan(
            {"styles": ["warm"], "negative_styles": ["vocals", "harsh"]}, [{"section_name": "a"}])
        self.assertEqual(result["positive_global_styles"], ["warm"])
        self.assertEqual(result["negative_global_styles"], ["vocals", "harsh", "silence", "drops out"])

    def test_defaults(self):
        result = music_plan.composition_plan({}, [])
        self.assertEqual(result["positive_global_styles"],
                          ["instrumental", "cinematic ambient electronic", "warm analog"])
        self.assertEqual(result["negative_global_styles"], ["vocals", "silence", "drops out"])


class MusicCfgSha(unittest.TestCase):
    def test_volume_only_change_keeps_the_same_sha(self):
        a = music_plan.music_cfg_sha({"mode": "elevenlabs", "prompt": "calm", "volume": 0.45})
        b = music_plan.music_cfg_sha({"mode": "elevenlabs", "prompt": "calm", "volume": 0.9})
        self.assertEqual(a, b)

    def test_other_field_change_changes_the_sha(self):
        a = music_plan.music_cfg_sha({"mode": "elevenlabs", "prompt": "calm"})
        b = music_plan.music_cfg_sha({"mode": "elevenlabs", "prompt": "different"})
        self.assertNotEqual(a, b)

    def test_key_order_independent(self):
        a = music_plan.music_cfg_sha({"mode": "elevenlabs", "prompt": "calm"})
        b = music_plan.music_cfg_sha({"prompt": "calm", "mode": "elevenlabs"})
        self.assertEqual(a, b)

    def test_none_is_empty_config(self):
        self.assertEqual(music_plan.music_cfg_sha(None), music_plan.music_cfg_sha({}))


class FindDropouts(unittest.TestCase):
    def test_excludes_head_and_tail_closes_eof_open_silence(self):
        stderr = (
            "silence_start: 0.100\nsilence_end: 0.300\n"
            "silence_start: 2.000\nsilence_end: 3.000\n"
            "silence_start: 9.500\nsilence_end: 9.800\n"
            "silence_start: 6.000\n"
        )
        self.assertEqual(
            music_plan.find_dropouts(stderr, total_s=10, head=0.5, tail=3.0),
            [(2.0, 3.0), (6.0, 10.0)])

    def test_no_silence_no_dropouts(self):
        self.assertEqual(music_plan.find_dropouts("", total_s=10), [])


if __name__ == "__main__":
    unittest.main()
