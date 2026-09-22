import { AbsoluteFill, continueRender, delayRender, interpolate, useCurrentFrame } from "remotion";
import { useEffect, useState } from "react";
import { withBrandDefaults, type BrandProps } from "./brand";

export type TitleCardProps = {
  brand?: Partial<BrandProps>;
  props?: { title?: string; subtitle?: string };
};

// A missing/slow network must never hang the render -- race document.fonts.ready
// against a fixed timeout and continue either way (a late-loading font just means
// this one frame falls back to the platform default, not a stuck render).
const FONT_LOAD_TIMEOUT_MS = 4000;

function useGoogleFontsReady(url: string | null | undefined): void {
  const [handle] = useState(() => delayRender(`Loading Google Fonts: ${url ?? "(none)"}`));
  useEffect(() => {
    if (!url) {
      continueRender(handle);
      return;
    }
    const fontsReady =
      typeof document !== "undefined" && document.fonts
        ? document.fonts.ready
        : Promise.resolve();
    const timeout = new Promise<void>((resolve) => setTimeout(resolve, FONT_LOAD_TIMEOUT_MS));
    Promise.race([fontsReady, timeout]).then(() => continueRender(handle));
    // no cleanup: continueRender must fire exactly once per delayRender handle,
    // even if this effect re-runs (React StrictMode double-invoke) -- calling it
    // twice for the same handle is a Remotion render error, so this intentionally
    // does NOT re-delay/cancel on cleanup.
  }, [handle, url]);
}

export const TitleCard: React.FC<TitleCardProps> = ({ brand, props }) => {
  const frame = useCurrentFrame();
  const b = withBrandDefaults(brand);
  useGoogleFontsReady(b.fonts.google_fonts_url);
  const opacity = interpolate(frame, [0, 15], [0, 1], { extrapolateRight: "clamp" });
  const title = props?.title ?? b.project_name;
  const subtitle = props?.subtitle ?? b.project_url;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: b.palette.bg ?? "#0a0705",
        color: b.palette.fg ?? "#dcd7cf",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        opacity,
      }}
    >
      {b.fonts.google_fonts_url && <link rel="stylesheet" href={b.fonts.google_fonts_url} />}
      <div style={{ fontFamily: b.fonts.display, fontSize: 96, fontWeight: 500 }}>{title}</div>
      <div
        style={{
          fontFamily: b.fonts.tagline,
          fontStyle: "italic",
          fontSize: 36,
          marginTop: 24,
          color: b.palette.accent ?? "#dbaf71",
        }}
      >
        {subtitle}
      </div>
    </AbsoluteFill>
  );
};
