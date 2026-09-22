"""Tests for plan-scenes.py's `type: remotion` scene resolution.
Run: python -m unittest discover -s tests
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = str((Path(__file__).resolve().parent.parent / "assets" / "scripts" / "plan-scenes.py"))


def _run(scenes):
    config = {
        "scenes": {"sequence": scenes},
        "subs": {
            "project_name": "Demo", "project_url": "https://demo.test",
            "font_display": "Disp", "font_body": "Body", "font_mono": "Mono", "font_tagline": "Tag",
            "palette_bg": "#000000", "palette_end_card_bg": "#111111",
            "palette_rule": "#222222", "palette_fg": "#eeeeee",
        },
        "palette": {"bg": "#000000", "accent": "#ff0000"},
        "project": {"name": "Demo", "url": "https://demo.test"},
    }
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        cfg = root / "config.json"
        cfg.write_text(json.dumps(config), encoding="utf-8")
        env = dict(os.environ, DEMO_CONFIG=str(cfg))
        result = subprocess.run([sys.executable, SCRIPT], cwd=root, env=env,
                                capture_output=True, text=True)
        plan = None
        plan_path = root / "scene-plan.json"
        if plan_path.exists():
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        return result, plan


class RemotionScene(unittest.TestCase):
    def test_valid_scene_produces_expected_props(self):
        result, plan = _run([
            {"type": "remotion", "composition": "Opening", "duration": 4.2, "props": {"title": "Hi"}},
            {"type": "browser_capture", "url": "https://x.test"},
        ])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        entry = next(s for s in plan["scenes"] if s["type"] == "remotion")
        self.assertEqual(entry["composition"], "Opening")
        self.assertEqual(entry["duration"], 4.2)
        props = entry["remotion_props"]
        self.assertEqual(props["durationInFrames"], round(4.2 * 30))
        self.assertEqual(props["fps"], 30)
        self.assertEqual(props["width"], 1920)
        self.assertEqual(props["height"], 1080)
        self.assertEqual(props["props"], {"title": "Hi"})
        self.assertEqual(props["brand"]["palette"], {"bg": "#000000", "accent": "#ff0000"})
        self.assertEqual(props["brand"]["project_name"], "Demo")
        self.assertEqual(props["brand"]["project_url"], "https://demo.test")
        self.assertEqual(entry["mascot_plan"].get("emotion", "idle"), "idle")

    def test_missing_composition_names_the_field(self):
        result, _ = _run([
            {"type": "remotion", "duration": 3},
            {"type": "browser_capture", "url": "https://x.test"},
        ])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("composition", result.stdout + result.stderr)

    def test_missing_duration_names_the_field(self):
        result, _ = _run([
            {"type": "remotion", "composition": "Opening"},
            {"type": "browser_capture", "url": "https://x.test"},
        ])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duration", result.stdout + result.stderr)

    def test_zero_or_negative_duration_rejected(self):
        result, _ = _run([
            {"type": "remotion", "composition": "Opening", "duration": 0},
            {"type": "browser_capture", "url": "https://x.test"},
        ])
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
