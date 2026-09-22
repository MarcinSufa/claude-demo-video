"""Tests for apply-brand.py's secret refusal — brand.yaml must never carry an
API key/secret/token/password; the compiler refuses before rendering anything.
Run: python -m unittest discover -s tests
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "assets" / "scripts"


class ApplyBrandSecrets(unittest.TestCase):
    def _run(self, brand_text):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "brand.yaml").write_text(brand_text, encoding="utf-8")
            (root / "templates").mkdir()
            return subprocess.run(
                [sys.executable, str(SCRIPTS / "apply-brand.py"),
                 "--brand", "brand.yaml", "--templates", "templates", "--out", "out"],
                cwd=root, capture_output=True, text=True)

    def test_refuses_nested_api_key(self):
        secret = "sk-do-not-print-me"
        result = self._run(f"voice:\n  api_key: {secret}\nproject:\n  name: Demo\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("voice.api_key", result.stdout + result.stderr)
        self.assertNotIn(secret, result.stdout + result.stderr)

    def test_refuses_xi_api_key_case_insensitive(self):
        result = self._run("voice:\n  XI_API_KEY: whatever\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("voice.XI_API_KEY", result.stdout + result.stderr)

    def test_ordinary_brand_yaml_passes(self):
        result = self._run("project:\n  name: Demo\n  url: demo.test\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_does_not_false_positive_on_plural_or_partial_words(self):
        # review round 1 / P3: whole-segment match only -- "tokens" contains
        # "token" as a substring but must not be refused.
        result = self._run(
            "scenes:\n  api_tokens_seen: 3\n  attempts: 1\nproject:\n  name: Demo\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_voice_pronounce_keys_are_exempt(self):
        # pronounce keys are arbitrary brand terms to respell for TTS, not
        # config -- a term that happens to look secret-shaped must not refuse.
        result = self._run(
            "voice:\n  pronounce:\n    SecretSauce: \"Secret Sauce\"\n"
            "    ApiToken: \"A P I Token\"\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_refuses_apikey_and_api_key_variants(self):
        for snippet in ("voice:\n  apiKey: x\n", "voice:\n  api_key: x\n", "voice:\n  apikey: x\n"):
            with self.subTest(snippet=snippet):
                result = self._run(snippet)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
