"""Tests for make-vo.py's elevenlabs provider approval gating (A1.2 / A2.2).
Run: python -m unittest discover -s tests
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "assets" / "scripts"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class MakeVoElevenlabsApproval(unittest.TestCase):
    def _make(self, cwd, voiceover, extra_voice=None):
        cfg = {"voice": {"provider": "elevenlabs", "voice_id": "v1", **(extra_voice or {})},
               "voiceover": voiceover}
        (cwd / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
        os.chdir(cwd)
        os.environ["DEMO_CONFIG"] = "config.json"
        timing_util = _load("timing_util", "timing_util.py")
        _load("elevenlabs_api", "elevenlabs_api.py")
        _load("vo_audio", "vo_audio.py")
        mod = _load("make_vo", "make-vo.py")
        return mod, timing_util

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self._tmp.name)
        self._old_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self._old_cwd)
        os.environ.pop("DEMO_CONFIG", None)
        self._tmp.cleanup()

    def test_no_approval_record_refuses_with_no_key_lookup(self):
        mod, _ = self._make(self.cwd, [{"text": "a fresh uncached line"}])
        with self.assertRaises(SystemExit) as caught:
            mod.gen_segments_elevenlabs()
        self.assertEqual(caught.exception.code, 4)

    def test_stale_voiceover_sha_in_record_refuses_even_with_matching_key(self):
        mod, timing_util = self._make(self.cwd, [{"text": "current text"}])
        voice_cfg = {"voice_id": "v1"}
        cache_key = mod.elevenlabs_api.tts_cache_key(voice_cfg, "current text")
        record = {
            "code": "deadbeef",
            "tts_keys": [cache_key],
            "music_max_seconds": None,
            "voiceover_sha": timing_util.voiceover_sha([{"text": "an older, different script"}]),
        }
        (self.cwd / ".spend-approved.json").write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaises(SystemExit) as caught:
            mod.gen_segments_elevenlabs()
        self.assertEqual(caught.exception.code, 4)

    def test_matching_voiceover_sha_and_key_proceeds_to_key_lookup(self):
        mod, timing_util = self._make(self.cwd, [{"text": "current text"}])
        voice_cfg = {"voice_id": "v1"}
        cache_key = mod.elevenlabs_api.tts_cache_key(voice_cfg, "current text")
        record = {
            "code": "deadbeef",
            "tts_keys": [cache_key],
            "music_max_seconds": None,
            "voiceover_sha": timing_util.voiceover_sha([{"text": "current text"}]),
        }
        (self.cwd / ".spend-approved.json").write_text(json.dumps(record), encoding="utf-8")
        # No API key anywhere -> should get PAST the approval gate and fail on
        # the key lookup instead (exit 3), proving the sha/key checks passed.
        with self.assertRaises(SystemExit) as caught:
            mod.gen_segments_elevenlabs()
        self.assertEqual(caught.exception.code, 3)


if __name__ == "__main__":
    unittest.main()
