import { AbsoluteFill, continueRender, delayRender, interpolate, useCurrentFrame } from "remotion";
import { useEffect, useRef, useState } from "react";
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
  // A2.5: continueRender must fire AT MOST ONCE for this handle. Without this
  // guard, an effect re-run (e.g. `url` changes, or React StrictMode's
  // double-invoke) starts a SECOND race while the first one's promise is
  // still pending; when both eventually resolve, continueRender(handle)
  // would be called twice for the same handle, which Remotion treats as an
  // error. The ref (not state) means the guard itself never triggers a
  // re-render or a further effect run.
  const continuedRef = useRef(false);

  useEffect(() => {
    const continueOnce = () => {
      if (continuedRef.current) return;
      continuedRef.current = true;
      continueRender(handle);
    };
    if (!url) {
      continueOnce();
      return;
    }
    const fontsReady =
      typeof document !== "undefined" && document.fonts
        ? document.fonts.ready
        : Promise.resolve();
    const timeout = new Promise<void>((resolve) => setTimeout(resolve, FONT_LOAD_TIMEOUT_MS));
    Promise.race([fontsReady, timeout]).then(continueOnce);
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
