import React from "react";
import {
  AbsoluteFill,
  Easing,
  Freeze,
  interpolate,
  OffthreadVideo,
  Sequence,
  staticFile,
  useCurrentFrame,
} from "remotion";
import { Phone } from "../Phone";
import { c, font } from "../theme";
import { FEATURE_NAMES, type AppScene as AppSceneData, type Label } from "./scenes";
import { VoiceTrack } from "./Subtitles";
import { srcToOut, VIEW_H, VIEW_W, type ScenePlan, type Segment } from "./timeline";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const ease = Easing.bezier(0.33, 0, 0.2, 1);

// Màn điện thoại theo đúng tỉ lệ viewport 390×844.
export const SCREEN_H = 960;
export const K = SCREEN_H / VIEW_H;
export const SCREEN_W = VIEW_W * K;
const BEZEL = 12;
const PHONE_LEFT = 1920 - 150 - (SCREEN_W + BEZEL * 2);
const PHONE_TOP = (1080 - (SCREEN_H + BEZEL * 2)) / 2;
const COL_LEFT = 110;
const COL_W = PHONE_LEFT - COL_LEFT - 90;

export const Night: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <AbsoluteFill
    style={{
      background: `radial-gradient(1200px 800px at 75% 40%, ${c.nightSoft}, ${c.night})`,
      fontFamily: font,
    }}
  >
    {children}
  </AbsoluteFill>
);

const fadeWindow = (fr: number, a: number, b: number, edge = 8) =>
  b - a < edge * 2
    ? interpolate(fr, [a, a + 1], [0, 1], clamp)
    : interpolate(fr, [a, a + edge, b - edge, b], [0, 1, 1, 0], clamp);

const ClipVideo: React.FC<{ src: string; segments: Segment[]; editedLen: number; lastSrc: number; duration: number }> = ({
  src,
  segments,
  editedLen,
  lastSrc,
  duration,
}) => {
  const style: React.CSSProperties = { width: VIEW_W, height: VIEW_H, display: "block" };
  return (
    <>
      {segments.map((s, i) => (
        <Sequence key={i} from={s.outFrom} durationInFrames={s.outLen} name={`clip ×${s.rate}`}>
          <OffthreadVideo src={staticFile(src)} trimBefore={s.srcFrom} playbackRate={s.rate} muted style={style} />
        </Sequence>
      ))}
      {editedLen < duration && (
        <Sequence from={editedLen} durationInFrames={duration - editedLen} name="clip freeze">
          <Freeze frame={0}>
            <OffthreadVideo src={staticFile(src)} trimBefore={lastSrc} muted style={style} />
          </Freeze>
        </Sequence>
      )}
    </>
  );
};

/** Ô chờ khi chưa có clip: lưới 100 CSS px để đối chiếu toạ độ box/tap. */
const Placeholder: React.FC<{ src: string }> = ({ src }) => (
  <AbsoluteFill style={{ background: "#1d1424", fontFamily: font }}>
    <svg width={VIEW_W} height={VIEW_H} style={{ position: "absolute", inset: 0 }}>
      {Array.from({ length: 9 }, (_, i) => (
        <line key={`h${i}`} x1={0} x2={VIEW_W} y1={(i + 1) * 100} y2={(i + 1) * 100} stroke="#ffffff14" />
      ))}
      {Array.from({ length: 3 }, (_, i) => (
        <line key={`v${i}`} y1={0} y2={VIEW_H} x1={(i + 1) * 100} x2={(i + 1) * 100} stroke="#ffffff14" />
      ))}
      {Array.from({ length: 8 }, (_, i) => (
        <text key={`t${i}`} x={18} y={(i + 1) * 100 - 6} fill="#ffffff40" fontSize={11}>
          {(i + 1) * 100}
        </text>
      ))}
      <rect x={10} y={10} width={VIEW_W - 20} height={VIEW_H - 20} rx={24} fill="none" stroke={c.brand} strokeWidth={2} strokeDasharray="10 8" />
    </svg>
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", textAlign: "center", color: "#cdbfd6" }}>
      <div style={{ fontSize: 22, fontWeight: 600 }}>Screen recording</div>
      <div style={{ fontSize: 16, marginTop: 8, color: "#8a7b93" }}>{src} · pending</div>
    </AbsoluteFill>
  </AbsoluteFill>
);

const Taps: React.FC<{ fr: number; plan: ScenePlan; data: AppSceneData; s: number }> = ({ fr, plan, data, s }) => (
  <>
    {(data.clip.taps ?? []).map((t, i) => {
      const at = srcToOut(plan.clip?.segments ?? null, t.t);
      const l = fr - at;
      if (l < -6 || l > 24) return null;
      const r = interpolate(l, [-6, 0, 24], [26, 16, 40], clamp) / s;
      const o = interpolate(l, [-6, 0, 10, 24], [0, 1, 0.9, 0], clamp);
      return (
        <div
          key={i}
          style={{
            position: "absolute",
            left: t.x - r,
            top: t.y - r,
            width: r * 2,
            height: r * 2,
            borderRadius: r,
            border: `${3 / s}px solid white`,
            background: l < 6 ? "rgba(255,255,255,0.45)" : "transparent",
            boxShadow: `0 0 ${12 / s}px rgba(200,32,126,0.9)`,
            opacity: o,
          }}
        />
      );
    })}
  </>
);

/**
 * Spotlight: làm tối phần ngoài hộp (đen 55%) với lỗ bo tròn quanh hộp, cộng khung viền hồng có quầng sáng và một nhịp
 * nảy lúc hiện. Màn app không zoom, không cắt. `to` bỏ trống = tới hết cảnh (kể cả lúc đứng hình ở khung cuối).
 */
const Spotlights: React.FC<{ fr: number; plan: ScenePlan; data: AppSceneData }> = ({ fr, plan, data }) => {
  const segs = plan.clip?.segments ?? null;
  return (
    <>
      {(data.clip.spotlights ?? []).map((sp, i) => {
        const a = srcToOut(segs, sp.from);
        const b = sp.to == null ? plan.duration : srcToOut(segs, sp.to);
        if (fr < a - 1 || fr > b + 1) return null;
        const edge = Math.min(8, Math.floor((b - a) / 2));
        const o = interpolate(fr, [a, a + edge, b - edge, b], [0, 1, 1, 0], clamp);
        const pulse = interpolate(fr - a, [0, 7, 14], [1.05, 0.985, 1], clamp);
        const pad = sp.pad ?? 7;
        const rect: React.CSSProperties = {
          position: "absolute",
          left: sp.box.x - pad,
          top: sp.box.y - pad,
          width: sp.box.w + pad * 2,
          height: sp.box.h + pad * 2,
          borderRadius: 14,
        };
        return (
          <React.Fragment key={i}>
            <div style={{ ...rect, boxShadow: `0 0 0 2000px rgba(0,0,0,${0.55 * o})` }} />
            <div
              style={{
                ...rect,
                boxSizing: "border-box",
                border: `3.5px solid ${c.brandVivid}`,
                boxShadow: `0 0 16px rgba(216,45,139,0.85), inset 0 0 10px rgba(216,45,139,0.35)`,
                opacity: o,
                scale: String(pulse),
              }}
            />
          </React.Fragment>
        );
      })}
    </>
  );
};

const SpedUp: React.FC<{ fr: number; plan: ScenePlan }> = ({ fr, plan }) => {
  const seg = plan.clip?.segments.find((s) => s.rate > 1 && fr >= s.outFrom - 4 && fr < s.outFrom + s.outLen + 4);
  if (!seg) return null;
  const o = interpolate(fr, [seg.outFrom - 4, seg.outFrom + 4, seg.outFrom + seg.outLen - 4, seg.outFrom + seg.outLen + 4], [0, 1, 1, 0], clamp);
  const rate = Number.isInteger(seg.rate) ? seg.rate : seg.rate.toFixed(1);
  return (
    <div
      style={{
        position: "absolute",
        right: 1920 - PHONE_LEFT + 28,
        top: PHONE_TOP + 24,
        padding: "8px 18px",
        borderRadius: 999,
        background: "rgba(255,255,255,0.1)",
        border: "1px solid rgba(255,255,255,0.25)",
        color: "#e9dff0",
        fontSize: 24,
        fontWeight: 600,
        display: "flex",
        alignItems: "center",
        gap: 10,
        opacity: o,
      }}
    >
      <svg width={22} height={16} viewBox="0 0 22 16">
        <path d="M1 1 L10 8 L1 15 Z M11 1 L20 8 L11 15 Z" fill="#e9dff0" />
      </svg>
      real agent · sped up ×{rate}
    </div>
  );
};

const Labels: React.FC<{ fr: number; plan: ScenePlan; labels: Label[]; duration: number }> = ({ fr, plan, labels, duration }) => {
  const segs = plan.clip?.segments ?? null;
  const shown = labels
    .map((l, i) => {
      const a = l.from == null ? 0 : srcToOut(segs, l.from);
      const b = l.to == null ? duration : srcToOut(segs, l.to);
      return { l, i, o: l.from == null && l.to == null ? interpolate(fr, [10 + i * 6, 24 + i * 6], [0, 1], clamp) : fadeWindow(fr, a, b) };
    })
    .filter((x) => x.o > 0);
  if (!shown.length) return null;
  return (
    <div style={{ position: "absolute", left: COL_LEFT, top: 452, width: COL_W }}>
      <div style={{ fontSize: 22, letterSpacing: 2, color: "#8a7b93", fontWeight: 600, marginBottom: 14 }}>ON SCREEN</div>
      {shown.map(({ l, i, o }) => (
        <div
          key={i}
          style={{
            display: "flex",
            alignItems: "baseline",
            gap: 18,
            fontSize: 34,
            padding: "10px 0",
            borderBottom: "1px solid rgba(255,255,255,0.08)",
            opacity: o,
            translate: `${interpolate(o, [0, 1], [-24, 0])}px 0px`,
          }}
        >
          <span style={{ color: "#ff9fd0", fontWeight: 600 }}>{l.vi}</span>
          <span style={{ color: "#8a7b93" }}>→</span>
          <span style={{ color: "white" }}>{l.en}</span>
        </div>
      ))}
    </div>
  );
};

const NightlyCard: React.FC<{ fr: number; plan: ScenePlan; data: AppSceneData }> = ({ fr, plan, data }) => {
  if (!data.nightly) return null;
  const at =
    data.nightly.at != null
      ? srcToOut(plan.clip?.segments ?? null, data.nightly.at)
      : (plan.voice[1]?.from ?? plan.voice[0]?.from ?? 0);
  const o = interpolate(fr, [at, at + 12], [0, 1], clamp);
  const st = data.nightly.stats;
  return (
    <div
      style={{
        position: "absolute",
        left: COL_LEFT,
        top: 600,
        width: Math.min(COL_W, 820),
        padding: "26px 32px",
        borderRadius: 26,
        background: "rgba(255,255,255,0.07)",
        border: "1px solid rgba(255,255,255,0.14)",
        color: "white",
        opacity: o,
        translate: `0px ${interpolate(o, [0, 1], [24, 0])}px`,
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: 18 }}>
        <span style={{ fontSize: 44, fontWeight: 800 }}>Every night · 02:00</span>
      </div>
      <div style={{ fontSize: 26, color: "#cdbfd6", marginTop: 6 }}>EventBridge Scheduler → Step Functions → forecast for every user</div>
      {st ? (
        <div style={{ display: "flex", flexWrap: "wrap", columnGap: 30, rowGap: 6, marginTop: 18, fontSize: 28 }}>
          <span>
            last {st.runs} runs: <b style={{ color: "#7fe0b0" }}>{st.succeeded}</b> succeeded,{" "}
            <b style={{ color: st.failed ? "#ff8a8f" : "#7fe0b0" }}>{st.failed}</b> failed
          </span>
          <span style={{ color: "#cdbfd6" }}>
            latest {st.latest} · {st.latestSeconds} s
          </span>
        </div>
      ) : (
        <div style={{ marginTop: 18, fontSize: 24, color: "#8a7b93", border: "2px dashed #8a7b9366", borderRadius: 12, padding: "8px 14px" }}>
          run stats from rec/nightly.json (phase 2)
        </div>
      )}
    </div>
  );
};

export const AppScene: React.FC<{ data: AppSceneData; plan: ScenePlan }> = ({ data, plan }) => {
  const fr = useCurrentFrame();
  const intro = interpolate(fr, [0, 16], [0, 1], { ...clamp, easing: ease });
  return (
    <Night>
      {/* Cột trái: tính năng, tiêu đề, nhãn dịch */}
      <div style={{ position: "absolute", left: COL_LEFT, top: 104, width: COL_W, color: "white", opacity: intro }}>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <span
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              fontSize: 22,
              fontWeight: 600,
              padding: "8px 16px",
              borderRadius: 999,
              background: "rgba(47,158,107,0.18)",
              color: "#9be7c2",
            }}
          >
            <span style={{ width: 10, height: 10, borderRadius: 5, background: "#4cd492" }} />
            Real app · on AWS
          </span>
          {data.features.map((f) => (
            <span
              key={f}
              style={{
                fontSize: 22,
                fontWeight: 600,
                padding: "8px 16px",
                borderRadius: 999,
                background: "rgba(200,32,126,0.22)",
                color: "#ffc4e4",
              }}
            >
              {f} · {FEATURE_NAMES[f] ?? f}
            </span>
          ))}
        </div>
        <div style={{ fontSize: 76, fontWeight: 800, lineHeight: 1.08, marginTop: 26, whiteSpace: "pre-line" }}>{data.title}</div>
      </div>
      <Labels fr={fr} plan={plan} labels={data.labels ?? []} duration={plan.duration} />
      <NightlyCard fr={fr} plan={plan} data={data} />
      <SpedUp fr={fr} plan={plan} />

      {/* Điện thoại bên phải */}
      <Phone
        width={SCREEN_W + BEZEL * 2}
        height={SCREEN_H + BEZEL * 2}
        bezel={BEZEL}
        radius={58}
        notch={false}
        screenBackground="#1d1424"
        style={{
          position: "absolute",
          boxSizing: "border-box",
          left: PHONE_LEFT,
          top: PHONE_TOP,
          translate: `0px ${interpolate(intro, [0, 1], [30, 0])}px`,
        }}
      >
        <div style={{ position: "absolute", left: 0, top: 0, width: VIEW_W, height: VIEW_H, transformOrigin: "0 0", scale: String(K) }}>
          {plan.clip ? (
            <ClipVideo {...plan.clip} duration={plan.duration} />
          ) : (
            <Placeholder src={data.clip.src} />
          )}
          <Spotlights fr={fr} plan={plan} data={data} />
          <Taps fr={fr} plan={plan} data={data} s={1} />
        </div>
      </Phone>

      <VoiceTrack voice={plan.voice} area={{ left: COL_LEFT - 20, width: COL_W + 40, bottom: 56 }} />
    </Night>
  );
};
