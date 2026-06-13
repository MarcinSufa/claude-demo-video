# tests/test_diorama_plan.py
import importlib.util, os, sys, unittest
SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts")
sys.path.insert(0, SCRIPTS)
spec = importlib.util.spec_from_file_location("plan_scenes", os.path.join(SCRIPTS, "plan-scenes.py"))
ps = importlib.util.module_from_spec(spec); spec.loader.exec_module(ps)

# Also load make-diorama for diorama_timeline (used in test 3)
_md_spec = importlib.util.spec_from_file_location(
    "make_diorama", os.path.join(SCRIPTS, "make-diorama.py"))
md = importlib.util.module_from_spec(_md_spec); _md_spec.loader.exec_module(md)


class TestDioramaPlan(unittest.TestCase):
    SCENE = {"type": "diorama", "duration": 12,
             "canvas": {"width": 3840, "height": 2160, "backdrop": "assets/desk.jpg"},
             "windows": [{"id": "a", "source": "footage/a.mp4", "x": 100, "y": 100, "w": 1280},
                         {"id": "b", "url": "http://localhost:3000", "x": 2300, "y": 800, "w": 1280}],
             "camera": [{"focus": "a", "zoom": 1.5, "hold": 4},
                        {"focus": "b", "zoom": 1.5, "hold": 5, "transition": 1.0}],
             "mascot": {"keyframes": [{"at": 0, "emotion": "idle", "at_window": "a", "anchor": "top"},
                                      {"at": 5, "emotion": "point", "at_window": "b", "anchor": "beside"}]}}

    def test_entry_has_diorama_fields(self):
        plan = ps.custom_arc([self.SCENE])
        e = plan[0]
        self.assertEqual(e["type"], "diorama")
        self.assertEqual(len(e["windows"]), 2)
        self.assertEqual(e["camera"][1]["focus"], "b")

    def test_url_window_gets_a_capture_spec_source_passes_through(self):
        e = ps.custom_arc([self.SCENE])[0]
        a, b = e["windows"]
        self.assertIn("a.mp4", a["source"])         # source path resolved
        self.assertIn("capture", b)                 # url window -> browser_capture spec

    def test_mascot_timeline_has_walk_move_between_windows(self):
        # plan-scenes stores keyframes (sorted by `at`); make-diorama.diorama_timeline
        # expands them into segments + walk-moves at build time.
        # Test 1: keyframes are present and sorted by `at`.
        e = ps.custom_arc([self.SCENE])[0]
        kf = e["mascot"]["keyframes"]
        self.assertIsNotNone(kf, "mascot keyframes should be stored")
        self.assertEqual(kf, sorted(kf, key=lambda k: k["at"]), "keyframes must be sorted by at")
        # Test 2: calling diorama_timeline on the stored keyframes produces a walk
        # move from window 'a' to window 'b'.
        tl = md.diorama_timeline(kf, e["duration"])
        self.assertTrue(any("move" in s for s in tl), "walk move should be inserted")
        moves = [s for s in tl if "move" in s]
        self.assertTrue(any(m["move"]["from_window"] == "a" and m["move"]["to_window"] == "b"
                            for m in moves),
                        "move should go from window 'a' to window 'b'")
        self.assertTrue(any(s.get("at_window") == "a" for s in tl),
                        "a segment at window 'a' should appear")


class TestDioramaMascotSuppressed(unittest.TestCase):
    def test_mascot_plan_disabled_for_diorama(self):
        # the diorama composites its own mascot on the canvas (window-relative
        # keyframes), so the standard corner-overlay phase must never fire — even
        # when the global mascot is enabled and the scene carries keyframes
        stub = ps.mascot_stub(
            {"enabled": True, "character": "kangaroo"},
            {"type": "diorama"},
            {"enabled": True, "keyframes": [{"at": 0, "emotion": "idle",
                                             "at_window": "a", "anchor": "top"}]})
        self.assertFalse(stub["enabled"])
        self.assertNotIn("keyframes", stub)   # overlay keyframes must not leak through


class TestDioramaChromeStyleInEntry(unittest.TestCase):
    SCENE = {"type": "diorama", "canvas": {"width": 2560, "height": 1440},
             "camera": [{"focus": "a", "hold": 2}, {"focus": "a", "hold": 2}],
             "windows": [{"id": "a", "source": "footage/a.mp4", "x": 1, "y": 2, "w": 900, "chrome": True}]}
    CTX = {"chrome_style": {"bar_bg": "#17171a", "rule": "#2c2c32", "fg": "#f4efe3"}}

    def test_chrome_window_carries_chrome_style_into_entry(self):
        # the chrome bar colours must land in the scene entry so the scene cache
        # (which hashes the entry) busts a stale chrome clip when the palette changes
        e = ps.custom_arc([self.SCENE], ctx=self.CTX)[0]
        self.assertEqual(e["chrome_style"], self.CTX["chrome_style"])

    def test_no_chrome_window_no_chrome_style(self):
        plain = {**self.SCENE,
                 "windows": [{"id": "a", "source": "footage/a.mp4", "x": 1, "y": 2, "w": 900}]}
        e = ps.custom_arc([plain], ctx=self.CTX)[0]
        self.assertNotIn("chrome_style", e)


if __name__ == "__main__":
    unittest.main()
