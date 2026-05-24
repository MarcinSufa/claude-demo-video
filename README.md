# claude-demo-video

> Turn your app into a beautiful ~50-second **feature film** — record your real UI, narrate how it works, and the skill scores it with music, burns in synced captions, and composites it into a polished launch video. One `brand.yaml` drives everything. Zero paid services.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Status: alpha](https://img.shields.io/badge/status-alpha-orange)]()

## What it makes

A single `videos/final-framed.mp4` (1920×1080, ~50s) that shows **how your application works** — in the polished aesthetic of an Anthropic/Linear-style product film:

- 🎬 **Your real app, on screen** — drive a live URL (click, type, scroll, hover) and record the interaction, or render a designed HTML mockup for a feature you haven't built yet, or capture a terminal/CLI. Mix scene types freely.
- 🎙️ **AI voiceover** narrating the feature — Microsoft Edge TTS (free, no API key, many languages/voices).
- 📝 **Karaoke word-highlight captions** synced to the voice, readable on light *and* dark UI.
- 🎵 **Music bed** — procedural ambient pad, your own CC0 track, or none — auto-ducked under the voice.
- 🖼️ **Beautiful framing** — your brand palette, fonts, logo and end cards; the demo can play inside a styled window composited on a real workspace photo.

Built entirely with **free tools** — `ffmpeg`, Playwright headless Chromium, VHS (Charm), `edge-tts`. No Synthesia / HeyGen / After Effects subscription.

## Scene types — compose your own video

You pick the scenes and their order in `brand.yaml` (`scenes.sequence`). Every scene gets the same voiceover, captions, music and framing treatment:

| Scene type | What it does |
|---|---|
| **`browser_capture`** | Drive a **real running app or website** with Playwright — clicks, typing, scrolling, a smooth cursor — and record it. Warms dev-server routes first so you never capture a "loading" frame. |
| **`html_mockup`** | Render a **designed HTML screen** (your palette/fonts) for a feature that doesn't exist yet — no throwaway code in your real app. |
| **`screen_recording`** | Fold in an **existing clip** (Screen Studio, OBS, QuickTime). |
| **`terminal`** | Record a **CLI/terminal** scene via VHS — great for dev tools. |
| **`graph` / `endcards`** | Built-in **knowledge-graph animation** and **branded end cards**. |

Pin any scene to an exact `duration:` for deterministic timing, and run `/demo-video plan` to preview the total length before rendering.

## Install

This is a Claude Code plugin.

```bash
# From GitHub:
/plugin marketplace add MarcinSufa/claude-demo-video
/plugin install demo-video@claude-demo-video
```

<details><summary>Local clone (for development)</summary>

```bash
git clone https://github.com/MarcinSufa/claude-demo-video
# In Claude Code:
/plugin marketplace add file:///absolute/path/to/claude-demo-video
/plugin install demo-video@claude-demo-video
```
</details>

## Usage

```bash
# In your app's repo:
/demo-video init        # scaffolds demo-video/ (brand.yaml, package.json, mockup starter)
# → edit brand.yaml: brand palette/fonts/logo, voiceover script, and the scenes
#   (point browser_capture at your running app, e.g. http://localhost:3000)
/demo-video plan        # ~1s dry run: estimates voiceover vs video length, PASS/WARN
/demo-video build       # runs the pipeline → videos/final-framed.mp4
/demo-video preview     # local server + cloudflared tunnel to review on your phone
```

See [SKILL.md](./SKILL.md) for the full workflow and [references/scene-config.md](./references/scene-config.md) for every scene option.

## Example — a feature launch for a real app

```yaml
project: { name: "Asistel", url: "asistel.io" }
palette: { bg: "#0b0f14", fg: "#e8eef5", accent: "#5eb0a0" }
typography: { display: "Fraunces", body: "Inter", mono: "JetBrains Mono" }
voice:
  voice_id: "en-US-AndrewNeural"     # or pl-PL-MarekNeural, de-DE-..., 100+ voices
  # pronounce: { Asistel: "Assystel" }  # respell English names for a non-English voice

scenes:
  speedup: 1.15
  sequence:
    - { type: browser_capture, url: "http://localhost:3000/dashboard", duration: 7,
        actions: [ { wait: 1 }, { click: "button.new" }, { scroll: 300 } ] }
    - { type: html_mockup, source: "mockups/inventory.html", duration: 6 }   # unbuilt feature
    - endcards

voiceover:
  - { text: "Every order used to mean three phone calls.", pause_after: 1.0 }
  - { text: "Now it's one screen.", pause_after: 0.6 }
  # ... ~12-15 short lines, ~80 words, ~45s of speech

music: { mode: "file", file: "assets/track.mp3" }   # or "procedural" | "none"
end_cards: { tagline: "Orders, handled.", spec_line: "fast · clear · reliable", url_pill: "asistel.io" }
```

Full schema: [references/brand-config.md](./references/brand-config.md) · scene options: [references/scene-config.md](./references/scene-config.md).

## Prerequisites

| Tool | Install | Required for |
|---|---|---|
| **ffmpeg** | `winget install Gyan.FFmpeg` / `brew install ffmpeg` / `apt install ffmpeg` | all video/audio operations |
| **Python 3.10+** | system | voiceover + caption + planning scripts |
| **Node 18+ + pnpm** | system | Playwright recorder (real UI / mockups / end cards) |
| **edge-tts** | `pip install --user edge-tts` | free Microsoft TTS |
| **playwright** | `cd demo-video && pnpm install && pnpm exec playwright install chromium` | UI / HTML / end-card capture (always) |
| **VHS** (Charm) | `winget install charmbracelet.vhs` / `brew install vhs` | **only** if your video has terminal/multi-agent scenes |

`/demo-video build` resolves your scenes first and verifies only the prerequisites your arc actually needs (a pure real-UI video doesn't require VHS).

## How it works

```
apply-brand.py    → compile brand.yaml → .build/ (rendered templates + Google Fonts link)
make-vo.py        → vo.mp3 + vo-words.json     (Edge TTS streaming with word boundaries)
make-captions.py  → captions.ass + .srt        (karaoke + standard subtitles)
make-music.sh     → music.mp3                  (procedural / your file / none)
plan-scenes.py    → scene-plan.json            (resolve your scene sequence)
build-scenes.sh   → one clip per scene         (real UI, mockup, terminal, graph… cached)
assemble.sh       → final-rough.mp4            (scenes crossfaded + sped up)
mix-final.sh      → final-with-audio.mp4       (voice + music ducked; gates VO-overruns-video)
burn-captions.sh  → final-with-captions.mp4    (captions burned in)
record-frame.mjs  → final-framed.mp4           (optional window-on-desk composite)
```

Scene captures are **cached** — edit only the voiceover and the next build reuses every clip. See [references/workflow.md](./references/workflow.md).

## Why I built this

After analyzing Anthropic's "Agent view in Claude Code" film and trying to reproduce that aesthetic, I rebuilt the pipeline from scratch — Edge TTS sync, Playwright capture, ffmpeg xfade math, sidechain ducking, karaoke caption timing — and it ended up reusable across projects, so I packaged it.

The trade-off: **looks like a professional product film** without the monthly subscription for Synthesia / HeyGen / After Effects.

## Status (alpha)

Works end-to-end and is config-driven for any brand. Rough edges:

- Procedural music is a serviceable placeholder — supply a real CC0 track (Pixabay / Free Music Archive / YouTube Audio Library) for production.
- `screen_recording`/auth'd routes are supported but lightly tested; complex OAuth login flows may need an on-camera login.
- Line endings: scripts run fine via the rendered LF outputs; a repo-wide line-ending normalization pass is pending (tracked).

## Troubleshooting

White flashes, sync drift, audio truncation, fonts not loading → [references/troubleshooting.md](./references/troubleshooting.md).

## License

MIT — see [LICENSE](./LICENSE).

## Author

[Marcin Sufa](mailto:sufa.marcin@gmail.com) · [@smolexander](https://x.com/smolexander)

Built while shipping [ExoVault](https://exovault.co) — encrypted persistent memory for AI agents.
