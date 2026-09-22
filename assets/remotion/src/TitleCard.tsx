import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { withBrandDefaults, type BrandProps } from "./brand";

export type TitleCardProps = {
  brand?: Partial<BrandProps>;
  props?: { title?: string; subtitle?: string };
};

export const TitleCard: React.FC<TitleCardProps> = ({ brand, props }) => {
  const frame = useCurrentFrame();
  const b = withBrandDefaults(brand);
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
