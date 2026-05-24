"""apply-brand.py — the brand compiler.

Reads brand.yaml, renders every template in templates/ with {{placeholders}}
substituted, writes results to .build/, and emits .build/config.json for the
runtime scripts (make-vo.py, make-captions.py, assemble.sh) to read.

Run this FIRST in the pipeline. build.sh calls it automatically.

Usage:  python scripts/apply-brand.py [--brand brand.yaml] [--out .build]
"""
import argparse
import json
import os
import re
import shutil
import sys

try:
    import yaml
except ImportError:
    sys.exit("Missing pyyaml — run: pip install --user pyyaml")


def hex_to_ansi(hex_color):
    """#0a0705 -> '10;7;5' for \\033[38;2;R;G;Bm true-color ANSI."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"{r};{g};{b}"


# Google Fonts css2 is STRICT: requesting an axis a family lacks (e.g. `ital` on Geist,
# which has no italic) returns HTTP 400 and loads NOTHING. So map each known family to a
# SAFE axis spec. Display serifs keep `ital` (the wordmark renders italic). Unknown
# families fall back to no axis (regular only) — never 400s — and are reported so the
# author can add them here or supply axes.
FONT_SPECS = {
    # serif / display (italic kept for the end-card wordmark)
    "Newsreader": "ital,opsz,wght@0,6..72,300;0,6..72,400;0,6..72,500;1,6..72,300;1,6..72,400",
    "Fraunces": "ital,opsz,wght@0,9..144,300;0,9..144,400;0,9..144,500;1,9..144,300;1,9..144,400",
    "Instrument Serif": "ital@0;1",
    "Playfair Display": "ital,wght@0,400;0,500;0,600;1,400;1,500",
    "Lora": "ital,wght@0,400;0,500;0,600;1,400",
    "Cormorant Garamond": "ital,wght@0,400;0,500;1,400",
    "EB Garamond": "ital,wght@0,400;0,500;1,400",
    "Spectral": "ital,wght@0,300;0,400;0,500;1,400",
    # sans (Geist has NO italic — must not request it)
    "Geist": "wght@300;400;500;600;700",
    "Inter": "ital,wght@0,300;0,400;0,500;0,600;1,400",
    "Instrument Sans": "ital,wght@0,400;0,500;0,600;1,400",
    "Space Grotesk": "wght@300;400;500;700",
    "DM Sans": "ital,opsz,wght@0,9..40,400;0,9..40,500;1,9..40,400",
    # mono
    "JetBrains Mono": "ital,wght@0,300;0,400;0,500;0,700;1,400",
    "Geist Mono": "wght@300;400;500",
    "IBM Plex Mono": "ital,wght@0,400;0,500;1,400",
    "Space Mono": "ital,wght@0,400;0,700;1,400",
    "Roboto Mono": "ital,wght@0,300;0,400;0,500;1,400",
    "Fira Code": "wght@300;400;500;700",
    "DM Mono": "ital,wght@0,400;0,500;1,400",
}


def build_google_fonts_link(families):
    """Build the css2 stylesheet URL for `families`. Returns (url, unknown_set).

    Dedupes, drops empties, maps known families to safe axis specs, and falls back to
    a no-axis request (regular only) for unknown families so the request never 400s.
    """
    seen = []
    for fam in families:
        if fam and fam not in seen:
            seen.append(fam)
    parts, unknown = [], set()
    for fam in seen:
        plus = fam.replace(" ", "+")
        spec = FONT_SPECS.get(fam)
        if spec:
            parts.append(f"family={plus}:{spec}")
        else:
            parts.append(f"family={plus}")
            unknown.add(fam)
    url = "https://fonts.googleapis.com/css2?" + "&".join(parts) + "&display=swap"
    return url, unknown


def deep_get(d, path, default=None):
    cur = d
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def build_substitutions(brand):
    """Flatten brand.yaml into a {placeholder: value} dict for template rendering."""
    pal = brand.get("palette", {})
    proj = brand.get("project", {})
    logo = brand.get("logo", {})
    typo = brand.get("typography", {})
    voice = brand.get("voice", {})
    backdrop = brand.get("backdrop", {})
    scenes = brand.get("scenes", {})
    cards = brand.get("end_cards", {})

    # Defaults mirror the ExoVault Vellum reference
    pal_defaults = {
        "bg": "#0a0705", "fg": "#dcd7cf", "fg_lo": "#a9a49c", "fg_faint": "#7a736c",
        "accent": "#dbaf71", "rule": "#29231f", "end_card_bg": "#1e1714",
    }
    for k, v in pal_defaults.items():
        pal.setdefault(k, v)

    mem = pal.get("memory_type_colors", {})
    mem_defaults = {
        "fact": "#c9a471", "skill": "#84b385", "decision": "#c37b7d",
        "preference": "#d0c3a7", "constraint": "#7a8ea8", "correction": "#d3896c",
        "episodic": "#a18cc8", "task": "#c3b16d",
    }
    for k, v in mem_defaults.items():
        mem.setdefault(k, v)

    url = proj.get("url", "myproduct.com")
    url_spoken = url.replace(".", " dot ").replace("/", " slash ")

    # Wordmark: prefer split, fall back to full
    wm_full = logo.get("wordmark_full")
    if wm_full:
        wm_italic, wm_roman = "", wm_full
    else:
        wm_italic = logo.get("wordmark_italic", "My")
        wm_roman = logo.get("wordmark_roman", "Product")

    subs = {
        # project
        "project_name": proj.get("name", "MyProduct"),
        "project_url": url,
        "project_url_spoken": url_spoken,
        "project_version_tag": proj.get("version_tag", "v0.1.mp4"),
        # palette hex
        "palette_bg": pal["bg"],
        "palette_fg": pal["fg"],
        "palette_fg_lo": pal["fg_lo"],
        "palette_fg_faint": pal["fg_faint"],
        "palette_accent": pal["accent"],
        "palette_rule": pal["rule"],
        "palette_end_card_bg": pal["end_card_bg"],
        # palette ANSI (for display.sh true-color)
        "ansi_bg": hex_to_ansi(pal["bg"]),
        "ansi_fg": hex_to_ansi(pal["fg"]),
        "ansi_fg_lo": hex_to_ansi(pal["fg_lo"]),
        "ansi_fg_faint": hex_to_ansi(pal["fg_faint"]),
        "ansi_accent": hex_to_ansi(pal["accent"]),
        "ansi_rule": hex_to_ansi(pal["rule"]),
        # memory colors (hex + ANSI)
        **{f"mem_{k}": v for k, v in mem.items()},
        **{f"ansi_mem_{k}": hex_to_ansi(v) for k, v in mem.items()},
        # logo + wordmark
        "logo_svg": logo.get("svg_inline", "").strip(),
        "wordmark_italic": wm_italic,
        "wordmark_roman": wm_roman,
        # typography
        "font_display": typo.get("display", "Newsreader"),
        "font_body": typo.get("body", "Geist"),
        "font_mono": typo.get("mono", "JetBrains Mono"),
        "font_tagline": typo.get("tagline", "Instrument Serif"),  # end-card italic serif
        # voice
        "voice_id": voice.get("voice_id", "en-US-AndrewNeural"),
        "voice_rate": voice.get("rate", "+0%"),
        # backdrop
        "backdrop_source": backdrop.get("source", "assets/backdrop.jpg"),
        "backdrop_blur": str(backdrop.get("blur", 4)),
        "backdrop_darken": str(backdrop.get("darken", 0.55)),
        # scenes
        "speedup": str(scenes.get("speedup", 1.20)),
        "crossfade": str(scenes.get("crossfade_seconds", 0.6)),
        # end cards
        "tagline": cards.get("tagline", "Memory that compounds."),
        "spec_line_dotted": cards.get("spec_line", "encrypted · multi-agent · mcp-native"),
        "url_pill": cards.get("url_pill", url),
    }

    # spec_line_html: split on middot, rejoin with styled dot spans
    spec_raw = subs["spec_line_dotted"]
    parts = [p.strip() for p in re.split(r"[·•|]", spec_raw) if p.strip()]
    subs["spec_line_html"] = '<span class="dot">·</span>'.join(parts)

    # P1-3: build the Google Fonts <link> from typography (templates reference
    # {{google_fonts_link}} instead of a hardcoded link, so display/body/mono actually load).
    fonts_url, fonts_unknown = build_google_fonts_link(
        [subs["font_display"], subs["font_tagline"], subs["font_body"], subs["font_mono"]]
    )
    subs["google_fonts_link"] = (
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        f'<link href="{fonts_url}" rel="stylesheet">'
    )
    if fonts_unknown:
        print(f"WARNING: fonts not in the known axis table (requesting regular weight "
              f"only — add to FONT_SPECS for italic/weights): {sorted(fonts_unknown)}",
              file=sys.stderr)

    return subs, mem


def render(text, subs):
    """Replace {{key}} with subs[key]. Unknown placeholders left as-is (with warning)."""
    missing = set()

    def repl(m):
        key = m.group(1).strip()
        if key in subs:
            return str(subs[key])
        missing.add(key)
        return m.group(0)

    out = re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", repl, text)
    return out, missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default="brand.yaml")
    ap.add_argument("--templates", default="templates")
    ap.add_argument("--out", default=".build")
    args = ap.parse_args()

    if not os.path.exists(args.brand):
        sys.exit(f"Missing {args.brand} — run /demo-video init or copy assets/brand.example.yaml")

    with open(args.brand, encoding="utf-8") as f:
        brand = yaml.safe_load(f)

    subs, mem = build_substitutions(brand)

    # Render all templates → .build/ (FLATTENED — tapes land alongside html/display.sh
    # so VHS `bash display.sh <scene>` resolves from a single working dir)
    os.makedirs(args.out, exist_ok=True)
    rendered = []
    all_missing = set()
    for root, _dirs, files in os.walk(args.templates):
        for fn in files:
            src = os.path.join(root, fn)
            dst = os.path.join(args.out, fn)   # flatten: ignore subdir
            with open(src, encoding="utf-8") as f:
                text = f.read()
            out_text, missing = render(text, subs)
            all_missing |= missing
            # LF newlines — rendered .sh/.tape run in Linux bash (Docker VHS); CRLF breaks them
            with open(dst, "w", encoding="utf-8", newline="\n") as f:
                f.write(out_text)
            rendered.append(dst)

    # Also render display.sh (lives in scripts/, templated for ANSI palette)
    display_src = os.path.join("scripts", "display.sh")
    if os.path.exists(display_src):
        with open(display_src, encoding="utf-8") as f:
            text = f.read()
        out_text, missing = render(text, subs)
        all_missing |= missing
        with open(os.path.join(args.out, "display.sh"), "w", encoding="utf-8", newline="\n") as f:
            f.write(out_text)
        rendered.append(os.path.join(args.out, "display.sh"))

    # Emit scene-data.sh — bash-sourceable content for display.sh
    scenes_cfg = brand.get("scenes", {})
    cli_name = scenes_cfg.get("cli_name", "Claude Code")
    cli_subtitle = scenes_cfg.get("cli_subtitle", "Opus (1M context)")
    workdir = scenes_cfg.get("workdir", f"~/{subs['project_name'].lower()}")
    product = subs["project_name"]
    am_user = scenes_cfg.get("amnesia_user_line", "i added the user.role check the way you suggested")
    am_reply = scenes_cfg.get("amnesia_reply", "Hmm, I don't have context on that. Can you share the file and what we discussed?")
    recall_mems = scenes_cfg.get("recall_memories", [
        {"type": "fact", "text": "postgres + drizzle, hono (not express)"},
        {"type": "fact", "text": "pnpm workspaces, vitest, no db mocks"},
        {"type": "preference", "text": "composition over inheritance"},
        {"type": "decision", "text": "moved from express → hono (2025-11-04)"},
        {"type": "project", "text": "yesterday: user.role check in middleware"},
    ])
    agents = scenes_cfg.get("agents", [
        {"name": "Claude Code", "sigil": "▦", "subtitle": "Opus"},
        {"name": "Cursor", "sigil": "▸", "subtitle": "agent mode"},
        {"name": "acme-bot", "sigil": "▢", "subtitle": "custom CLI"},
    ])

    def bash_array(name, items):
        quoted = " ".join("'" + str(x).replace("'", "'\\''") + "'" for x in items)
        return f"{name}=({quoted})\n"

    # Wrap amnesia reply at ~52 chars into two lines for terminal display
    am_words = am_reply.split()
    line1, line2 = "", ""
    for w in am_words:
        if len(line1) + len(w) + 1 <= 52 or not line1:
            line1 += (" " if line1 else "") + w
        else:
            line2 += (" " if line2 else "") + w

    scene_data = "#!/usr/bin/env bash\n# Generated by apply-brand.py — do not edit\n"
    scene_data += f"CLI_NAME='{cli_name}'\n"
    scene_data += f"CLI_SUBTITLE='{cli_subtitle}'\n"
    scene_data += f"WORKDIR='{workdir}'\n"
    scene_data += f"PRODUCT='{product}'\n"
    scene_data += f"AMNESIA_USER='{am_user.replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'\n"
    scene_data += f"AMNESIA_REPLY1='{line1.replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'\n"
    scene_data += f"AMNESIA_REPLY2='{line2.replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'\n"
    scene_data += bash_array("MEM_TYPES", [m["type"] for m in recall_mems])
    scene_data += bash_array("MEM_TEXTS", [m["text"] for m in recall_mems])
    scene_data += bash_array("AGENT_NAMES", [a["name"] for a in agents])
    scene_data += bash_array("AGENT_SIGILS", [a.get("sigil", "▦") for a in agents])
    scene_data += bash_array("AGENT_SUBS", [a.get("subtitle", "") for a in agents])
    with open(os.path.join(args.out, "scene-data.sh"), "w", encoding="utf-8", newline="\n") as f:
        f.write(scene_data)
    rendered.append(os.path.join(args.out, "scene-data.sh"))

    # Emit config.json for runtime scripts
    config = {
        "subs": subs,
        "voiceover": brand.get("voiceover", []),
        "voice": brand.get("voice", {}),
        "scenes": brand.get("scenes", {}),
        "palette": brand.get("palette", {}),
        "memory_colors": mem,
        "project": brand.get("project", {}),
        "music": brand.get("music", {"mode": "procedural", "volume": 0.45}),
        "auth": brand.get("auth", {}),  # P2-1: optional login flow for make-auth.mjs
    }
    with open(os.path.join(args.out, "config.json"), "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    print(f"Rendered {len(rendered)} files -> {args.out}/")
    print(f"Config -> {args.out}/config.json ({len(config['voiceover'])} VO lines)")
    if all_missing:
        print(f"WARNING: unknown placeholders left as-is: {sorted(all_missing)}", file=sys.stderr)


if __name__ == "__main__":
    main()
