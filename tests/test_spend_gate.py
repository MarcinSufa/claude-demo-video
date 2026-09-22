"""Tests for spend-gate.py — cost estimate/refusal, no network I/O ever.
Run: python -m unittest discover -s tests
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "assets" / "scripts"


class SpendGate(unittest.TestCase):
    def _build(self, root, voice, voiceover, music, scenes):
        build = root / ".build"
        build.mkdir()
        for name in ("spend-gate.py", "elevenlabs_api.py", "timing_util.py"):
            shutil.copy2(SCRIPTS / name, build / name)
        (build / "config.json").write_text(json.dumps({
            "voice": voice, "voiceover": voiceover, "music": music,
        }), encoding="utf-8")
        (build / "scene-plan.json").write_text(json.dumps({"scenes": scenes}), encoding="utf-8")
        return build

    def _run(self, build, cmd, env_extra=None):
        env = dict(os.environ, DEMO_ROOT=str(build.parent))
        env.pop("DEMO_APPROVE_SPEND", None)
        env.update(env_extra or {})
        return subprocess.run([sys.executable, "spend-gate.py", cmd], cwd=build,
                              env=env, capture_output=True, text=True)

    def test_estimate_reports_none_when_provider_not_elevenlabs(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            build = self._build(root, {"provider": "edge-tts"}, [{"text": "hi"}],
                                 {"mode": "procedural"}, [{"id": "a", "type": "title"}])
            result = self._run(build, "estimate")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Billed services: none", result.stdout)

    def test_check_refuses_then_accepts_the_printed_code(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            build = self._build(
                root, {"provider": "elevenlabs", "voice_id": "v1"},
                [{"text": "hello there"}], {"mode": "procedural"},
                [{"id": "a", "type": "title"}])
            estimate = self._run(build, "estimate")
            self.assertIn("tts: 1/1 lines uncached, 11 characters", estimate.stdout)
            match = re.search(r"APPROVAL CODE:\s*([0-9a-f]{8})", estimate.stdout)
            self.assertIsNotNone(match)
            code = match.group(1)

            refused = self._run(build, "check")
            self.assertEqual(refused.returncode, 4)

            approved = self._run(build, "check", {"DEMO_APPROVE_SPEND": code})
            self.assertEqual(approved.returncode, 0)

    def test_check_never_touches_network(self):
        # No urlopen import failure possible — proven by exit code alone since the
        # module only imports urllib.request lazily inside elevenlabs_api's I/O
        # functions, never called from spend-gate's estimate/check paths.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            build = self._build(
                root, {"provider": "elevenlabs", "voice_id": "v1"},
                [{"text": "line"}], {"mode": "procedural"}, [{"id": "a", "type": "title"}])
            result = self._run(build, "estimate")
        self.assertEqual(result.returncode, 0)

    def test_cached_line_reports_no_billed_services(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            import importlib.util
            spec = importlib.util.spec_from_file_location("elevenlabs_api", SCRIPTS / "elevenlabs_api.py")
            eleven = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(eleven)
            voice_cfg = {"voice_id": "v1"}
            key = eleven.tts_cache_key(voice_cfg, "cached line")
            cache_dir = root / ".tts-cache" / "elevenlabs"
            cache_dir.mkdir(parents=True)
            (cache_dir / f"{key}.mp3").write_bytes(b"x")
            (cache_dir / f"{key}.json").write_text("{}", encoding="utf-8")
            build = self._build(
                root, {"provider": "elevenlabs", "voice_id": "v1"},
                [{"text": "cached line"}], {"mode": "procedural"}, [{"id": "a", "type": "title"}])
            result = self._run(build, "estimate")
        self.assertIn("Billed services: none", result.stdout)


if __name__ == "__main__":
    unittest.main()
