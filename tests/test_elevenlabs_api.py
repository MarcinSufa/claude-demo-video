"""Tests for elevenlabs_api.py — key loading, redaction, alignment grouping,
cache keys, the urllib request/error contract, approval codes, and the ledger.
Network is always mocked. Run: python -m unittest discover -s tests
"""
import base64
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "assets", "scripts"))
import elevenlabs_api  # noqa: E402


class LoadKey(unittest.TestCase):
    def test_env_var_wins_over_files(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, ".env").write_text("ELEVENLABS_API_KEY=file-key\n", encoding="utf-8")
            self.assertEqual(
                elevenlabs_api.load_key({"ELEVENLABS_API_KEY": "env-key"}, root=d), "env-key")

    def test_configured_file_used_when_no_env_var(self):
        with tempfile.TemporaryDirectory() as d:
            custom = Path(d, "custom.env")
            custom.write_text("export ELEVENLABS_API_KEY=\"quoted-key\"   \n", encoding="utf-8")
            self.assertEqual(
                elevenlabs_api.load_key({"DEMO_ELEVENLABS_ENV_FILE": str(custom)}, root=d),
                "quoted-key")

    def test_falls_back_to_root_env_first_matching_line(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, ".env").write_text(
                "UNRELATED=x\nELEVENLABS_API_KEY='first'\nELEVENLABS_API_KEY=second\n",
                encoding="utf-8")
            self.assertEqual(elevenlabs_api.load_key({}, root=d), "first")

    def test_none_when_nothing_found(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(elevenlabs_api.load_key({}, root=d))


class Redact(unittest.TestCase):
    def test_replaces_all_occurrences(self):
        self.assertEqual(elevenlabs_api.redact("a KEY b KEY", "KEY"), "a <redacted> b <redacted>")

    def test_none_or_empty_key_no_op(self):
        self.assertEqual(elevenlabs_api.redact("x", None), "x")
        self.assertEqual(elevenlabs_api.redact("x", ""), "x")


class AlignmentToWords(unittest.TestCase):
    def test_merges_punctuation_and_collapses_spaces(self):
        chars = list("Hello world !")
        starts = [float(i) for i in range(len(chars))]
        ends = [s + 0.5 for s in starts]
        words = elevenlabs_api.alignment_to_words({
            "characters": chars, "character_start_times_seconds": starts,
            "character_end_times_seconds": ends})
        self.assertEqual([w["text"] for w in words], ["Hello", "world!"])

    def test_leading_punctuation_is_its_own_word(self):
        chars = list("- go")
        starts = [float(i) for i in range(len(chars))]
        ends = [s + 0.2 for s in starts]
        words = elevenlabs_api.alignment_to_words({
            "characters": chars, "character_start_times_seconds": starts,
            "character_end_times_seconds": ends})
        self.assertEqual([w["text"] for w in words], ["-", "go"])

    def test_rejects_missing_or_mismatched_arrays(self):
        for bad in ({}, {"characters": [], "character_start_times_seconds": [],
                          "character_end_times_seconds": []},
                     {"characters": ["a"], "character_start_times_seconds": [0.0],
                      "character_end_times_seconds": []}):
            with self.assertRaises(ValueError):
                elevenlabs_api.alignment_to_words(bad)


class TtsCacheKey(unittest.TestCase):
    def test_canonical_and_field_sensitive(self):
        cfg = {"voice_id": "v1", "model_id": "m1"}
        k1 = elevenlabs_api.tts_cache_key(cfg, "hello")
        k2 = elevenlabs_api.tts_cache_key(dict(reversed(list(cfg.items()))), "hello")
        self.assertEqual(k1, k2)
        self.assertNotEqual(k1, elevenlabs_api.tts_cache_key(cfg, "goodbye"))
        self.assertNotEqual(k1, elevenlabs_api.tts_cache_key({**cfg, "voice_id": "v2"}, "hello"))

    def test_ignores_undocumented_fields(self):
        cfg = {"voice_id": "v1", "pause_after": 0.1, "rate": "+5%"}
        self.assertEqual(
            elevenlabs_api.tts_cache_key(cfg, "hi"),
            elevenlabs_api.tts_cache_key({**cfg, "pause_after": 9.0, "rate": "-5%"}, "hi"))


class FakeResponse:
    def __init__(self, payload, headers=None):
        self._payload = payload
        self.headers = headers or {}

    def read(self):
        return self._payload

    def getheaders(self):
        return list(self.headers.items())

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TtsRequest(unittest.TestCase):
    def test_posts_expected_shape_and_decodes_alignment(self):
        payload = {"audio_base64": base64.b64encode(b"abc").decode(),
                   "alignment": {"characters": ["a"]},
                   "normalized_alignment": {"characters": ["z"]}}
        resp = FakeResponse(json.dumps(payload).encode(), {"xi-character-cost": "1"})
        with mock.patch("urllib.request.urlopen", return_value=resp) as urlopen:
            audio, alignment, headers = elevenlabs_api.tts_request(
                "secret", {"voice_id": "v"}, "hi")
        req = urlopen.call_args.args[0]
        self.assertIn("/v1/text-to-speech/v/with-timestamps", req.full_url)
        self.assertEqual(req.get_header("Xi-api-key"), "secret")
        self.assertEqual(audio, b"abc")
        self.assertEqual(alignment, {"characters": ["a"]})
        self.assertIn("xi-character-cost", headers)

    def test_http_error_redacts_key_and_caps_body(self):
        key = "very-secret"
        body = (f"oops {key} " + "x" * 400).encode()
        err = urllib.error.HTTPError("url", 401, "Unauthorized", {}, io.BytesIO(body))
        with mock.patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaises(elevenlabs_api.ElevenLabsError) as caught:
                elevenlabs_api.tts_request(key, {"voice_id": "v"}, "hi")
        msg = str(caught.exception)
        self.assertNotIn(key, msg)
        self.assertIn("401", msg)
        self.assertLessEqual(len(msg), 500)


class MusicRequest(unittest.TestCase):
    def test_never_sends_prompt_or_force_instrumental(self):
        payload = {"audio_base64": base64.b64encode(b"m").decode()}
        resp = FakeResponse(json.dumps(payload).encode(), {})
        with mock.patch("urllib.request.urlopen", return_value=resp) as urlopen:
            audio, _ = elevenlabs_api.music_request("k", {"sections": []}, seed=1)
        body = json.loads(urlopen.call_args.args[0].data.decode())
        for forbidden in ("prompt", "force_instrumental", "music_length_ms"):
            self.assertNotIn(forbidden, body)
        self.assertEqual(audio, b"m")


class ApprovalCode(unittest.TestCase):
    def test_order_independent_and_hex8(self):
        code = elevenlabs_api.approval_code(["b", "a"], "m")
        self.assertEqual(code, elevenlabs_api.approval_code(["a", "b", "a"], "m"))
        self.assertRegex(code, r"^[0-9a-f]{8}$")

    def test_sensitive_to_music_key(self):
        self.assertNotEqual(
            elevenlabs_api.approval_code(["a"], "m1"),
            elevenlabs_api.approval_code(["a"], "m2"))


class LedgerAppend(unittest.TestCase):
    def test_never_persists_key_or_text(self):
        with tempfile.TemporaryDirectory() as d:
            elevenlabs_api.ledger_append(d, {"kind": "tts", "characters": 3, "status": "success"})
            text = Path(d, ".spend-ledger.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("secret-key", text)
        self.assertEqual(json.loads(text.splitlines()[0])["kind"], "tts")


if __name__ == "__main__":
    unittest.main()
