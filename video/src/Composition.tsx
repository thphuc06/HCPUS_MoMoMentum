import { Composition } from "remotion";
import { Story, STORY_FRAMES } from "./Story";
import { calculateDemoMetadata, demoDefaultProps, YofinaDemo } from "./demo/YofinaDemo";

export const MyComposition = () => {
  return (
    <>
      <Composition
        id="YofinaStory"
        component={Story}
        durationInFrames={STORY_FRAMES}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{ demoClip: "" }}
      />
      <Composition
        id="YofinaDemo"
        component={YofinaDemo}
        durationInFrames={30}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={demoDefaultProps}
        calculateMetadata={calculateDemoMetadata}
      />
    </>
  );
};
