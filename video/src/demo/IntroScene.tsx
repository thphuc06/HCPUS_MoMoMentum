import React from "react";
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { c, vnd } from "../theme";
import { Night } from "./AppScene";
import type { IntroScene as IntroData } from "./scenes";
import { VoiceTrack } from "./Subtitles";
import type { ScenePlan } from "./timeline";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const out = Easing.bezier(0.16, 1, 0.3, 1);

/**
 * Cảnh 0, dựng lại từ Story.tsx bằng chữ tiếng Anh. Mốc hình theo câu lời:
 * câu 0 "Minh is twenty-two…" → tiêu đề; câu 1 "Coffee. Lunch…" → các khoản nhỏ trừ dần;
 * câu 2 "His food jar has…" → thẻ hũ và ngày lương; câu 3 "Is that enough?" → "Enough?".
 */
export const IntroScene: React.FC<{ data: IntroData; plan: ScenePlan }> = ({ data, plan }) => {
  const fr = useCurrentFrame();
  const { fps } = useVideoConfig();
  const v = plan.voice;
  const t0 = v[0]?.from ?? 0;
  const t1 = v[1]?.from ?? t0 + 60;
  const t2 = v[2]?.from ?? t1 + 60;
  const t3 = v[3]?.from ?? t2 + 90;
  const spendSpan = Math.max(30, t2 - t1);
  const step = spendSpan / data.spends.length;
  const start = data.balance + data.spends.reduce((a, s) => a + s.amount, 0);
  const spent = data.spends.reduce(
    (a, s, i) => a + s.amount * interpolate(fr, [t1 + i * step, t1 + i * step + 10], [0, 1], clamp),
    0,
  );
  const bal = start - spent;
  const rise = (d: number): React.CSSProperties => ({
    opacity: interpolate(fr, [d, d + 14], [0, 1], clamp),
    translate: interpolate(fr, [d, d + 20], ["0px 26px", "0px 0px"], { ...clamp, easing: out }),
  });
  const dim = interpolate(fr, [t3 - 4, t3 + 10], [1, 0.07], clamp);
  const blur = interpolate(fr, [t3 - 4, t3 + 10], [0, 8], clamp);
  const pop = spring({ frame: fr - t3, fps, config: { damping: 11 } });
  const focus = spring({ frame: fr - t2, fps, config: { damping: 200 } });

  return (
    <Night>
      <div style={{ opacity: dim, filter: `blur(${blur}px)`, position: "absolute", inset: 0 }}>
        <div style={{ position: "absolute", left: 140, top: 110, color: "white" }}>
          <div style={{ fontSize: 34, color: c.brandVivid, fontWeight: 600, ...rise(t0) }}>Minh, 22</div>
          <div style={{ fontSize: 84, fontWeight: 800, marginTop: 10, ...rise(t0 + 8) }}>Small spends, all week.</div>
        </div>
        <div style={{ position: "absolute", left: 140, top: 330, display: "flex", flexDirection: "column", gap: 14 }}>
          {data.spends.map((s, i) => {
            const a = t1 + i * step;
            return (
              <div
                key={s.label}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  width: 640,
                  padding: "18px 30px",
                  borderRadius: 22,
                  background: "rgba(255,255,255,0.07)",
                  color: "white",
                  fontSize: 34,
                  opacity: interpolate(fr, [a, a + 10], [0, 1], clamp),
                  translate: interpolate(fr, [a, a + 14], ["-60px 0px", "0px 0px"], { ...clamp, easing: out }),
                }}
              >
                <span>{s.label}</span>
                <span style={{ color: "#ff9db8", fontWeight: 600 }}>−{vnd(s.amount)}</span>
              </div>
            );
          })}
        </div>
        <div
          style={{
            position: "absolute",
            right: 180,
            top: 300,
            width: 640,
            padding: 50,
            borderRadius: 40,
            background: c.paper,
            color: c.ink,
            opacity: interpolate(fr, [t1 - 10, t1 + 6], [0, 1], clamp),
            scale: String(interpolate(focus, [0, 1], [1, 1.06])),
            boxShadow: `0 30px 90px rgba(200,32,126,${0.15 + 0.3 * focus})`,
          }}
        >
          <div style={{ fontSize: 34, color: c.muted }}>Food jar</div>
          <div style={{ fontSize: 96, fontWeight: 800, marginTop: 10, color: bal <= data.balance + 1 ? c.brandDeep : c.ink }}>
            {vnd(bal)}
          </div>
          <div style={{ height: 22, borderRadius: 11, background: "#f1e4ec", marginTop: 30, overflow: "hidden" }}>
            <div style={{ width: `${(bal / start) * 100}%`, height: "100%", background: c.brand }} />
          </div>
          <div
            style={{
              marginTop: 30,
              fontSize: 36,
              fontWeight: 700,
              color: c.ink,
              display: "flex",
              justifyContent: "space-between",
              opacity: focus,
            }}
          >
            <span>Payday in</span>
            <span style={{ color: c.brand }}>{data.paydayDays} days</span>
          </div>
        </div>
      </div>
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", pointerEvents: "none" }}>
        <div style={{ textAlign: "center", color: "white", opacity: interpolate(fr, [t3, t3 + 6], [0, 1], clamp) }}>
          <div style={{ fontSize: 56, fontWeight: 600, color: "#cdbfd6" }}>
            {vnd(data.balance)} · {data.paydayDays} days
          </div>
          <div style={{ fontSize: 170, fontWeight: 800, color: c.brandVivid, scale: String(pop), marginTop: 10 }}>Enough?</div>
        </div>
      </AbsoluteFill>
      <VoiceTrack voice={plan.voice} area={{ left: 260, width: 1400, bottom: 56 }} />
    </Night>
  );
};
