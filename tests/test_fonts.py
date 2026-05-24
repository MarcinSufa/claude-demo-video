"""Tests for apply-brand's Google Fonts <link> builder (P1-3).

Google Fonts css2 is STRICT: requesting an axis a family doesn't have (e.g. `ital`
on Geist, which has no italic) returns 400 and loads NOTHING. So the builder uses a
per-family axis table and a safe no-axis fallback for unknown families.
Run: python -m unittest discover -s tests
"""
import importlib.util
import os
import unittest

_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts", "apply-brand.py")
_spec = importlib.util.spec_from_file_location("apply_brand", _PATH)
apply_brand = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(apply_brand)


class GoogleFontsLink(unittest.TestCase):
    def test_includes_each_family_and_display_swap(self):
        url, _ = apply_brand.build_google_fonts_link(["Newsreader", "Geist", "JetBrains Mono"])
        self.assertTrue(url.startswith("https://fonts.googleapis.com/css2?"))
        self.assertIn("family=Newsreader:", url)
        self.assertIn("family=Geist:", url)
        self.assertIn("family=JetBrains+Mono:", url)   # spaces -> +
        self.assertTrue(url.endswith("&display=swap"))

    def test_geist_requested_without_italic(self):
        # Geist has no italic axis on Google Fonts — requesting ital would 400 the
        # whole stylesheet. Its spec must not contain "ital".
        url, _ = apply_brand.build_google_fonts_link(["Geist"])
        # normalize the `css2?` prefix so the first family also splits on a boundary
        geist = [p for p in url.replace("?", "&").split("&") if p.startswith("family=Geist")][0]
        self.assertNotIn("ital", geist)

    def test_serif_display_keeps_italic_for_wordmark(self):
        url, _ = apply_brand.build_google_fonts_link(["Newsreader"])
        self.assertIn("ital", url)  # the wordmark renders italic, so the serif needs it

    def test_dedupes_repeated_families(self):
        url, _ = apply_brand.build_google_fonts_link(["Inter", "Inter", "Inter"])
        self.assertEqual(url.count("family=Inter"), 1)

    def test_unknown_family_has_no_axis_and_is_reported(self):
        url, unknown = apply_brand.build_google_fonts_link(["Totally Made Up Face"])
        # no axis tuple (no ':') for the unknown family -> request can't 400
        self.assertIn("family=Totally+Made+Up+Face", url)
        self.assertNotIn("family=Totally+Made+Up+Face:", url)
        self.assertIn("Totally Made Up Face", unknown)

    def test_skips_empty_family_names(self):
        url, _ = apply_brand.build_google_fonts_link(["Inter", "", None])
        self.assertEqual(url.count("family="), 1)


if __name__ == "__main__":
    unittest.main()
