# claude-demo-video

> Produce a ~50-second product demo video — voiceover, karaoke captions, knowledge-graph animation, terminal scenes, and a real-photo terminal-on-desk backdrop. Single `brand.yaml` drives the whole thing. Zero paid services.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Status: alpha](https://img.shields.io/badge/status-alpha-orange)]()

## What you get

A single `videos/final-framed.mp4` (1920×1080, ~50s, ~3 MB) containing:

- **7-scene story arc** — hero → typing → amnesia → knowledge-graph → memory recall → multi-agent split → end cards
- **AI voiceover** via Microsoft Edge TTS (free, no API key)
- **Karaoke word-highlight captions** synced to voice via `WordBoundary` events
- **Procedural ambient music bed** (placeholder — swap with real CC0 track for production)
- **Terminal-on-desk treatment** — the demo plays inside a styled terminal window composited on a real workspace photo

Built entirely with **free tools** — `ffmpeg`, Playwright headless Chromium, VHS (Charm), `edge-tts`.

## Install (local testing)

This is a Claude Code plugin. Three install paths:

### A. Direct from a local clone (recommended for testing)

```bash
git clone https://github.com/MarcinSufa/claude-demo-video
# In Claude Code:
/plugin install file:///absolute/path/to/claude-demo-video
```

### B. Via local marketplace

```bash
# In Claude Code (point at your local clone):
/plugin marketplace add file:///absolute/path/to/claude-demo-video
/plugin install demo-video@claude-demo-video
```

### C. From GitHub (after publishing)

```bash
/plugin marketplace add MarcinSufa/claude-demo-video
/plugin install demo-video@claude-demo-video
```

## Usage

```bash
# In any project:
/demo-video init        # scaffolds demo-video/ folder with brand.yaml
# (edit brand.yaml — set product name, palette, VO script, etc.)
/demo-video build       # runs full 7-step pipeline → videos/final-framed.mp4
/demo-video preview     # starts local server + cloudflared tunnel for phone review
```

See [SKILL.md](./SKILL.md) for the full workflow.

## Prerequisites

| Tool | Install | Required for |
|---|---|---|
| **ffmpeg** | `winget install Gyan.FFmpeg` / `brew install ffmpeg` / `apt install ffmpeg` | all video/audio operations |
| **Python 3.10+** | system | voiceover + caption scripts |
| **Node 18+ + pnpm** | system | Playwright headless recorder |
| **edge-tts** | `pip install --user edge-tts` | free Microsoft TTS |
| **playwright** | `cd demo-video && pnpm add playwright && pnpm exec playwright install chromium` | HTML scene capture |
| **VHS** (Charm) | `winget install charmbracelet.vhs` / `brew install vhs` | terminal scene recording |
| **Docker** | system | VHS Windows fallback if `vhs` binary unavailable |

The `/demo-video build` command verifies these before running.

## How it works

Pipeline runs 7 steps with caching:

```
make-vo.py        → vo.mp3 + vo-words.json   (Edge TTS streaming with word boundaries)
make-captions.py  → captions.ass + .srt      (karaoke + standard subtitles)
make-music.sh     → music.mp3                (procedural ambient pad)
assemble.sh       → final-rough.mp4          (7 scenes crossfaded, sped 1.20×)
mix-final.sh     → final-with-audio.mp4     (voice + music sidechain-ducked)
burn-captions.sh  → final-with-captions.mp4  (ASS burned into video)
record-frame.mjs  → final-framed.mp4         (terminal-on-desk composite via overlay)
```

See [references/workflow.md](./references/workflow.md) for step-by-step details.

## Configuration

A single `brand.yaml` controls everything:

```yaml
project:
  name: "MyProduct"
  url: "myproduct.com"

palette:
  bg: "#0a0705"
  fg: "#dcd7cf"
  accent: "#dbaf71"

voice:
  voice_id: "en-US-AndrewNeural"   # try ChristopherNeural, EricNeural, AriaNeural
  rate: "+0%"

voiceover:
  - { text: "Every session starts the same way.", pause_after: 1.1 }
  # ... ~15 lines, ~80 words, ~45s of speech
```

Full schema: [references/brand-config.md](./references/brand-config.md).

## Why I built this

After analyzing Anthropic's "Agent view in Claude Code" demo film and trying to reproduce that aesthetic for ExoVault, I burned a weekend rebuilding the pipeline from scratch — Edge TTS sync gotchas, Playwright headless throttling, VHS terminal recording, ffmpeg xfade math, audio sidechain ducking, karaoke caption timing. The setup ended up reusable across projects, so I packaged it.

The trade-off: **looks like a professional product film** without the $500/mo for Synthesia / HeyGen / After Effects subscriptions.

## Known limitations (alpha)

- Skill currently expects a memory/persistence narrative (the "agents forget → ExoVault remembers" arc). Other arcs (`feature-launch`, `tutorial-quickstart`) declared in config but not yet implemented — falls back to default.
- Procedural music sounds OK as placeholder but you should swap with real CC0 track (Pixabay/FMA) before publishing.
- Currently English-only voice. Polish/other languages need updated TTS voice_id + rewritten VO script.
- Windows VHS requires Docker fallback (native binary doesn't exist).

## Troubleshooting

White flashes, sync drift, audio truncation, scene-order bugs → [references/troubleshooting.md](./references/troubleshooting.md).

## License

MIT — see [LICENSE](./LICENSE).

## Author

[Marcin Sufa](mailto:sufa.marcin@gmail.com) · [@smolexander](https://x.com/smolexander)

Built while shipping [ExoVault](https://exovault.co) — encrypted persistent memory for AI agents.
