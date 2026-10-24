# Critical gotchas (must apply, do not skip)

These were discovered the hard way building the reference implementation. The bundled scripts already encode them but if the agent regenerates from scratch, re-apply:

| Gotcha | Fix |
|---|---|
| **HTML pages record as WHITE flashes** at start because Playwright captures pre-CSS frames | (a) Inline `style="background:#0a0705"` on `<html>`. (b) `-ss` trim in ffmpeg conversion. For `html_mockup` scenes the recorder now ALSO injects the palette bg before first paint automatically (P2-3), so a mockup that forgets the inline bg won't flash. |
| **First capture of a cold dev-server route shows "Rendering…"** (Next compiles on first hit) | `browser_capture` warms the route in a separate non-recording context before recording (P2-2). Default on for `localhost`, off for public sites; override per-scene with `warmup: true|false`. |
| **Brand fonts don't load / wrong font on end card** | The Google Fonts `<link>` is generated from `typography.{display,body,mono,tagline}` (P1-3). Google `css2` is strict — an unsupported axis 400s the whole request — so `apply-brand.py` keeps a per-family axis table (`FONT_SPECS`); unknown families load regular-only and print a warning. Add new families there. |
| **Audio truncates video** to voice length (~45s) instead of full 50s, causing white tail | `apad` on voice + `duration=first` on amix in `mix-final.sh`. Never use `-shortest` for the final mux. |
| **record-graph.mjs picks endcards.webm alphabetically** when both exist | Delete `graph.webm` and `graph.mp4` at start of script. Filter webm list by mtime, not name. |
| **VHS terminal pre-CSS shows white** during VHS startup | Use bash here-doc to print Vellum theme + clear screen before any content prints |
| **Embedded `<video>` in Playwright headless plays at ~20% speed** due to throttling | Don't embed video in Playwright. Use ffmpeg `overlay` filter to composite source video onto a Playwright-captured PNG of the frame chrome. |
| **Edge TTS WordBoundary events don't fire by default** | Pass `boundary="WordBoundary"` to `edge_tts.Communicate(...)` |
| **Scene crossfade offsets drift** when scene durations change | `assemble.sh` reads actual normalized durations via ffprobe before computing xfade offsets, never hardcodes |
| **VO timing drifts from scenes** | `check-timing.py` now checks this automatically on every build (Problem B): it maps each VO line to the scene it starts in and warns (never fails the build) if the line overruns that scene's window, including the internal BEFORE/AFTER cut inside a composite `before_after` scene. No hand-run script needed -- if a warning prints, adjust `pause_after` values in `brand.yaml` and regenerate VO. |
| **Karaoke captions wash out on light app UI** (`browser_capture` / `html_mockup` scenes) | Use `BorderStyle=3` opaque box. The box colour goes in the **`OutlineColour` slot** (libass draws the BorderStyle=3 box from OutlineColour, NOT BackColour) and **must be fully opaque (alpha `00`)** — a semi-transparent box overlaps at the per-word `\k` seams and doubles up into ugly darker vertical bands. Set box colour = `palette_bg` so it blends invisibly on dark terminal scenes but reads as a solid bar over light UI. |
