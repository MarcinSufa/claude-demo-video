# remotion/ — optional Remotion scene package

This folder is only needed for `type: remotion` scenes (`scripts/prereqs.py
needs-remotion` gates the build on it). It is NOT copied automatically at
`/demo-video init` — copy it in (or run `/demo-video remotion`) the first
time you add a `remotion` scene, then:

```
cd remotion && pnpm install
```

## Licence

**Remotion is NOT MIT-licensed.** It is free for companies/individuals with
3 or fewer people; larger orgs need a paid licence — see
https://www.remotion.dev/license. This package.json pins exact versions
(`remotion` / `@remotion/cli` 4.0.527, React 19) so a build never silently
picks up a different licence term via a caret/tilde range. Check the current
terms before shipping if your org has grown past the free tier.

## Adding a scene

`plan-scenes.py` writes `remotion_props` (composition id, durationInFrames,
fps, width, height, `brand` from your `brand.yaml` — including
`google_fonts_url`, reusing apply-brand.py's own Google Fonts link builder —
and any per-scene `props:`) to a generated JSON file and renders with
`pnpm exec remotion render src/index.ts <composition> <out.mp4> --props=<file>`.
`src/Root.tsx` registers the `TitleCard` composition and resolves its real
duration/fps/size from those props via `calculateMetadata`. `TitleCard`
injects the Google Fonts stylesheet and holds the render
(`delayRender`/`continueRender`) until `document.fonts.ready` (or a 4s
timeout, so a missing network never hangs the render). Add further
compositions in `src/` the same way (read `brand` for palette/fonts, keep the
id matching what you put in `brand.yaml`'s `composition:`).
