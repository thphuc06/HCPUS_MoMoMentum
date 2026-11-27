import React from "react";
import { getStaticFiles, staticFile, type CalculateMetadataFunction } from "remotion";
import { fade } from "@remotion/transitions/fade";
import { linearTiming, TransitionSeries } from "@remotion/transitions";
import { AppScene } from "./AppScene";
import { ArchScene } from "./ArchScene";
import { EndScene } from "./EndScene";
import { IntroScene } from "./IntroScene";
import { SCENES, type SceneData } from "./scenes";
import { buildPlan, FPS, TRANSITION_FRAMES, type DemoPlan, type Manifest } from "./timeline";

export type YofinaDemoProps = {
  /** "auto": dùng clip nếu tệp có trong public/; "off": luôn hiện ô chờ (bản nháp giai đoạn 1). */
  clips: "auto" | "off";
  /** Ghi đè dữ liệu từng cảnh theo id (thử nghiệm qua --props, không cần sửa scenes.ts). */
  overrides?: Record<string, Partial<SceneData>>;
  /** Do calculateMetadata điền. */
  plan?: DemoPlan;
  scenes?: SceneData[];
};

export const demoDefaultProps: YofinaDemoProps = { clips: "auto", overrides: {} };

export const calculateDemoMetadata: CalculateMetadataFunction<YofinaDemoProps> = async ({ props }) => {
  const res = await fetch(staticFile("voice/manifest.json"));
  if (!res.ok) throw new Error("Thiếu public/voice/manifest.json: chạy `node scripts/tts.mjs` trước.");
  const manifest = (await res.json()) as Manifest;
  const files = new Set(getStaticFiles().map((f) => f.name.replace(/\\/g, "/")));
  const scenes = SCENES.map((s) => ({ ...s, ...(props.overrides?.[s.id] ?? {}) }) as SceneData);
  const plan = buildPlan(scenes, manifest, (src) => props.clips !== "off" && files.has(src));
  return { durationInFrames: plan.total, fps: FPS, props: { ...props, plan, scenes } };
};

export const YofinaDemo: React.FC<YofinaDemoProps> = ({ plan, scenes }) => {
  if (!plan || !scenes) return null;
  const items: React.ReactNode[] = [];
  scenes.forEach((sc, i) => {
    const p = plan.scenes[i];
    if (i > 0) {
      items.push(
        <TransitionSeries.Transition
          key={`t${i}`}
          presentation={fade()}
          timing={linearTiming({ durationInFrames: TRANSITION_FRAMES })}
        />,
      );
    }
    items.push(
      <TransitionSeries.Sequence key={sc.id} durationInFrames={p.duration} name={`scene ${sc.id}`}>
        {sc.kind === "intro" && <IntroScene data={sc} plan={p} />}
        {sc.kind === "app" && <AppScene data={sc} plan={p} />}
        {sc.kind === "arch" && <ArchScene plan={p} />}
        {sc.kind === "end" && <EndScene data={sc} plan={p} />}
      </TransitionSeries.Sequence>,
    );
  });
  return <TransitionSeries>{items}</TransitionSeries>;
};
