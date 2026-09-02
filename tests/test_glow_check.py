"""Tests for glow_check.mjs: a glow/highlight selector must match exactly one node.

record-browser.mjs imports these helpers before it touches the page, so the
message format is pinned here. Runs through node; skipped when node is missing.
"""
import json
import pathlib
import shutil
import subprocess
import unittest

NODE = shutil.which("node")
MODULE = pathlib.Path(__file__).resolve().parent.parent / "assets" / "scripts" / "glow_check.mjs"


def _call(fn, *args):
    script = (
        f"import({json.dumps(MODULE.as_uri())}).then(m => "
        f"console.log(JSON.stringify(m.{fn}(...{json.dumps(args)}) ?? null)))")
    out = subprocess.check_output([NODE, "--input-type=module", "-e", script], text=True)
    return json.loads(out)


@unittest.skipUnless(NODE, "needs node")
class GlowTargets(unittest.TestCase):
    def test_click_with_glow(self):
        self.assertEqual(_call("glowTarget", {"click": "button.new", "glow": True}), "button.new")

    def test_fill_with_glow_uses_inner_selector(self):
        action = {"fill": {"selector": "input[name=title]", "text": "x"}, "glow": True}
        self.assertEqual(_call("glowTarget", action), "input[name=title]")

    def test_highlight_always_glows(self):
        self.assertEqual(_call("glowTarget", {"highlight": ".total-row"}), ".total-row")

    def test_click_without_glow_is_not_validated(self):
        self.assertIsNone(_call("glowTarget", {"click": "button.new"}))


@unittest.skipUnless(NODE, "needs node")
class SelectorCountError(unittest.TestCase):
    def test_exactly_one_is_fine(self):
        self.assertIsNone(_call("selectorCountError", "click", ".target", 1))

    def test_two_matches_name_selector_and_count(self):
        msg = _call("selectorCountError", "open dialog", ".target", 2)
        self.assertIn(".target", msg)
        self.assertIn("2", msg)
        self.assertIn("open dialog", msg)

    def test_zero_matches_is_an_error(self):
        msg = _call("selectorCountError", "click", ".missing", 0)
        self.assertIn("0", msg)

    def test_invalid_selector_is_an_error(self):
        msg = _call("selectorCountError", "click", "button >> nth=0", None)
        self.assertIn("button >> nth=0", msg)


if __name__ == "__main__":
    unittest.main()
