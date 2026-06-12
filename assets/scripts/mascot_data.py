# assets/scripts/mascot_data.py
"""mascot_data.py — load + validate a mascot pixel-grid data file.

A mascot is deterministic data, not an image: legend (char -> palette slot),
palette (slot -> hex), animations (name -> frames of equal-width rows).
This module is the single format authority; render-mascot.py and the brand
remap helper both consume it.
"""
import json
import re

REQUIRED_ANIMATIONS = (
    "idle", "type", "panic", "celebrate", "sleep", "point", "enter", "exit",
)
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class MascotError(Exception):
    pass


def load_mascot(path):
    try:
        with open(path, encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError as e:
                raise MascotError(f"invalid JSON in {path}: {e}") from e
    except FileNotFoundError:
        raise MascotError(f"mascot file not found: {path}") from None


def validate_mascot(m):
    for key in ("name", "cell_px", "fps", "legend", "palette", "animations"):
        if key not in m:
            raise MascotError(f"missing required key '{key}'")
    for key in ("cell_px", "fps"):
        v = m[key]
        if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
            raise MascotError(f"'{key}' must be a positive integer, got {v!r}")
    if "scale" in m:
        s = m["scale"]
        if isinstance(s, bool) or not isinstance(s, (int, float)) or s <= 0:
            raise MascotError(f"'scale' must be a positive number, got {s!r}")
    legend, palette, anims = m["legend"], m["palette"], m["animations"]
    for slot, color in palette.items():
        if not _HEX.match(color):
            raise MascotError(f"palette slot '{slot}' has invalid hex '{color}'")
    for ch, slot in legend.items():
        if slot is not None and slot not in palette:
            raise MascotError(f"legend char '{ch}' maps to unknown palette slot '{slot}'")
    for name in REQUIRED_ANIMATIONS:
        if name not in anims or not anims[name]:
            raise MascotError(f"missing or empty required animation '{name}'")
    for name, frames in anims.items():
        for fi, frame in enumerate(frames):
            if not frame:
                raise MascotError(f"animation '{name}' frame {fi} is empty")
            width = len(frame[0])
            for row in frame:
                if len(row) != width:
                    raise MascotError(
                        f"animation '{name}' frame {fi} has inconsistent row width")
                for ch in row:
                    if ch not in legend:
                        raise MascotError(
                            f"animation '{name}' frame {fi} uses char '{ch}' "
                            f"not in legend")
