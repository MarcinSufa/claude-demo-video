"""Tests for fetch-music.py: manifest lookup, per-user cache, sha256 verification.

Every URL is a local file:// fixture, so nothing here touches the network.
"""
import contextlib
import hashlib
import importlib.util
import io
import os
import pathlib
import tempfile
import unittest

import yaml

_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts", "fetch-music.py")
_spec = importlib.util.spec_from_file_location("fetch_music", _PATH)
fm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fm)


def _track(directory, name, payload):
    path = os.path.join(directory, name)
    with open(path, "wb") as f:
        f.write(payload)
    return {
        "url": pathlib.Path(path).resolve().as_uri(),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "licence": "CC0",
        "source_page": "fixture",
        "title": name,
        "artist": "fixture",
        "duration_s": 1,
    }


class CacheDir(unittest.TestCase):
    def test_explicit_env_wins(self):
        env = {"DEMO_MUSIC_CACHE": "/x/cache", "XDG_CACHE_HOME": "/y", "LOCALAPPDATA": "/z"}
        self.assertEqual(fm.cache_dir(env, "linux"), pathlib.Path("/x/cache"))

    def test_xdg_on_linux(self):
        env = {"XDG_CACHE_HOME": "/y", "HOME": "/home/u"}
        self.assertEqual(fm.cache_dir(env, "linux"), pathlib.Path("/y/demo-video/music"))

    def test_localappdata_on_windows(self):
        env = {"LOCALAPPDATA": "C:/Users/u/AppData/Local", "HOME": "/home/u"}
        self.assertEqual(fm.cache_dir(env, "win32"),
                         pathlib.Path("C:/Users/u/AppData/Local/demo-video/music"))

    def test_home_cache_fallback(self):
        self.assertEqual(fm.cache_dir({"HOME": "/home/u"}, "linux"),
                         pathlib.Path("/home/u/.cache/demo-video/music"))


class Fetch(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.cache = pathlib.Path(self.dir, "cache")

    def tearDown(self):
        self._tmp.cleanup()

    def test_primary_track_lands_in_output_and_cache(self):
        primary = _track(self.dir, "calm.mp3", b"calm bytes")
        out = os.path.join(self.dir, "music-src.mp3")
        chosen = fm.fetch({"calm": {"primary": primary}}, "calm", out, self.cache)
        self.assertEqual(chosen["title"], "calm.mp3")
        with open(out, "rb") as f:
            self.assertEqual(f.read(), b"calm bytes")
        self.assertTrue((self.cache / f"{primary['sha256']}.mp3").exists())

    def test_wrong_sha256_is_rejected_and_not_cached(self):
        primary = _track(self.dir, "calm.mp3", b"calm bytes")
        primary["sha256"] = "0" * 64
        out = os.path.join(self.dir, "music-src.mp3")
        with self.assertRaises(fm.FetchError) as ctx:
            fm.fetch({"calm": {"primary": primary}}, "calm", out, self.cache)
        self.assertIn("sha256", str(ctx.exception))
        self.assertFalse(os.path.exists(out))
        self.assertFalse((self.cache / ("0" * 64 + ".mp3")).exists())

    def test_alternate_used_when_primary_fails(self):
        primary = _track(self.dir, "gone.mp3", b"gone")
        os.remove(os.path.join(self.dir, "gone.mp3"))
        alternate = _track(self.dir, "alt.mp3", b"alt bytes")
        out = os.path.join(self.dir, "music-src.mp3")
        chosen = fm.fetch({"calm": {"primary": primary, "alternate": alternate}},
                          "calm", out, self.cache)
        self.assertEqual(chosen["title"], "alt.mp3")

    def test_cache_hit_skips_download_but_still_verifies(self):
        primary = _track(self.dir, "calm.mp3", b"calm bytes")
        self.cache.mkdir(parents=True)
        cached = self.cache / f"{primary['sha256']}.mp3"
        cached.write_bytes(b"corrupted")
        os.remove(os.path.join(self.dir, "calm.mp3"))
        out = os.path.join(self.dir, "music-src.mp3")
        with self.assertRaises(fm.FetchError):
            fm.fetch({"calm": {"primary": primary}}, "calm", out, self.cache)
        self.assertFalse(cached.exists(), "a corrupted cache entry must be evicted")

    def test_non_cc0_licence_is_rejected_before_download(self):
        track = _track(self.dir, "by.mp3", b"attribution required")
        track["licence"] = "CC-BY 4.0"
        out = os.path.join(self.dir, "music-src.mp3")
        with self.assertRaises(fm.FetchError) as ctx:
            fm.fetch({"calm": {"primary": track}}, "calm", out, self.cache)
        self.assertIn("licence", str(ctx.exception))
        self.assertFalse(os.path.exists(out))
        self.assertFalse((self.cache / f"{track['sha256']}.mp3").exists())

    def test_public_domain_wording_is_accepted(self):
        for wording in ("CC0", "CC0 1.0", "public domain", "Public Domain"):
            track = _track(self.dir, "pd.mp3", b"free")
            track["licence"] = wording
            out = os.path.join(self.dir, "music-src.mp3")
            fm.fetch({"calm": {"primary": track}}, "calm", out, self.cache)
            self.assertTrue(os.path.exists(out), wording)

    def test_main_reports_os_errors_as_warning_not_traceback(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = fm.main(["--manifest", os.path.join(self.dir, "missing.yaml"),
                          "--style", "calm", "--output", os.path.join(self.dir, "x.mp3")])
        self.assertEqual(rc, 1)
        self.assertIn("WARNING", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())

    def test_unwritable_output_is_fatal_not_a_warning(self):
        primary = _track(self.dir, "calm.mp3", b"calm bytes")
        manifest = os.path.join(self.dir, "m.yaml")
        with open(manifest, "w", encoding="utf-8") as f:
            yaml.safe_dump({"calm": {"primary": primary}}, f)
        output = os.path.join(self.dir, "no-such-dir", "music-src")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = fm.main(["--manifest", manifest, "--style", "calm", "--output", output,
                          "--cache-dir", str(self.cache)])
        self.assertNotEqual(rc, 0)
        self.assertNotIn("WARNING", err.getvalue())
        self.assertIn("no-such-dir", err.getvalue())
        self.assertIn("No such file", err.getvalue())

    def test_unknown_style_and_procedural_only(self):
        with self.assertRaises(fm.FetchError):
            fm.fetch({"calm": {"primary": {}}}, "tech", "x", self.cache)
        with self.assertRaises(fm.FetchError) as ctx:
            fm.fetch({"tech": {"procedural_only": True}}, "tech", "x", self.cache)
        self.assertIn("procedural", str(ctx.exception))

    def test_load_manifest_reads_track_fields(self):
        text = (
            "calm:\n  primary:\n    url: \"file:///a.mp3\"\n    sha256: \"ab\"\n"
            "    licence: CC0\n    source_page: \"p\"\n    title: \"T\"\n"
            "    artist: \"A\"\n    duration_s: 1\n")
        path = os.path.join(self.dir, "m.yaml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        manifest = fm.load_manifest(path)
        self.assertEqual(manifest["calm"]["primary"]["title"], "T")
        self.assertEqual(manifest["calm"]["primary"]["duration_s"], 1)


if __name__ == "__main__":
    unittest.main()
