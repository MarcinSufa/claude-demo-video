"""Tests for dry-run-plan.measured_vo: --plan prefers a current vo-words.json
over the word-count heuristic and says so."""
import importlib.util
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "assets", "scripts"))

_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts", "dry-run-plan.py")
_spec = importlib.util.spec_from_file_location("dry_run_plan_measured", _PATH)
drp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drp)

import timing_util

VOICEOVER = [{"text": "one two three"}, {"text": "four five"}]


class MeasuredVo(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _write_words(self, lines, script_sha=None):
        data = {"lines": lines}
        if script_sha is not None:
            data["script_sha"] = script_sha
        with open("vo-words.json", "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_no_file_returns_none(self):
        self.assertIsNone(drp.measured_vo({"voiceover": VOICEOVER}))

    def test_matching_line_count_without_sha_is_used(self):
        self._write_words([{"text": "a", "line_start": 0, "line_end": 12.5, "words": []},
                           {"text": "b", "line_start": 13, "line_end": 37.5, "words": []}])
        seconds, source = drp.measured_vo({"voiceover": VOICEOVER})
        self.assertAlmostEqual(seconds, 37.5)
        self.assertIn("vo-words.json", source)
        self.assertIn("unverified, no script_sha", source)

    def test_line_count_mismatch_is_stale(self):
        self._write_words([{"text": "a", "line_start": 0, "line_end": 37.5, "words": []}])
        self.assertIsNone(drp.measured_vo({"voiceover": VOICEOVER}))

    def test_sha_mismatch_is_stale(self):
        self._write_words([{"line_end": 1.0}, {"line_end": 2.0}], script_sha="deadbeef")
        self.assertIsNone(drp.measured_vo({"voiceover": VOICEOVER}))

    def test_sha_match_is_current(self):
        self._write_words([{"line_end": 1.0}, {"line_end": 20.0}],
                          script_sha=timing_util.voiceover_sha(VOICEOVER))
        seconds, source = drp.measured_vo({"voiceover": VOICEOVER})
        self.assertAlmostEqual(seconds, 20.0)
        self.assertNotIn("unverified", source)

    def test_unreadable_file_returns_none(self):
        with open("vo-words.json", "w", encoding="utf-8") as f:
            f.write("{not json")
        self.assertIsNone(drp.measured_vo({"voiceover": VOICEOVER}))


class VoiceoverSha(unittest.TestCase):
    def test_depends_on_text_only(self):
        a = timing_util.voiceover_sha([{"text": "hi", "pause_after": 1}])
        b = timing_util.voiceover_sha([{"text": "hi", "pause_after": 2}])
        c = timing_util.voiceover_sha([{"text": "hi there"}])
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)


if __name__ == "__main__":
    unittest.main()
