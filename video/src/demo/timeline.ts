// Tính kế hoạch dựng (frame) từ dữ liệu cảnh + manifest giọng. Hàm thuần, chạy trong calculateMetadata.
import type { ClipEdit, SceneData } from "./scenes";

export const FPS = 30;
export const LEAD_S = 0.3; // lặng đầu cảnh trước câu đầu
export const GAP_S = 0.18; // lặng giữa hai câu
export const TAIL_S = 0.45; // lặng cuối cảnh
export const TRANSITION_FRAMES = 10; // fade giữa hai cảnh (chồng lên phần lặng)
export const VIEW_W = 390;
export const VIEW_H = 844;

export type VoiceItem = { id: string; scene: string; index: number; text: string; file: string; ms: number };
export type Manifest = { items: VoiceItem[] };

export type Segment = { srcFrom: number; outFrom: number; outLen: number; rate: number }; // frame
export type VoicePlan = { file: string; text: string; from: number; len: number };
export type ScenePlan = {
  id: string;
  duration: number;
  voice: VoicePlan[];
  clip: { src: string; segments: Segment[]; editedLen: number; lastSrc: number } | null;
};
export type DemoPlan = { scenes: ScenePlan[]; total: number };

const f = (s: number) => Math.round(s * FPS);

/** Đoạn ra theo thứ tự: mỗi đoạn giữ lại, tách theo các đoạn tua. */
export function buildSegments(clip: ClipEdit, fallbackLen: number): Segment[] {
  const keep = clip.keep?.length ? clip.keep : [{ from: 0, to: fallbackLen }];
  const speed = [...(clip.speed ?? [])].sort((a, b) => a.from - b.from);
  const segs: Segment[] = [];
  let out = 0;
  const push = (a: number, b: number, rate: number) => {
    if (b - a <= 1e-3) return;
    const outLen = Math.max(1, f((b - a) / rate));
    segs.push({ srcFrom: f(a), outFrom: out, outLen, rate });
    out += outLen;
  };
  for (const k of keep) {
    let t = k.from;
    for (const s of speed) {
      if (s.to <= t || s.from >= k.to) continue;
      const a = Math.max(s.from, t);
      const b = Math.min(s.to, k.to);
      push(t, a, 1);
      push(a, b, s.rate);
      t = b;
    }
    push(t, k.to, 1);
  }
  return segs;
}

/** Giây nguồn -> frame ra (trong cảnh). Rơi vào phần bị cắt thì lấy đầu đoạn kế. */
export function srcToOut(segs: Segment[] | null, tSrc: number): number {
  if (!segs || !segs.length) return f(tSrc);
  const fr = tSrc * FPS;
  for (const s of segs) {
    const srcEnd = s.srcFrom + s.outLen * s.rate;
    if (fr < s.srcFrom) return s.outFrom;
    if (fr <= srcEnd) return Math.round(s.outFrom + (fr - s.srcFrom) / s.rate);
  }
  const last = segs[segs.length - 1];
  return last.outFrom + last.outLen;
}

/** Frame ra (trong cảnh) -> giây nguồn; dùng để kiểm câu lời rơi vào đoạn hình nào. */
export function outToSrc(segs: Segment[] | null, out: number): number {
  if (!segs || !segs.length) return out / FPS;
  for (const s of segs) {
    if (out < s.outFrom + s.outLen) return (s.srcFrom + Math.max(0, out - s.outFrom) * s.rate) / FPS;
  }
  const last = segs[segs.length - 1];
  return (last.srcFrom + last.outLen * last.rate) / FPS;
}

export function buildPlan(
  scenes: SceneData[],
  manifest: Manifest,
  clipAvailable: (src: string) => boolean,
): DemoPlan {
  const plans: ScenePlan[] = scenes.map((sc) => {
    const items = manifest.items.filter((it) => it.scene === sc.id).sort((a, b) => a.index - b.index);
    const app = sc.kind === "app" ? sc : null;
    const voiceLen = items.reduce((a, it) => a + it.ms / 1000, 0) + GAP_S * Math.max(0, items.length - 1);
    const roughLen = LEAD_S + voiceLen + TAIL_S;

    let clip: ScenePlan["clip"] = null;
    if (app && clipAvailable(app.clip.src)) {
      const segments = buildSegments(app.clip, Math.max(roughLen, app.minSeconds ?? 0));
      const last = segments[segments.length - 1];
      clip = {
        src: app.clip.src,
        segments,
        editedLen: last ? last.outFrom + last.outLen : 0,
        lastSrc: last ? Math.max(0, last.srcFrom + Math.round(last.outLen * last.rate) - 1) : 0,
      };
    }

    const voice: VoicePlan[] = [];
    let cursor = f(LEAD_S);
    items.forEach((it, i) => {
      const at = app?.voiceAt?.[i];
      const from = at == null ? cursor : Math.max(cursor, srcToOut(clip?.segments ?? null, at));
      const len = Math.max(1, Math.ceil((it.ms / 1000) * FPS));
      voice.push({ file: it.file, text: it.text, from, len });
      cursor = from + len + f(GAP_S);
    });
    const voiceEnd = voice.length ? voice[voice.length - 1].from + voice[voice.length - 1].len : 0;
    let duration = Math.max(voiceEnd + f(TAIL_S), f(app?.minSeconds ?? 0), f(2));
    if (app?.holdClip && clip) duration = Math.max(duration, clip.editedLen);
    return { id: sc.id, duration, voice, clip };
  });
  const total =
    plans.reduce((a, p) => a + p.duration, 0) - TRANSITION_FRAMES * Math.max(0, plans.length - 1);
  return { scenes: plans, total };
}
