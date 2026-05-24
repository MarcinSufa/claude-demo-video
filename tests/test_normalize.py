"""Tests for normalize-clip's pure decision logic (P0-3 per-scene duration).

decide_normalization picks trim/pad/none from a measured vs target duration.
Run: python -m unittest discover tests
"""
import importlib.util
import os
import sys
import unittest

# normalize-clip.py has a hyphen → import by path
_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts", "normalize-clip.py")
_spec = importlib.util.spec_from_file_location("normalize_clip", _PATH)
normalize_clip = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(normalize_clip)


class DecideNormalization(unittest.TestCase):
    def test_trim_when_longer_than_target(self):
        action, value = normalize_clip.decide_normalization(8.5, 8.0)
        self.assertEqual(action, "trim")
        self.assertAlmostEqual(value, 8.0, places=3)

    def test_pad_when_shorter_than_target(self):
        action, value = normalize_clip.decide_normalization(7.5, 8.0)
        self.assertEqual(action, "pad")
        self.assertAlmostEqual(value, 0.5, places=3)  # pad AMOUNT (seconds to add)

    def test_none_within_epsilon(self):
        action, _ = normalize_clip.decide_normalization(8.02, 8.0, epsilon=0.05)
        self.assertEqual(action, "none")

    def test_just_past_epsilon_trims(self):
        action, _ = normalize_clip.decide_normalization(8.06, 8.0, epsilon=0.05)
        self.assertEqual(action, "trim")


if __name__ == "__main__":
    unittest.main()
