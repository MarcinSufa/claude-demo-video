"""The shipped music manifest must be complete and licence-clean: fetch-music.py
trusts it, so a bad entry here is a bad download for every user."""
import os
import re
import unittest

import yaml

MANIFEST = os.path.join(os.path.dirname(__file__), "..", "assets", "music", "manifest.yaml")
MOODS = ("calm", "uplift", "tech", "bugfix")


class Manifest(unittest.TestCase):
    def setUp(self):
        with open(MANIFEST, encoding="utf-8") as f:
            self.manifest = yaml.safe_load(f)

    def test_every_mood_has_primary_and_alternate(self):
        self.assertEqual(sorted(self.manifest), sorted(MOODS))
        for mood in MOODS:
            self.assertEqual(sorted(self.manifest[mood]), ["alternate", "primary"], mood)

    def test_every_entry_is_complete_and_cc0(self):
        for mood in MOODS:
            for role, track in self.manifest[mood].items():
                where = f"{mood}/{role}"
                self.assertRegex(track["sha256"], r"^[0-9a-f]{64}$", where)
                self.assertTrue(track["url"].startswith("https://"), where)
                self.assertTrue(track["source_page"].startswith("https://"), where)
                self.assertEqual(track["licence"], "CC0", where)
                self.assertTrue(30 <= int(track["duration_s"]) <= 240, where)
                for key in ("title", "artist"):
                    self.assertTrue(str(track.get(key, "")).strip(), f"{where} {key}")


if __name__ == "__main__":
    unittest.main()
