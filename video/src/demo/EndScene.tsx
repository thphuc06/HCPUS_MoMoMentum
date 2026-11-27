import React from "react";
import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from "remotion";
import { c } from "../theme";
import { Night } from "./AppScene";
import type { EndScene as EndData } from "./scenes";
import { VoiceTrack } from "./Subtitles";
import type { ScenePlan } from "./timeline";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const out = Easing.bezier(0.16, 1, 0.3, 1);

// Cảnh kết: chữ trên hình trùng lời nên không hiện phụ đề.
export const EndScene: React.FC<{ data: EndData; plan: ScenePlan }> = ({ data, plan }) => {
  const fr = useCurrentFrame();
  const t0 = plan.voice[0]?.from ?? 0;
  const t1 = plan.voice[1]?.from ?? t0 + 40;
  const rise = (d: number): React.CSSProperties => ({
    opacity: interpolate(fr, [d - 6, d + 10], [0, 1], clamp),
    translate: interpolate(fr, [d - 6, d + 18], ["0px 30px", "0px 0px"], { ...clamp, easing: out }),
  });
  return (
    <Night>
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", textAlign: "center", color: "white" }}>
        <div style={{ fontSize: 150, fontWeight: 800, letterSpacing: -2, ...rise(t0) }}>
          {data.title.split(" ")[0]} <span style={{ color: c.brandVivid }}>{data.title.split(" ").slice(1).join(" ")}</span>
        </div>
        <div style={{ fontSize: 58, fontWeight: 600, color: "#e9dff0", marginTop: 26, ...rise(t1) }}>{data.tagline}</div>
      </AbsoluteFill>
      <VoiceTrack voice={plan.voice} area={{ left: 260, width: 1400, bottom: 56 }} subtitles={false} />
    </Night>
  );
};
