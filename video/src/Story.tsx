import React from "react";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  OffthreadVideo,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { fade } from "@remotion/transitions/fade";
import { linearTiming, TransitionSeries } from "@remotion/transitions";
import { Phone } from "./Phone";
import { c, font, vnd } from "./theme";

export type StoryProps = {
  // Đường dẫn trong public/ tới đoạn quay màn hình app thật; rỗng thì hiện khung chờ.
  demoClip: string;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const out = Easing.bezier(0.16, 1, 0.3, 1);

const Caption: React.FC<{
  kicker?: string;
  title: string;
  sub?: string;
  delay?: number;
}> = ({ kicker, title, sub, delay = 0 }) => {
  const f = useCurrentFrame() - delay;
  const rise = (d: number) => ({
    opacity: interpolate(f, [d, d + 18], [0, 1], clamp),
    translate: interpolate(f, [d, d + 24], ["0px 30px", "0px 0px"], {
      ...clamp,
      easing: out,
    }),
  });
  return (
    <div style={{ color: "white", fontFamily: font, maxWidth: 820 }}>
      {kicker && (
        <div
          style={{
            fontSize: 34,
            color: c.brandVivid,
            fontWeight: 600,
            marginBottom: 18,
            ...rise(0),
          }}
        >
          {kicker}
        </div>
      )}
      <div
        style={{
          fontSize: 84,
          fontWeight: 800,
          lineHeight: 1.12,
          whiteSpace: "pre-line",
          ...rise(8),
        }}
      >
        {title}
      </div>
      {sub && (
        <div
          style={{
            fontSize: 44,
            color: "#cdbfd6",
            marginTop: 28,
            lineHeight: 1.3,
            ...rise(26),
          }}
        >
          {sub}
        </div>
      )}
    </div>
  );
};

const Night: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <AbsoluteFill
    style={{
      background: `radial-gradient(1200px 800px at 75% 40%, ${c.nightSoft}, ${c.night})`,
      fontFamily: font,
    }}
  >
    {children}
  </AbsoluteFill>
);

/* Cảnh 1: chạm để chuyển tiền */
const SceneTap: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const digits = "200000";
  const typed = Math.floor(interpolate(f, [30, 75], [0, digits.length], clamp));
  const amount = typed ? Number(digits.slice(0, typed)) : 0;
  const press = interpolate(f, [100, 108, 116], [1, 0.92, 1], clamp);
  const done = spring({ frame: f - 125, fps, config: { damping: 14 } });
  const phoneIn = spring({ frame: f, fps, config: { damping: 200 } });
  return (
    <Night>
      <AbsoluteFill
        style={{ justifyContent: "center", paddingLeft: 140 }}
      >
        <Caption
          kicker="Tối thứ Sáu, 20/11"
          title={"Minh chuyển 200.000 ₫\nđi ăn với bạn."}
          sub="Một cú chạm. Chẳng nghĩ gì thêm."
        />
      </AbsoluteFill>
      <Phone
        style={{
          position: "absolute",
          right: 220,
          top: 100,
          translate: `0px ${interpolate(phoneIn, [0, 1], [120, 0])}px`,
          opacity: phoneIn,
        }}
      >
        <div
          style={{
            background: `linear-gradient(160deg, ${c.brand}, ${c.brandDeep})`,
            color: "white",
            padding: "76px 34px 34px",
            fontSize: 34,
            fontWeight: 700,
          }}
        >
          Chuyển tiền
          <div style={{ fontSize: 24, fontWeight: 400, opacity: 0.85, marginTop: 8 }}>
            Từ hũ Ăn uống
          </div>
        </div>
        <div style={{ padding: 34, color: c.ink }}>
          <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
            <div
              style={{
                width: 72,
                height: 72,
                borderRadius: 36,
                background: "#f6d5e7",
                color: c.brandDeep,
                display: "grid",
                placeItems: "center",
                fontSize: 32,
                fontWeight: 800,
              }}
            >
              H
            </div>
            <div>
              <div style={{ fontSize: 30, fontWeight: 700 }}>Huy</div>
              <div style={{ fontSize: 22, color: c.muted }}>Bạn bè</div>
            </div>
          </div>
          <div style={{ fontSize: 24, color: c.muted, marginTop: 56 }}>Số tiền</div>
          <div
            style={{
              fontSize: 64,
              fontWeight: 800,
              marginTop: 8,
              borderBottom: `3px solid ${c.brand}`,
              paddingBottom: 12,
            }}
          >
            {amount ? vnd(amount) : "0 ₫"}
          </div>
          <div style={{ fontSize: 24, color: c.muted, marginTop: 18 }}>
            Lời nhắn: Ăn tối thứ Sáu
          </div>
        </div>
        <div
          style={{
            position: "absolute",
            left: 34,
            right: 34,
            bottom: 50,
            height: 96,
            borderRadius: 48,
            background: c.brand,
            color: "white",
            display: "grid",
            placeItems: "center",
            fontSize: 34,
            fontWeight: 700,
            scale: press,
          }}
        >
          Chuyển
        </div>
        {/* ngón tay chạm */}
        <div
          style={{
            position: "absolute",
            left: 190,
            bottom: 70,
            width: 70,
            height: 70,
            borderRadius: 35,
            background: "rgba(255,255,255,0.55)",
            border: "3px solid white",
            opacity: interpolate(f, [88, 98, 118, 124], [0, 1, 1, 0], clamp),
            scale: interpolate(f, [98, 108], [1, 0.75], clamp),
          }}
        />
        <AbsoluteFill
          style={{
            background: "white",
            opacity: interpolate(done, [0, 1], [0, 1]),
            justifyContent: "center",
            alignItems: "center",
            color: c.ink,
          }}
        >
          <div
            style={{
              width: 150,
              height: 150,
              borderRadius: 75,
              background: c.ok,
              color: "white",
              display: "grid",
              placeItems: "center",
              fontSize: 90,
              scale: done,
            }}
          >
            ✓
          </div>
          <div style={{ fontSize: 34, fontWeight: 800, marginTop: 36, whiteSpace: "nowrap" }}>
            Đã chuyển 200.000 ₫
          </div>
          <div style={{ fontSize: 26, color: c.muted, marginTop: 12 }}>
            Hũ Ăn uống còn 380.000 ₫
          </div>
        </AbsoluteFill>
      </Phone>
    </Night>
  );
};

/* Cảnh 2: những khoản nhỏ */
const SPENDS = [
  { t: "Cà phê sáng", v: 45000 },
  { t: "Cơm trưa", v: 55000 },
  { t: "Grab về nhà", v: 38000 },
  { t: "Trà sữa", v: 42000 },
  { t: "Ăn tối với Huy", v: 200000 },
];
const SceneDrip: React.FC = () => {
  const f = useCurrentFrame();
  const start = 760000;
  const spentBy = (frame: number) =>
    SPENDS.reduce(
      (s, x, i) => s + x.v * interpolate(frame, [20 + i * 24, 34 + i * 24], [0, 1], clamp),
      0,
    );
  const bal = start - spentBy(f);
  return (
    <Night>
      <AbsoluteFill style={{ padding: "150px 140px" }}>
        <Caption
          kicker="Nhìn lại cả tuần"
          title={"Toàn khoản nhỏ."}
          sub="Không ai tính tới ngày hũ cạn."
        />
      </AbsoluteFill>
      <div style={{ position: "absolute", left: 140, top: 470, display: "flex", flexDirection: "column", gap: 14 }}>
        {SPENDS.map((s, i) => (
          <div
            key={s.t}
            style={{
              display: "flex",
              justifyContent: "space-between",
              width: 640,
              padding: "20px 30px",
              borderRadius: 22,
              background: "rgba(255,255,255,0.07)",
              color: "white",
              fontSize: 34,
              opacity: interpolate(f, [20 + i * 24, 32 + i * 24], [0, 1], clamp),
              translate: interpolate(f, [20 + i * 24, 36 + i * 24], ["-60px 0px", "0px 0px"], {
                ...clamp,
                easing: out,
              }),
            }}
          >
            <span>{s.t}</span>
            <span style={{ color: "#ff9db8", fontWeight: 600 }}>−{vnd(s.v)}</span>
          </div>
        ))}
      </div>
      <div
        style={{
          position: "absolute",
          right: 200,
          top: 330,
          width: 620,
          padding: 50,
          borderRadius: 40,
          background: c.paper,
          color: c.ink,
        }}
      >
        <div style={{ fontSize: 34, color: c.muted }}>Hũ Ăn uống</div>
        <div style={{ fontSize: 96, fontWeight: 800, marginTop: 10, color: bal < 450000 ? c.brandDeep : c.ink }}>
          {vnd(bal)}
        </div>
        <div style={{ height: 22, borderRadius: 11, background: "#f1e4ec", marginTop: 34, overflow: "hidden" }}>
          <div style={{ width: `${(bal / start) * 100}%`, height: "100%", background: c.brand }} />
        </div>
      </div>
    </Night>
  );
};

/* Cảnh 3: câu hỏi */
const SceneQuestion: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame: f - 70, fps, config: { damping: 10 } });
  const line = (d: number): React.CSSProperties => ({
    opacity: interpolate(f, [d, d + 15], [0, 1], clamp),
    translate: interpolate(f, [d, d + 22], ["0px 24px", "0px 0px"], { ...clamp, easing: out }),
  });
  return (
    <Night>
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", color: "white", textAlign: "center" }}>
        <div style={{ fontSize: 72, fontWeight: 600, ...line(0) }}>Còn 380.000 ₫.</div>
        <div style={{ fontSize: 72, fontWeight: 600, marginTop: 20, ...line(25) }}>
          14 ngày nữa mới tới lương.
        </div>
        <div style={{ fontSize: 150, fontWeight: 800, color: c.brandVivid, marginTop: 50, scale: pop }}>
          Đủ không?
        </div>
      </AbsoluteFill>
    </Night>
  );
};

/* Cảnh 4: Yofina nhìn trước */
// Đường minh họa cho phần kể chuyện; số khớp kịch bản demo (cạn 23/11, lương 05/12).
const MEDIAN = [380, 330, -20, -95, -160, -230, -330, -400, -470, -560, -640, -720, -810, -900, -980];
const DAYS = 15;
const SceneForesee: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const notif = spring({ frame: f - 10, fps, config: { damping: 16 } });
  const draw = interpolate(f, [60, 170], [0, 1], { ...clamp, easing: Easing.inOut(Easing.cubic) });
  const W = 900;
  const H = 520;
  const x = (i: number) => 60 + (i / (DAYS - 1)) * (W - 100);
  const y = (v: number) => 40 + ((400 - v) / 1450) * (H - 100);
  const band = (i: number) => 40 + i * 18;
  const up = MEDIAN.map((v, i) => `${x(i)},${y(v + band(i))}`);
  const lo = MEDIAN.map((v, i) => `${x(i)},${y(v - band(i))}`).reverse();
  const line = MEDIAN.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join(" ");
  const shown = Math.max(0.001, draw);
  const markers = interpolate(f, [150, 175], [0, 1], clamp);
  const labels = ["21/11", "", "23/11", "", "", "", "", "28/11", "", "", "", "", "", "", "05/12"];
  return (
    <Night>
      <Phone style={{ position: "absolute", left: 150, top: 100 }}>
        <div style={{ padding: "90px 28px", color: c.ink }}>
          <div style={{ fontSize: 26, color: c.muted }}>Thứ Bảy, 21/11</div>
          <div style={{ fontSize: 44, fontWeight: 800, marginTop: 6 }}>Chào Minh</div>
        </div>
        <div
          style={{
            position: "absolute",
            left: 18,
            right: 18,
            top: interpolate(notif, [0, 1], [-200, 210]),
            padding: 26,
            borderRadius: 30,
            background: "white",
            boxShadow: "0 18px 50px rgba(0,0,0,0.18)",
            color: c.ink,
          }}
        >
          <div style={{ fontSize: 22, color: c.brand, fontWeight: 700 }}>YOFINA · bây giờ</div>
          <div style={{ fontSize: 30, fontWeight: 800, marginTop: 8, lineHeight: 1.25 }}>
            Hũ Ăn uống dự kiến cạn ngày 23/11
          </div>
          <div style={{ fontSize: 24, color: c.muted, marginTop: 8, lineHeight: 1.35 }}>
            Còn 380.000 ₫, sau đó 12 ngày nữa mới tới lương 05/12.
          </div>
        </div>
      </Phone>
      <div style={{ position: "absolute", left: 720, top: 120, color: "white" }}>
        <Caption
          delay={40}
          kicker="Yofina nhìn trước"
          title="Biết hũ nào cạn, cạn ngày nào."
        />
      </div>
      <svg
        width={W}
        height={H}
        style={{ position: "absolute", left: 720, top: 430, overflow: "visible", fontFamily: font }}
      >
        <defs>
          <clipPath id="reveal">
            <rect x={0} y={0} width={60 + shown * (W - 100)} height={H} />
          </clipPath>
        </defs>
        <line x1={60} x2={W - 40} y1={y(0)} y2={y(0)} stroke="#ffffff55" strokeDasharray="8 8" strokeWidth={2} />
        <text x={48} y={y(0) + 8} fill="#ffffffaa" fontSize={24} textAnchor="end">0 ₫</text>
        <g clipPath="url(#reveal)">
          <polygon points={[...up, ...lo].join(" ")} fill={c.brand} opacity={0.28} />
          <path d={line} stroke={c.brandVivid} strokeWidth={6} fill="none" />
        </g>
        {labels.map((l, i) =>
          l ? (
            <text key={i} x={x(i)} y={H - 10} fill="#cdbfd6" fontSize={24} textAnchor="middle">
              {l}
            </text>
          ) : null,
        )}
        <g opacity={markers}>
          <circle cx={x(2)} cy={y(0)} r={14} fill={c.danger} />
          <text x={x(2) + 24} y={y(0) - 22} fill="white" fontSize={30} fontWeight={800}>
            Cạn 23/11
          </text>
          <line x1={x(14)} x2={x(14)} y1={30} y2={H - 50} stroke={c.ok} strokeWidth={4} />
          <text x={x(14) - 12} y={24} fill="#7fe0b0" fontSize={26} fontWeight={700} textAnchor="end">
            Lương về 05/12
          </text>
        </g>
      </svg>
    </Night>
  );
};

/* Cảnh 5: sang app thật */
const SceneReal: React.FC<StoryProps> = ({ demoClip }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const frameIn = spring({ frame: f - 20, fps, config: { damping: 200 } });
  return (
    <AbsoluteFill style={{ background: c.paper, fontFamily: font, color: c.ink }}>
      <div
        style={{
          position: "absolute",
          left: 140,
          top: 120,
          opacity: interpolate(f, [0, 15], [0, 1], clamp),
        }}
      >
        <div style={{ fontSize: 34, color: c.brand, fontWeight: 700 }}>Không phải mô phỏng</div>
        <div style={{ fontSize: 84, fontWeight: 800, marginTop: 10, lineHeight: 1.1 }}>
          Đây là app thật,
          <br />
          đang chạy.
        </div>
        <div style={{ fontSize: 40, color: c.muted, marginTop: 30, maxWidth: 620, lineHeight: 1.35 }}>
          Agent, dự báo và xác nhận trước khi ghi, chạy trên AWS.
        </div>
      </div>
      <div
        style={{
          position: "absolute",
          right: 140,
          top: 90,
          width: 900,
          height: 900,
          borderRadius: 36,
          overflow: "hidden",
          background: "#1d1424",
          boxShadow: "0 30px 90px rgba(165,0,100,0.25)",
          scale: interpolate(frameIn, [0, 1], [0.9, 1]),
          opacity: frameIn,
        }}
      >
        {demoClip ? (
          <OffthreadVideo src={staticFile(demoClip)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        ) : (
          <AbsoluteFill
            style={{
              justifyContent: "center",
              alignItems: "center",
              color: "#cdbfd6",
              fontSize: 40,
              textAlign: "center",
              border: `4px dashed ${c.brand}`,
              borderRadius: 36,
            }}
          >
            Chỗ ghép đoạn quay màn hình
            <br />
            app thật (cảnh 1 demo)
          </AbsoluteFill>
        )}
      </div>
    </AbsoluteFill>
  );
};

export const SCENES = { tap: 210, drip: 180, question: 150, foresee: 270, real: 240 };
export const TRANSITION = 15;
export const STORY_FRAMES =
  Object.values(SCENES).reduce((a, b) => a + b, 0) - TRANSITION * 4;

export const Story: React.FC<StoryProps> = ({ demoClip }) => {
  const t = <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: TRANSITION })} />;
  return (
    <TransitionSeries>
      <TransitionSeries.Sequence durationInFrames={SCENES.tap}>
        <SceneTap />
      </TransitionSeries.Sequence>
      {t}
      <TransitionSeries.Sequence durationInFrames={SCENES.drip}>
        <SceneDrip />
      </TransitionSeries.Sequence>
      {t}
      <TransitionSeries.Sequence durationInFrames={SCENES.question}>
        <SceneQuestion />
      </TransitionSeries.Sequence>
      {t}
      <TransitionSeries.Sequence durationInFrames={SCENES.foresee}>
        <SceneForesee />
      </TransitionSeries.Sequence>
      {t}
      <TransitionSeries.Sequence durationInFrames={SCENES.real}>
        <SceneReal demoClip={demoClip} />
      </TransitionSeries.Sequence>
    </TransitionSeries>
  );
};
