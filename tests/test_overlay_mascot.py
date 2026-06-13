import importlib.util
import os
import sys
import unittest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts")
sys.path.insert(0, SCRIPTS)
spec = importlib.util.spec_from_file_location(
    "overlay_mascot", os.path.join(SCRIPTS, "overlay-mascot.py"))
om = importlib.util.module_from_spec(spec)
spec.loader.exec_module(om)

TL = [
    {"at": 0.0, "until": 4.0, "emotion": "idle", "position": "bottom-right"},
    {"at": 4.0, "until": 6.0, "emotion": "panic", "position": "bottom-right"},
    {"at": 6.0, "until": 10.0, "emotion": "idle", "position": "bottom-right"},
]
POS = [(1700, 740)] * 3


class TestPosition(unittest.TestCase):
    def test_bottom_right_clears_captions(self):
        x, y = om.anchor_xy("bottom-right", video_w=1920, video_h=1080,
                            sprite_w=160, sprite_h=140)
        self.assertEqual(x, 1920 - 160 - om.MARGIN_PX)
        self.assertEqual(y, 1080 - 140 - om.CAPTION_CLEARANCE_PX)

    def test_bottom_left(self):
        x, y = om.anchor_xy("bottom-left", 1920, 1080, 160, 140)
        self.assertEqual(x, om.MARGIN_PX)

    def test_top_right(self):
        x, y = om.anchor_xy("top-right", 1920, 1080, 160, 140)
        self.assertEqual(y, om.MARGIN_PX)


class TestResolveAnchors(unittest.TestCase):
    DIMS = dict(video_w=1920, video_h=1080, sprite_w=160, sprite_h=140)

    def test_plain_segments_use_anchor_xy(self):
        anchors = om.resolve_anchors(TL, **self.DIMS)
        self.assertEqual(anchors, [om.anchor_xy("bottom-right", 1920, 1080,
                                                160, 140)] * 3)

    def test_move_segment_resolves_from_and_to(self):
        tl = [
            {"at": 0.0, "until": 3.0, "emotion": "idle",
             "position": "bottom-right"},
            {"at": 3.0, "until": 3.8, "emotion": "walk",
             "position": "bottom-left",
             "move": {"from": "bottom-right", "to": "bottom-left"}},
            {"at": 3.8, "until": 6.0, "emotion": "point",
             "position": "bottom-left"},
        ]
        anchors = om.resolve_anchors(tl, **self.DIMS)
        br = om.anchor_xy("bottom-right", 1920, 1080, 160, 140)
        bl = om.anchor_xy("bottom-left", 1920, 1080, 160, 140)
        self.assertEqual(anchors[1], (br, bl))
        self.assertEqual(anchors[2], bl)

    def test_offscreen_bottom_keeps_prev_home_x(self):
        tl = [
            {"at": 0.0, "until": 2.0, "emotion": "idle",
             "position": "bottom-left"},
            {"at": 2.0, "until": 2.8, "emotion": "walk",
             "position": "offscreen-bottom",
             "move": {"from": "bottom-left", "to": "offscreen-bottom"}},
        ]
        anchors = om.resolve_anchors(tl, **self.DIMS)
        bl = om.anchor_xy("bottom-left", 1920, 1080, 160, 140)
        self.assertEqual(anchors[1],
                         (bl, (bl[0], 1080 + om.OFFSCREEN_PAD_PX)))


class TestCmd(unittest.TestCase):
    def test_one_input_per_distinct_emotion(self):
        cmd = om.build_overlay_cmd("in.mp4", "out.mp4", "mascot", TL,
                                   POS, fps=7, speedup=1.0)
        self.assertEqual(cmd.count("-i"), 3)
        joined = " ".join(cmd)
        self.assertIn("mascot/idle/f_%03d.png", joined)
        self.assertIn("mascot/panic/f_%03d.png", joined)

    def test_enable_windows_match_timeline(self):
        cmd = om.build_overlay_cmd("in.mp4", "out.mp4", "mascot", TL,
                                   POS, fps=7, speedup=1.0)
        fc = cmd[cmd.index("-filter_complex") + 1]
        self.assertIn("between(t,0.000,4.000)", fc)
        self.assertIn("between(t,4.000,6.000)", fc)
        self.assertIn("between(t,6.000,10.000)", fc)

    def test_speedup_compensates_fps(self):
        cmd = om.build_overlay_cmd("in.mp4", "out.mp4", "mascot", TL,
                                   POS, fps=7, speedup=1.4)
        joined = " ".join(cmd)
        self.assertIn("-framerate 9.8", joined)

    def test_empty_timeline_returns_none(self):
        self.assertIsNone(om.build_overlay_cmd("in.mp4", "out.mp4", "mascot", [],
                                               [], fps=7, speedup=1.0))


class TestMotionExpressions(unittest.TestCase):
    MOVE_TL = [
        {"at": 0.0, "until": 3.0, "emotion": "idle", "position": "bottom-right"},
        {"at": 3.0, "until": 3.8, "emotion": "walk", "position": "bottom-left",
         "move": {"from": "bottom-right", "to": "bottom-left"}},
        {"at": 3.8, "until": 6.0, "emotion": "point", "position": "bottom-left"},
        {"at": 6.0, "until": 8.0, "emotion": "celebrate",
         "position": "bottom-left"},
    ]

    def _cmd(self, tl):
        positions = om.resolve_anchors(tl, 1920, 1080, 160, 140)
        return om.build_overlay_cmd("in.mp4", "out.mp4", "mascot", tl,
                                    positions, fps=7, speedup=1.0)

    def _fc(self, tl):
        cmd = self._cmd(tl)
        return cmd[cmd.index("-filter_complex") + 1]

    def test_move_segment_eases_between_anchor_xs(self):
        fc = self._fc(self.MOVE_TL)
        x0 = om.anchor_xy("bottom-right", 1920, 1080, 160, 140)[0]
        x1 = om.anchor_xy("bottom-left", 1920, 1080, 160, 140)[0]
        p = "clip((t-3.000)/0.800,0,1)"
        # smoothstep ease, not linear: x = x0+(x1-x0)*(p*p*(3-2*p))
        self.assertIn(f"'{x0}+({x1}-{x0})*({p}*{p}*(3-2*{p}))'", fc)

    def test_move_segment_has_hop_arc(self):
        fc = self._fc(self.MOVE_TL)
        # a horizontal move adds a parabolic jump arc to y (peak HOP_ARC_PX)
        self.assertIn(f"-{om.HOP_ARC_PX}*sin(PI*clip((t-3.000)/0.800,0,1))", fc)

    def test_celebrate_y_bounces(self):
        fc = self._fc(self.MOVE_TL)
        self.assertIn("-18*abs(sin((t-6.000)*4))", fc)

    def test_panic_x_shakes(self):
        fc = self._fc(TL)
        self.assertIn("+4*sin((t-4.000)*18)", fc)

    def test_plain_segments_stay_constant_ints(self):
        fc = self._fc(self.MOVE_TL)
        x, y = om.anchor_xy("bottom-right", 1920, 1080, 160, 140)
        self.assertIn(f"overlay={x}:{y}:shortest=1", fc)

    def test_walk_frames_input_for_move(self):
        cmd = self._cmd(self.MOVE_TL)
        # idle, walk, point, celebrate -> 4 looped inputs + capture
        self.assertEqual(cmd.count("-i"), 5)
        self.assertIn("mascot/walk/f_%03d.png", " ".join(cmd))


if __name__ == "__main__":
    unittest.main()
