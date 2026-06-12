# tests/test_mascot_brand.py
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "assets", "scripts"))
from mascot_brand import contrast_ratio, ensure_contrast, remap_palette  # noqa: E402


class TestContrast(unittest.TestCase):
    def test_black_on_white_is_21(self):
        self.assertAlmostEqual(contrast_ratio("#000000", "#ffffff"), 21.0, places=1)

    def test_same_color_is_1(self):
        self.assertAlmostEqual(contrast_ratio("#808080", "#808080"), 1.0, places=2)

    def test_ensure_contrast_passes_through_good_color(self):
        self.assertEqual(ensure_contrast("#dbaf71", "#0a0705", minimum=3.0), "#dbaf71")

    def test_ensure_contrast_lightens_failing_color_on_dark_bg(self):
        fixed = ensure_contrast("#1a120d", "#0a0705", minimum=3.0)
        self.assertNotEqual(fixed, "#1a120d")
        self.assertGreaterEqual(contrast_ratio(fixed, "#0a0705"), 3.0)

    def test_ensure_contrast_darkens_failing_color_on_light_bg(self):
        fixed = ensure_contrast("#f2ead9", "#fdf8ef", minimum=3.0)
        self.assertGreaterEqual(contrast_ratio(fixed, "#fdf8ef"), 3.0)


class TestRemap(unittest.TestCase):
    def test_remap_applies_mapping_and_guards_body_eyes(self):
        palette = {"body": "#d97757", "eyes": "#141414", "belly": "#e8a087", "accent": "#b35a3e"}
        out = remap_palette(palette, {"body": "#11100f"}, bg="#0a0705")
        self.assertGreaterEqual(contrast_ratio(out["body"], "#0a0705"), 3.0)
        self.assertEqual(out["belly"], "#e8a087")  # unmapped slots untouched


if __name__ == "__main__":
    unittest.main()
