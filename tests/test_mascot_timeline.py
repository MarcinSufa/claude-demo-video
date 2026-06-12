import importlib.util
import os
import sys
import unittest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts")
sys.path.insert(0, SCRIPTS)
spec = importlib.util.spec_from_file_location(
    "resolve_mascot_timeline", os.path.join(SCRIPTS, "resolve-mascot-timeline.py"))
rt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rt)

STUB = {"enabled": True, "emotion": "idle", "position": "bottom-right", "scale": 1.0}


def cover(tl, duration):
    """Assert segments are ordered, non-overlapping, and cover [0, duration]."""
    assert tl[0]["at"] == 0
    for a, b in zip(tl, tl[1:]):
        assert abs(a["until"] - b["at"]) < 1e-6
    assert abs(tl[-1]["until"] - duration) < 1e-6


class TestWholeScene(unittest.TestCase):
    def test_single_emotion_fills_scene(self):
        tl = rt.resolve_timeline(STUB, duration=10.0)
        cover(tl, 10.0)
        self.assertEqual([s["emotion"] for s in tl], ["idle"])

    def test_disabled_returns_empty(self):
        tl = rt.resolve_timeline({"enabled": False}, duration=10.0)
        self.assertEqual(tl, [])


class TestBeforeAfter(unittest.TestCase):
    def test_sequential_halves_split_at_midpoint(self):
        stub = dict(STUB, before="panic", after="celebrate")
        stub.pop("emotion")
        tl = rt.resolve_timeline(stub, duration=16.0, layout="sequential")
        cover(tl, 16.0)
        self.assertEqual(tl[0], {"at": 0.0, "until": 8.0, "emotion": "panic"})
        self.assertEqual(tl[1], {"at": 8.0, "until": 16.0, "emotion": "celebrate"})

    def test_half_duration_pins_the_split(self):
        stub = dict(STUB, before="panic", after="celebrate")
        stub.pop("emotion")
        tl = rt.resolve_timeline(stub, duration=14.0, layout="sequential",
                                 half_duration=6.0)
        self.assertEqual(tl[0]["until"], 6.0)
        cover(tl, 14.0)


class TestEvents(unittest.TestCase):
    def test_error_toast_window_becomes_panic(self):
        events = [{"kind": "waitToast", "text": "Error: save failed",
                   "at": 3.0, "until": 5.5}]
        tl = rt.resolve_timeline(STUB, duration=10.0, events=events)
        cover(tl, 10.0)
        self.assertEqual([s["emotion"] for s in tl], ["idle", "panic", "idle"])
        self.assertEqual(tl[1]["at"], 3.0)
        self.assertEqual(tl[1]["until"], 5.5)

    def test_benign_toast_becomes_point(self):
        events = [{"kind": "waitToast", "text": "Saved successfully",
                   "at": 3.0, "until": 5.0}]
        tl = rt.resolve_timeline(STUB, duration=10.0, events=events)
        self.assertEqual(tl[1]["emotion"], "point")

    def test_speed_ramp_becomes_sleep(self):
        events = [{"kind": "speed", "at": 2.0, "until": 6.0}]
        tl = rt.resolve_timeline(STUB, duration=10.0, events=events)
        self.assertEqual([s["emotion"] for s in tl], ["idle", "sleep", "idle"])

    def test_events_beyond_duration_are_clamped(self):
        events = [{"kind": "waitToast", "text": "error", "at": 8.0, "until": 14.0}]
        tl = rt.resolve_timeline(STUB, duration=10.0, events=events)
        cover(tl, 10.0)
        self.assertEqual(tl[-1]["emotion"], "panic")
        self.assertEqual(tl[-1]["until"], 10.0)


class TestSidecarNormalization(unittest.TestCase):
    def test_kind_field_wins_over_custom_label(self):
        raw = [{"label": "wait for the error", "kind": "waitToast",
                "text": "Error: nope", "start": 1.0, "end": 2.0}]
        evs = rt._normalize_sidecar_events(raw)
        self.assertEqual(evs[0]["kind"], "waitToast")
        tl = rt.resolve_timeline(STUB, duration=5.0, events=evs)
        self.assertIn("panic", [s["emotion"] for s in tl])

    def test_legacy_sidecar_label_still_detected(self):
        raw = [{"label": "waitToast", "start": 1.0, "end": 2.0, "speed": None, "zoom": None}]
        evs = rt._normalize_sidecar_events(raw)
        self.assertEqual(evs[0]["kind"], "waitToast")

    def test_zero_width_event_emits_nothing(self):
        tl = rt.resolve_timeline(STUB, duration=5.0,
                                 events=[{"kind": "speed", "at": 2.0, "until": 2.0}])
        self.assertEqual([s["emotion"] for s in tl], ["idle"])

    def test_half_duration_at_or_past_duration_single_segment(self):
        stub = dict(STUB, before="panic", after="celebrate")
        stub.pop("emotion")
        tl = rt.resolve_timeline(stub, duration=6.0, layout="sequential", half_duration=6.0)
        self.assertEqual(tl, [{"at": 0.0, "until": 6.0, "emotion": "panic"}])


class TestToastSeverity(unittest.TestCase):
    def test_severity_regex(self):
        for text in ("Error: x", "request FAILED", "invalid token", "access denied"):
            self.assertEqual(rt.toast_emotion(text), "panic")
        self.assertEqual(rt.toast_emotion("3 items copied"), "point")


if __name__ == "__main__":
    unittest.main()
