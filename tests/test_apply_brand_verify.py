"""Tests for apply-brand.runtime_config: every brand.yaml block a runtime
script reads must reach config.json, verify included."""
import importlib.util
import os
import unittest


def _load(name, filename):
    path = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts", filename)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


apply_brand = _load("apply_brand_verify", "apply-brand.py")


class RuntimeConfig(unittest.TestCase):
    def test_verify_block_passes_through(self):
        cfg = apply_brand.runtime_config({"verify": {"white_threshold": 200}}, {}, {})
        self.assertEqual(cfg["verify"], {"white_threshold": 200})

    def test_verify_defaults_to_empty(self):
        cfg = apply_brand.runtime_config({}, {}, {})
        self.assertEqual(cfg["verify"], {})

    def test_music_default_still_procedural(self):
        cfg = apply_brand.runtime_config({}, {}, {})
        self.assertEqual(cfg["music"]["mode"], "procedural")


if __name__ == "__main__":
    unittest.main()
