import { Composition } from "remotion";
import { TitleCard, type TitleCardProps } from "./TitleCard";
import { defaultBrand } from "./brand";

// plan-scenes.py writes remotion_props to a JSON file and passes it via
// --props=<file> (build-scenes.sh); calculateMetadata reads it back here so
// the composition's frame count/fps/size always match what the scene plan
// (and therefore scene_cache/assemble.sh's crossfade math) expects.
type RemotionProps = TitleCardProps & {
  composition?: string;
  durationInFrames: number;
  fps: number;
  width: number;
  height: number;
};

const defaultProps: RemotionProps = {
  composition: "TitleCard",
  durationInFrames: 150,
  fps: 30,
  width: 1920,
  height: 1080,
  brand: defaultBrand,
  props: {},
};

export const Root: React.FC = () => {
  return (
    <Composition
      id="TitleCard"
      component={TitleCard}
      durationInFrames={defaultProps.durationInFrames}
      fps={defaultProps.fps}
      width={defaultProps.width}
      height={defaultProps.height}
      defaultProps={defaultProps}
      calculateMetadata={async ({ props }) => {
        const p = props as RemotionProps;
        return {
          durationInFrames: p.durationInFrames,
          fps: p.fps,
          width: p.width,
          height: p.height,
        };
      }}
    />
  );
};
