import React from "react";
import { Audio, interpolate, Sequence, staticFile, useCurrentFrame } from "remotion";
import { font } from "../theme";
import type { VoicePlan } from "./timeline";

const MAX_CHARS = 86; // khoảng 2 dòng ở 44 px trong khung rộng 1000 px

/** Tách câu dài thành các mảnh ≤ MAX_CHARS ở dấu phẩy, hai chấm hoặc khoảng trắng gần giữa. */
export function chunk(text: string): string[] {
  if (text.length <= MAX_CHARS) return [text];
  const mid = text.length / 2;
  let best = -1;
  const re = /[,:;.?!] /g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    const i = m.index + 1;
    if (best < 0 || Math.abs(i - mid) < Math.abs(best - mid)) best = i;
  }
  if (best < 0 || Math.abs(best - mid) > text.length * 0.3) {
    best = text.lastIndexOf(" ", mid + 8);
  }
  return [...chunk(text.slice(0, best).trim()), ...chunk(text.slice(best).trim())];
}

const Line: React.FC<{ text: string; len: number; width: number }> = ({ text, len, width }) => {
  const fr = useCurrentFrame();
  const o = interpolate(fr, [0, 4, len - 3, len], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, display: "flex", justifyContent: "center" }}>
      <div
        style={{
          maxWidth: width,
          padding: "12px 26px 14px",
          borderRadius: 18,
          background: "rgba(10, 6, 16, 0.72)",
          color: "white",
          fontFamily: font,
          fontSize: 42,
          fontWeight: 600,
          lineHeight: 1.28,
          textAlign: "center",
          opacity: o,
        }}
      >
        {text}
      </div>
    </div>
  );
};

/** Âm thanh từng câu + phụ đề theo câu. `area` là vùng đặt phụ đề (đáy khung) trong hệ toạ độ 1920×1080. */
export const VoiceTrack: React.FC<{
  voice: VoicePlan[];
  area: { left: number; width: number; bottom: number };
  subtitles?: boolean;
}> = ({ voice, area, subtitles = true }) => (
  <>
    {voice.map((v, i) => {
      const next = voice[i + 1];
      // Giữ phụ đề tới câu sau (tối đa 0,4 s) cho đỡ nháy.
      const shown = Math.min(v.len + 12, next ? next.from - v.from : v.len + 12);
      const parts = chunk(v.text);
      const total = parts.reduce((a, p) => a + p.length, 0);
      let acc = 0;
      return (
        <React.Fragment key={v.file + i}>
          <Sequence from={v.from} durationInFrames={v.len} layout="none" name={`voice ${v.file}`}>
            <Audio src={staticFile(v.file)} />
          </Sequence>
          {subtitles &&
            parts.map((p, j) => {
              const start = Math.round((acc / total) * v.len);
              acc += p.length;
              const end = j === parts.length - 1 ? shown : Math.round((acc / total) * v.len);
              return (
                <Sequence
                  key={j}
                  from={v.from + start}
                  durationInFrames={Math.max(1, end - start)}
                  name={`sub ${p.slice(0, 24)}`}
                >
                  <div
                    style={{
                      position: "absolute",
                      left: area.left,
                      width: area.width,
                      bottom: area.bottom,
                    }}
                  >
                    <Line text={p} len={Math.max(1, end - start)} width={area.width} />
                  </div>
                </Sequence>
              );
            })}
        </React.Fragment>
      );
    })}
  </>
);
