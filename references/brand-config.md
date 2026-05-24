# brand.yaml — full schema + tuning guide

The `brand.yaml` is the single source of truth for everything visual + auditory in your demo video.

## Quick recipes

### "I want to swap the orange to teal"
```yaml
palette:
  accent: "#5eb0a0"           # teal instead of brass
  end_card_bg: "#0e1f1c"      # cooler dark bg
```

### "I want a female narrator instead"
```yaml
voice:
  voice_id: "en-US-AriaNeural"      # warm, conversational
  # or: en-US-JennyNeural (newscaster), en-GB-SoniaNeural (UK), en-AU-NatashaNeural (AUS)
```

### "I want it shorter — 30s instead of 50s"
```yaml
scenes:
  speedup: 1.50               # was 1.20
voiceover:
  # cut 5 lines, target ~50 words instead of ~80
  - { text: "Every session starts blank.", pause_after: 0.8 }
  ...
```

### "I want a different backdrop photo"
Browse Unsplash → "workspace by window" / "developer desk" / etc.
Click photo → copy URL → drop into `brand.yaml`:
```yaml
backdrop:
  source: "https://images.unsplash.com/photo-XXXX?w=1920&h=1080&fit=crop&q=85"
```
Or download manually to `assets/backdrop.jpg`.

## Full schema

### `project`
```yaml
project:
  name: "MyProduct"           # used in terminal headers
  url: "myproduct.com"        # used in title bar + end card
  version_tag: "v0.1.mp4"     # shown in title bar (good for iteration tracking)
```

### `palette`
```yaml
palette:
  bg:          "#0a0705"      # terminal bg (warm dark; avoid pure black)
  fg:          "#dcd7cf"      # text foreground (cream; avoid pure white)
  fg_lo:       "#a9a49c"      # dim text (subheadings, paths)
  fg_faint:    "#7a736c"      # faintest (timestamps, labels)
  accent:      "#dbaf71"      # cursor, links, highlights
  rule:        "#29231f"      # subtle dividers
  end_card_bg: "#1e1714"      # end card (can differ from terminal)

  memory_type_colors:         # only used in knowledge graph scene
    fact:        "#c9a471"
    skill:       "#84b385"
    decision:    "#c37b7d"
    preference:  "#d0c3a7"
    constraint:  "#7a8ea8"
    correction:  "#d3896c"
    episodic:    "#a18cc8"
    task:        "#c3b16d"
```

**Palette principles** (Anthropic-style):
- Warm dark backgrounds, never pure black (`#000`)
- Cream foregrounds, never pure white (`#fff`)
- ONE accent color used sparingly
- Avoid blue/purple "techie" defaults — use warm earth tones

### `logo`
```yaml
logo:
  svg_inline: |
    <svg viewBox="0 0 600 400" width="260" height="170">
      <!-- your SVG markup here -->
    </svg>
  wordmark_italic: "Exo"
  wordmark_roman:  "Vault"
  # OR: wordmark_full: "MyProduct"   (skip italic/roman split)
```

**Logo tips**:
- Use viewBox 600×400 for orbital/atomic logos
- Keep stroke widths between 2.5-4 (looks good at 260px render)
- Use 2 colors max — match `accent` and `fg_hi`
- For complex logos, just paste full SVG into `svg_inline`

### `typography`
```yaml
typography:
  display: "Newsreader"          # end-card wordmark serif
  body:    "Geist"               # UI sans (only used in HUD overlays)
  mono:    "JetBrains Mono"      # terminals + spec line
```

**Pairings that work**:
- `Newsreader` + `Geist` + `JetBrains Mono` (editorial, scholarly — ExoVault Vellum style)
- `Inter` + `Inter` + `JetBrains Mono` (modern, neutral)
- `Crimson Pro` + `IBM Plex Sans` + `IBM Plex Mono` (academic)
- `Instrument Serif` + `Manrope` + `Fira Code` (warm, friendly)

All fonts are auto-loaded from Google Fonts.

### `voice`
```yaml
voice:
  provider: "edge-tts"
  voice_id: "en-US-AndrewNeural"
  rate: "+0%"                    # -10% slower, +10% faster
  leading_silence: 0.2           # seconds of silence before first word
```

**Top voice picks**:
| voice_id | Tone | Best for |
|---|---|---|
| `en-US-AndrewNeural` | Warm, confident, authentic | Default. Anthropic-style narration. |
| `en-US-ChristopherNeural` | Reliable, authority | Enterprise / B2B |
| `en-US-EricNeural` | Rational, calm | Technical demos |
| `en-US-AriaNeural` | Friendly, conversational | Consumer apps |
| `en-US-JennyNeural` | Newscaster | Polished announcements |
| `en-US-SteffanNeural` | Storyteller | Long-form |
| `en-GB-RyanNeural` | UK male, refined | International polish |

Full list: https://gist.github.com/BettyJJ/17cbaa1de96235a7f5773b8690a20462

### `backdrop`
```yaml
backdrop:
  type:   "image"                # "image" | "color" | "gradient"
  source: "assets/backdrop.jpg"  # path or Unsplash URL
  blur:    4                     # 0-10 (depth-of-field)
  darken:  0.55                  # 0-1 (darkening overlay)
```

### `scenes`
```yaml
scenes:
  speedup:           1.20        # 1.0 realtime, 1.30 fast, 0.85 slow
  crossfade_seconds: 0.6         # transition time between scenes
  arc:              "memory-product-default"
```

Available arcs:
- `memory-product-default` — hero → typing → amnesia → graph → recall → multi-agent → endcards (memory/persistence narrative)
- `feature-launch` — hero → before → problem → reveal → benefit → cta → endcards (single-feature spotlight) [TODO]
- `tutorial-quickstart` — install → setup → first-run → result (how-to flow) [TODO]
- `custom` — define your own in `scenes/custom.yaml`

### `voiceover`
```yaml
voiceover:
  - { text: "Every session starts the same way.", pause_after: 1.1 }
  - { text: "You explain your stack.",            pause_after: 0.3 }
  # ...
```

**Writing principles**:
- **Short sentences.** 8-12 words max. Pauses do the work of commas.
- **Pace ~115 wpm.** Edge TTS at `+0%` is about right; +5% if you want tighter.
- **Pauses are emotional beats.** `pause_after: 2.0` = "let it land".
- **Last line = thesis, not CTA.** "Memory that compounds." > "Try ExoVault today!"
- **Total ~75-90 words** for a 50s video, leaving ~5s outro hold.

### `end_cards`
```yaml
end_cards:
  tagline:   "Memory that compounds."           # italic serif, large
  spec_line: "encrypted · multi-agent · mcp-native"  # 3 dots, uppercase, small mono
  url_pill:  "myproduct.com"                    # at bottom, in pill border
```

**Tagline patterns that work**:
- `<Noun> that <verb>.` (e.g. "Memory that compounds.")
- `<Outcome>, without <pain>.` (e.g. "Persistent context, without prompts.")
- `<Action>. <Result>.` (e.g. "Save. Recall. Build.")

Keep it under 5 words.
