# Setup and prerequisites

| Tool | Linux (apt) | macOS / Windows | Needed for |
|---|---|---|---|
| **ffmpeg** | `sudo apt install ffmpeg` | `brew install ffmpeg` / `winget install Gyan.FFmpeg` | everything |
| **Python 3.10+** | `python3` (preinstalled) | system | full film (`--plan` too) |
| **pyyaml** | `sudo apt install python3-yaml`, or pip in a venv | pip | full film (`--plan` too) |
| **edge-tts** | pip in a venv (below) | `pip install edge-tts` | voiceover |
| **Node 18+** | nodesource / nvm | system | Playwright recorder |
| **playwright** | `cd demo-video && npm install && npx playwright install chromium` (pnpm works too) | same | quick capture + every film |
| **VHS** (Charm) | `sudo apt install vhs` (Charm apt repo) | `brew install vhs` / `winget install charmbracelet.vhs` | **only** terminal/multi-agent scenes |
| **Docker** (alt) | system | system | VHS via container |

Python packages: `pip install --user` fails on PEP 668 distros (Debian/Ubuntu "externally-managed-environment"). Use a venv:

```bash
python3 -m venv .venv && .venv/bin/pip install pyyaml edge-tts
PYTHON=$PWD/.venv/bin/python bash scripts/build.sh     # or: source .venv/bin/activate
```

The scripts use `$PYTHON`, else `python3`, else `python`. `build.sh` checks all prerequisites
(arc-aware: VHS only when needed) and prints the install command for anything missing.
Pillow is **not** a dependency: inspect frames with ffmpeg (see Quick capture), not PIL.
