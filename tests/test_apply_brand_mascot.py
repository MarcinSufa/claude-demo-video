# tests/test_apply_brand_mascot.py
import importlib.util
import os
import unittest


def _load(name, filename):
    path = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts", filename)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


apply_brand = _load("apply_brand", "apply-brand.py")
_coerce_mascot = apply_brand._coerce_mascot


class TestCoerceMascot(unittest.TestCase):
    def test_dict_passthrough(self):
        d = {"character": "fox", "enabled": True}
        self.assertIs(_coerce_mascot(d), d)

    def test_string_becomes_dict(self):
        result = _coerce_mascot("fox")
        self.assertEqual(result, {"character": "fox", "enabled": True})

    def test_true_becomes_enabled(self):
        self.assertEqual(_coerce_mascot(True), {"enabled": True})

    def test_falsy_becomes_empty(self):
        self.assertEqual(_coerce_mascot(False), {})
        self.assertEqual(_coerce_mascot(None), {})
        self.assertEqual(_coerce_mascot(""), {})


if __name__ == "__main__":
    unittest.main()
