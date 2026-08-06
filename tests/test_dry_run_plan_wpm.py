"""Tests for dry-run-plan.resolve_wpm (fusion-timing.md Decision/A)."""
import importlib.util
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "assets", "scripts"))

_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts", "dry-run-plan.py")
_spec = importlib.util.spec_from_file_location("dry_run_plan_wpm", _PATH)
drp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drp)


class TestResolveWpm(unittest.TestCase):
    """resolve_wpm runs with cwd .build; each test chdirs into a temp dir."""

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _write_cache(self, cache):
        with open(drp.CALIBRATION_CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f)

    def test_explicit_wpm_wins(self):
        self._write_cache({"en-US-AndrewNeural|+0%": {"wpm": 150.0}})
        wpm, lead, overhead, source = drp.resolve_wpm({"voice": {"wpm": 172}})
        self.assertEqual(wpm, 172.0)
        self.assertEqual((lead, overhead), (0.0, 0.0))
        self.assertIn("voice.wpm", source)

    def test_explicit_wpm_accepts_string(self):
        # apply-brand.py writes config values as strings; float() must cover it.
        wpm, _, _, source = drp.resolve_wpm({"voice": {"wpm": "172"}})
        self.assertEqual(wpm, 172.0)
        self.assertIn("voice.wpm", source)

    def test_cache_hit_on_voice_and_rate(self):
        self._write_cache({"en-GB-RyanNeural|-5%": {
            "wpm": 168.4, "leading_offset": 1.2, "per_line_overhead": 0.35}})
        cfg = {"voice": {"voice_id": "en-GB-RyanNeural", "rate": "-5%"}}
        wpm, lead, overhead, source = drp.resolve_wpm(cfg)
        self.assertAlmostEqual(wpm, 168.4)
        self.assertAlmostEqual(lead, 1.2)
        self.assertAlmostEqual(overhead, 0.35)
        self.assertIn("cache", source.lower())

    def test_cache_miss_on_different_rate_falls_back(self):
        self._write_cache({"en-GB-RyanNeural|-5%": {"wpm": 168.4}})
        cfg = {"voice": {"voice_id": "en-GB-RyanNeural", "rate": "+0%"}}
        wpm, lead, overhead, source = drp.resolve_wpm(cfg)
        self.assertEqual(wpm, 115.0)
        self.assertEqual((lead, overhead), (0.0, 0.0))
        self.assertIn("uncalibrated", source.lower())

    def test_no_cache_file_falls_back_uncalibrated(self):
        wpm, _, _, source = drp.resolve_wpm({"voice": {}})
        self.assertEqual(wpm, 115.0)
        self.assertIn("uncalibrated", source.lower())

    def test_corrupt_cache_falls_back_uncalibrated(self):
        with open(drp.CALIBRATION_CACHE, "w", encoding="utf-8") as f:
            f.write("{not json")
        wpm, _, _, source = drp.resolve_wpm({"voice": {}})
        self.assertEqual(wpm, 115.0)
        self.assertIn("uncalibrated", source.lower())

    def test_explicit_wpm_still_applies_cached_leading_offset(self):
        # MAJOR finding 4 (grok-review.md #4): pinning the measured wpm into
        # brand.yaml (our own recommended workflow) must not make the
        # estimate WORSE than leaving the cache alone. The explicit path used
        # to force leading_offset/per_line_overhead to 0.0 even when a cache
        # entry for the exact same voice/rate had real measured values.
        self._write_cache({"en-US-AndrewNeural|+0%": {
            "wpm": 150.0, "leading_offset": 1.2, "per_line_overhead": 0.35}})
        wpm, lead, overhead, source = drp.resolve_wpm({"voice": {"wpm": 172}})
        self.assertEqual(wpm, 172.0)  # explicit wpm still wins
        self.assertAlmostEqual(lead, 1.2)
        self.assertAlmostEqual(overhead, 0.35)
        self.assertIn("voice.wpm", source)

    def test_explicit_wpm_with_no_cache_entry_has_zero_offset(self):
        # No cache entry for this voice/rate at all -> nothing to carry over;
        # explicit wpm alone, offsets stay 0.0 (unchanged prior behavior).
        wpm, lead, overhead, source = drp.resolve_wpm({"voice": {"wpm": 172}})
        self.assertEqual(wpm, 172.0)
        self.assertEqual((lead, overhead), (0.0, 0.0))

    def test_cache_wpm_null_falls_back_uncalibrated(self):
        # MINOR finding 6 (grok-review.md #6): a cached {"wpm": null} must not
        # crash --plan on float(None).
        self._write_cache({"en-US-AndrewNeural|+0%": {"wpm": None}})
        wpm, _, _, source = drp.resolve_wpm({"voice": {}})
        self.assertEqual(wpm, 115.0)
        self.assertIn("uncalibrated", source.lower())

    def test_cache_wpm_zero_falls_back_uncalibrated(self):
        # MINOR finding 6: a cached wpm of 0 must not reach estimate_vo_seconds
        # (ZeroDivisionError there) -- validate and fall back here instead.
        self._write_cache({"en-US-AndrewNeural|+0%": {"wpm": 0}})
        wpm, _, _, source = drp.resolve_wpm({"voice": {}})
        self.assertEqual(wpm, 115.0)
        self.assertIn("uncalibrated", source.lower())

    def test_cache_wpm_negative_falls_back_uncalibrated(self):
        self._write_cache({"en-US-AndrewNeural|+0%": {"wpm": -5}})
        wpm, _, _, source = drp.resolve_wpm({"voice": {}})
        self.assertEqual(wpm, 115.0)
        self.assertIn("uncalibrated", source.lower())


if __name__ == "__main__":
    unittest.main()
