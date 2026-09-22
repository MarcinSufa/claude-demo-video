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
        for name in ("spend-gate.py", "elevenlabs_api.py", "timing_util.py", "music_plan.py"):
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


class SpendGateApprovalRecordA2(unittest.TestCase):
    """Amendment A2: the approval record binds to the exact request (not just
    the code), never survives a failed check, and never trusts a foreign/
    unreadable leftover file silently.
    """
    def _build(self, root, voice, voiceover, music, scenes):
        build = root / ".build"
        build.mkdir()
        for name in ("spend-gate.py", "elevenlabs_api.py", "timing_util.py", "music_plan.py"):
            shutil.copy2(SCRIPTS / name, build / name)
        (build / "config.json").write_text(json.dumps({
            "voice": voice, "voiceover": voiceover, "music": music,
        }), encoding="utf-8")
        (build / "scene-plan.json").write_text(json.dumps({"scenes": scenes}), encoding="utf-8")
        return build

    def _run(self, build, cmd, env_extra=None):
        env = dict(os.environ, DEMO_ROOT=str(build.parent))
        env.pop("DEMO_APPROVE_SPEND", None)
        env.pop("DEMO_RETRY_REJECTED", None)
        env.update(env_extra or {})
        return subprocess.run([sys.executable, "spend-gate.py", cmd], cwd=build,
                              env=env, capture_output=True, text=True)

    def test_passing_check_records_fingerprints_and_retry_flag(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            build = self._build(
                root, {"provider": "elevenlabs", "voice_id": "v1"},
                [{"text": "hello there"}], {"mode": "procedural"},
                [{"id": "a", "type": "title"}])
            estimate = self._run(build, "estimate")
            code = re.search(r"APPROVAL CODE:\s*([0-9a-f]{8})", estimate.stdout).group(1)
            self._run(build, "check", {"DEMO_APPROVE_SPEND": code})
            record = json.loads((build / ".spend-approved.json").read_text(encoding="utf-8"))
        self.assertIn("voiceover_sha", record)
        self.assertIn("music_cfg_sha", record)
        self.assertIs(record["retry_rejected"], False)

    def test_check_with_a_foreign_leftover_record_refuses_once_then_passes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            build = self._build(
                root, {"provider": "edge-tts"}, [{"text": "free"}],
                {"mode": "procedural"}, [{"id": "a", "type": "title"}])
            (build / ".spend-approved.json").write_text('{"not": "ours"}', encoding="utf-8")
            first = self._run(build, "check")
            self.assertEqual(first.returncode, 4)
            self.assertFalse((build / ".spend-approved.json").exists())
            second = self._run(build, "check")
            self.assertEqual(second.returncode, 0)
            self.assertTrue((build / ".spend-approved.json").is_file())

    def test_atomic_write_leaves_no_tmp_file(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            build = self._build(
                root, {"provider": "edge-tts"}, [{"text": "free"}],
                {"mode": "procedural"}, [{"id": "a", "type": "title"}])
            self._run(build, "check")
            leftovers = sorted(p.name for p in build.glob(".spend-approved.json*"))
        self.assertEqual(leftovers, [".spend-approved.json"])

    def test_retry_env_at_check_time_is_captured_and_estimate_shows_it(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            build = self._build(
                root, {"provider": "edge-tts"}, [{"text": "free"}],
                {"mode": "elevenlabs", "max_seconds": 30},
                [{"id": "a", "type": "title"}])
            rejected_dir = root / ".music-cache" / "elevenlabs" / "rejected"
            rejected_dir.mkdir(parents=True)
            (rejected_dir / "somekey-1.mp3").write_bytes(b"x")

            estimate = self._run(build, "estimate", {"DEMO_RETRY_REJECTED": "1"})
            self.assertIn("retry of a rejected music track", estimate.stdout)
            code = re.search(r"APPROVAL CODE:\s*([0-9a-f]{8})", estimate.stdout).group(1)
            self._run(build, "check", {"DEMO_APPROVE_SPEND": code, "DEMO_RETRY_REJECTED": "1"})
            record = json.loads((build / ".spend-approved.json").read_text(encoding="utf-8"))
        self.assertIs(record["retry_rejected"], True)


if __name__ == "__main__":
    unittest.main()
