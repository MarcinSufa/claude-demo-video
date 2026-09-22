"""Tests for make-music-elevenlabs.py's pure/cache-key glue (compute_plan_and_key)
and its cache/approval-gate behavior. Network is always mocked; ffmpeg is only
needed to build a tiny normalized fixture clip, so the class skips without it.
Run: python -m unittest discover -s tests
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "assets" / "scripts"
FFMPEG = shutil.which("ffmpeg")


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(FFMPEG, "needs ffmpeg for the normalized clip fixture")
class ComputePlanAndKey(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self._tmp.name)
        (self.cwd / ".normalized").mkdir()
        subprocess.run([
            FFMPEG, "-y", "-v", "error", "-f", "lavfi",
            "-i", "color=c=black:s=64x36:r=10:d=4", "-an",
            str(self.cwd / ".normalized" / "s1.mp4")], check=True)
        self._old_cwd = os.getcwd()
        os.chdir(self.cwd)
        elevenlabs_api = _load("elevenlabs_api", "elevenlabs_api.py")
        _load("music_plan", "music_plan.py")
        _load("timing_util", "timing_util.py")
        self.mod = _load("make_music_elevenlabs", "make-music-elevenlabs.py")
        self.elevenlabs_api = elevenlabs_api

    def tearDown(self):
        os.chdir(self._old_cwd)
        self._tmp.cleanup()

    def test_key_is_deterministic_and_sensitive_to_model(self):
        cfg = {"music": {"mode": "elevenlabs"}, "subs": {"speedup": 1.0, "crossfade": 0.6}}
        plan_scenes = [{"id": "s1", "name": "s1", "type": "title"}]
        _, model_id, _, _, key1, total_s = self.mod.compute_plan_and_key(cfg, plan_scenes)
        _, _, _, _, key2, _ = self.mod.compute_plan_and_key(cfg, plan_scenes)
        self.assertEqual(key1, key2)
        self.assertEqual(model_id, "music_v1")
        self.assertGreater(total_s, 0)

        cfg2 = {"music": {"mode": "elevenlabs", "model_id": "music_v2"},
                "subs": {"speedup": 1.0, "crossfade": 0.6}}
        _, _, _, _, key3, _ = self.mod.compute_plan_and_key(cfg2, plan_scenes)
        self.assertNotEqual(key1, key3)

    def test_uncached_without_approval_exits_4_with_no_network_call(self):
        cfg = {"music": {"mode": "elevenlabs"}, "subs": {"speedup": 1.0, "crossfade": 0.6}}
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        with open("scene-plan.json", "w", encoding="utf-8") as f:
            json.dump({"scenes": [{"id": "s1", "name": "s1", "type": "title"}]}, f)
        (self.cwd / ".env").write_text("ELEVENLABS_API_KEY=test-key\n", encoding="utf-8")

        with mock.patch("urllib.request.urlopen") as urlopen:
            with mock.patch.object(sys, "argv", ["make-music-elevenlabs.py", "--output", "out.mp3"]):
                with mock.patch.dict(os.environ, {"DEMO_ROOT": str(self.cwd)}, clear=False):
                    os.environ.pop("DEMO_APPROVE_SPEND", None)
                    with self.assertRaises(SystemExit) as caught:
                        self.mod.main()
        self.assertEqual(caught.exception.code, 4)
        urlopen.assert_not_called()

    def _approved_config(self, retry_rejected=False):
        cfg = {"music": {"mode": "elevenlabs"}, "subs": {"speedup": 1.0, "crossfade": 0.6}}
        plan_scenes = [{"id": "s1", "name": "s1", "type": "title"}]
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        with open("scene-plan.json", "w", encoding="utf-8") as f:
            json.dump({"scenes": plan_scenes}, f)
        _, _, _, _, cache_key, total_s = self.mod.compute_plan_and_key(cfg, plan_scenes)
        with open(".spend-approved.json", "w", encoding="utf-8") as f:
            json.dump({
                "code": "aaaaaaaa", "tts_keys": [],
                "music_max_seconds": int(total_s) + 10,
                "voiceover_sha": self.mod.timing_util.voiceover_sha([]),
                "music_cfg_sha": self.mod.music_plan.music_cfg_sha(cfg["music"]),
                "retry_rejected": retry_rejected,
            }, f)
        return cache_key

    def test_a2_4_previously_rejected_track_refuses_without_record_retry_flag(self):
        """A2 item 3/4: a track already quarantined for a silence dropout must
        never be silently re-billed on rerun -- exit 5, no network call,
        unless the approval record's own retry_rejected is true (the env var
        alone, without a matching record, is not enough)."""
        cache_key = self._approved_config(retry_rejected=False)
        (self.cwd / ".env").write_text("ELEVENLABS_API_KEY=test-key\n", encoding="utf-8")
        rejected_dir = self.cwd / ".music-cache" / "elevenlabs" / "rejected"
        rejected_dir.mkdir(parents=True)
        (rejected_dir / f"{cache_key}-1.mp3").write_bytes(b"rejected-audio")

        with mock.patch("urllib.request.urlopen") as urlopen:
            with mock.patch.object(sys, "argv", ["make-music-elevenlabs.py", "--output", "out.mp3"]):
                with mock.patch.dict(
                    os.environ, {"DEMO_ROOT": str(self.cwd), "DEMO_RETRY_REJECTED": "1"}, clear=False,
                ):
                    with self.assertRaises(SystemExit) as caught:
                        self.mod.main()
        self.assertEqual(caught.exception.code, 5)
        urlopen.assert_not_called()

    def test_a2_4_record_retry_flag_allows_a_new_request_with_a_new_quarantine_name(self):
        cache_key = self._approved_config(retry_rejected=True)
        (self.cwd / ".env").write_text("ELEVENLABS_API_KEY=test-key\n", encoding="utf-8")
        rejected_dir = self.cwd / ".music-cache" / "elevenlabs" / "rejected"
        rejected_dir.mkdir(parents=True)
        (rejected_dir / f"{cache_key}-1.mp3").write_bytes(b"rejected-audio")

        with mock.patch.object(
            self.mod.elevenlabs_api, "music_request",
            return_value=(b"new-track", {}),
        ) as music_request:
            with mock.patch.object(self.mod.music_plan, "find_dropouts", return_value=[]):
                with mock.patch.object(sys, "argv", ["make-music-elevenlabs.py", "--output", "out.mp3"]):
                    with mock.patch.dict(os.environ, {"DEMO_ROOT": str(self.cwd)}, clear=False):
                        self.mod.main()
        music_request.assert_called_once()
        self.assertTrue((self.cwd / "out.mp3").exists())
        self.assertEqual((self.cwd / "out.mp3").read_bytes(), b"new-track")

    def test_a2_2_music_cfg_sha_mismatch_refuses_with_no_network_call(self):
        self._approved_config()
        cfg = json.loads(Path("config.json").read_text(encoding="utf-8"))
        cfg["music"]["prompt"] = "a different request entirely"
        Path("config.json").write_text(json.dumps(cfg), encoding="utf-8")
        (self.cwd / ".env").write_text("ELEVENLABS_API_KEY=test-key\n", encoding="utf-8")

        with mock.patch("urllib.request.urlopen") as urlopen:
            with mock.patch.object(sys, "argv", ["make-music-elevenlabs.py", "--output", "out.mp3"]):
                with mock.patch.dict(os.environ, {"DEMO_ROOT": str(self.cwd)}, clear=False):
                    with self.assertRaises(SystemExit) as caught:
                        self.mod.main()
        self.assertEqual(caught.exception.code, 4)
        urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
