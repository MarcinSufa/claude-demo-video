# tests/test_diorama_layout.py
import importlib.util, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "assets", "scripts"))
from diorama_layout import window_anchor  # noqa: E402

WIN = {"x": 100, "y": 200, "w": 1280, "h": 720}  # a window's canvas rect


class TestWindowAnchor(unittest.TestCase):
    def test_top_perches_centered_on_top_edge(self):
        # sprite 160x140: centered horizontally on the window, sitting ON the top edge
        self.assertEqual(window_anchor(WIN, "top", 160, 140),
                         (100 + (1280 - 160) // 2, 200 - 140))

    def test_beside_is_right_of_window_vertically_centered(self):
        self.assertEqual(window_anchor(WIN, "beside", 160, 140),
                         (100 + 1280 + 8, 200 + (720 - 140) // 2))

    def test_on_is_centered_inside(self):
        self.assertEqual(window_anchor(WIN, "on", 160, 140),
                         (100 + (1280 - 160) // 2, 200 + (720 - 140) // 2))

    def test_unknown_anchor_raises(self):
        with self.assertRaises(ValueError):
            window_anchor(WIN, "sideways", 160, 140)


if __name__ == "__main__":
    unittest.main()
