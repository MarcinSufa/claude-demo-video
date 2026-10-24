"""Pure unit tests for paint_guard.mjs; skipped when node is unavailable."""
import json
import pathlib
import shutil
import subprocess
import unittest

NODE = shutil.which("node")
MODULE = pathlib.Path(__file__).resolve().parent.parent / "assets" / "scripts" / "paint_guard.mjs"


def _module_values(expression):
    script = (f"import({json.dumps(MODULE.as_uri())}).then(m => "
              f"console.log(JSON.stringify({expression})))")
    out = subprocess.check_output([NODE, "--input-type=module", "-e", script], text=True)
    return json.loads(out)


@unittest.skipUnless(NODE, "needs node")
class PaintGuard(unittest.TestCase):
    def test_hex_luma(self):
        values = _module_values("['#000','#fff','#0a0705','#FFFFFF','garbage',null].map(m.hexLuma)")
        self.assertEqual(values[0], 0)
        self.assertEqual(values[1], 255)
        self.assertAlmostEqual(values[2], 7.669)
        self.assertEqual(values[3], 255)
        self.assertIsNone(values[4])
        self.assertIsNone(values[5])

    def test_blank_white_requires_dark_parseable_background(self):
        values = _module_values("[m.isBlankWhite(235, '#0a0705'), "
                                "m.isBlankWhite(30, '#0a0705'), "
                                "m.isBlankWhite(235, null), "
                                "m.isBlankWhite(235, '#f5f5f5')]")
        self.assertEqual(values, [True, False, False, False])

    def test_keepalive_script_parses(self):
        self.assertTrue(_module_values("typeof m.KEEPALIVE_JS === 'string' && m.KEEPALIVE_JS.length > 0 && (() => { new Function(m.KEEPALIVE_JS); return true; })()"))


if __name__ == "__main__":
    unittest.main()
