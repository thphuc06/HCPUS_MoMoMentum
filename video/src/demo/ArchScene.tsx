import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { c } from "../theme";
import { Night } from "./AppScene";
import { VoiceTrack } from "./Subtitles";
import type { ScenePlan, VoicePlan } from "./timeline";

/*
 * Cảnh 9: sơ đồ hệ thống. Chỉ vẽ thành phần có thật (đối chiếu docs/architecture/overview.md và infra-cdk/lib/ ngày 27/11):
 * Amplify Hosting (frontend-stack), Cognito (identity-stack), AgentCore Runtime + Gateway + interceptor + Policy Engine Cedar
 * (agent-stack), AgentCore Memory (memory.ts), Bedrock Guardrails (guardrail.ts), model theo llm_defaults.json,
 * Lambda ledger/forecast/ingest với sáu target Gateway, HTTP API (tools-stack), Aurora Serverless v2 (data-stack),
 * EventBridge bus → SQS → Lambda (forecast-pipeline, classify, roadmap-regen), S3 → SQS → worker nạp (ingest-stack),
 * EventBridge Scheduler 02:00 → Step Functions (forecast-pipeline).
 */

type Node = {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  title: string;
  sub?: string;
  items?: string[];
  cols?: number;
};

const NODES: Node[] = [
  { id: "cognito", x: 60, y: 110, w: 310, h: 104, title: "Amazon Cognito", sub: "sign-in · JWT" },
  { id: "web", x: 60, y: 300, w: 310, h: 124, title: "Web app", sub: "React + Vite · Amplify Hosting" },
  {
    id: "runtime",
    x: 460,
    y: 70,
    w: 520,
    h: 430,
    title: "AgentCore Runtime",
    sub: "Strands agent · harness",
    items: ["Router · Claude Haiku 4.5", "Planner · Claude Sonnet 4.6", "Number check", "Writer", "PII masking", "Guardrails"],
    cols: 1,
  },
  { id: "memory", x: 460, y: 530, w: 250, h: 140, title: "AgentCore Memory", sub: "per-user memory" },
  { id: "bedrock", x: 730, y: 530, w: 250, h: 140, title: "Amazon Bedrock", sub: "Claude · Nova" },
  {
    id: "gateway",
    x: 1070,
    y: 150,
    w: 320,
    h: 300,
    title: "AgentCore Gateway",
    sub: "MCP tools",
    items: ["JWT → user_id", "Cedar policies"],
    cols: 1,
  },
  {
    id: "tools",
    x: 1480,
    y: 70,
    w: 380,
    h: 300,
    title: "Lambda tools",
    sub: "6 Gateway targets · what-if runs in forecast",
    items: ["ledger", "forecast", "planner", "knowledge", "ingest", "audit"],
    cols: 2,
  },
  { id: "engine", x: 1480, y: 400, w: 380, h: 110, title: "Forecast engine", sub: "Monte Carlo · LP allocation" },
  { id: "aurora", x: 1480, y: 540, w: 380, h: 110, title: "Aurora PostgreSQL", sub: "Serverless v2 · source of truth" },
  { id: "event", x: 60, y: 740, w: 580, h: 116, title: "On new data", sub: "statement upload · S3 → SQS\nledger events · EventBridge → SQS → Lambda" },
  { id: "nightly", x: 670, y: 740, w: 580, h: 116, title: "Every night · 02:00", sub: "EventBridge Scheduler → Step Functions" },
  { id: "demand", x: 1280, y: 740, w: 580, h: 116, title: "On demand", sub: "chat · AG-UI stream from Runtime" },
];

/** Mốc sáng: câu thứ `s`, tại từ `word` (theo vị trí ký tự trong câu). */
type Cue = { target: string; s: number; word?: string };
const CUES: Cue[] = [
  { target: "web", s: 0 },
  { target: "cognito", s: 0, word: "Cognito" },
  { target: "runtime", s: 0, word: "Strands" },
  { target: "memory", s: 0, word: "Memory" },
  { target: "bedrock", s: 0, word: "Bedrock" },
  { target: "runtime.0", s: 1, word: "routes" },
  { target: "runtime.1", s: 1, word: "plans" },
  { target: "runtime.2", s: 1, word: "checks" },
  { target: "runtime.3", s: 1, word: "masks" },
  { target: "runtime.4", s: 1, word: "masks" },
  { target: "runtime.5", s: 1, word: "personal" },
  { target: "gateway", s: 2, word: "Gateway" },
  { target: "gateway.0", s: 2, word: "Gateway" },
  { target: "gateway.1", s: 2, word: "Cedar" },
  { target: "tools", s: 2, word: "Lambda" },
  { target: "engine", s: 2, word: "Monte" },
  { target: "aurora", s: 2, word: "Aurora" },
  { target: "event", s: 3, word: "new" },
  { target: "nightly", s: 3, word: "night" },
  { target: "demand", s: 3, word: "demand" },
];

type Edge = { from: string; to: string; d: string; label?: string; lx?: number; ly?: number; dashed?: boolean };
const EDGES: Edge[] = [
  { from: "web", to: "cognito", d: "M215 300 L215 214", label: "sign in", lx: 228, ly: 264 },
  { from: "web", to: "runtime", d: "M370 362 L460 362", label: "AG-UI", lx: 380, ly: 350 },
  { from: "runtime", to: "memory", d: "M585 500 L585 530" },
  { from: "runtime", to: "bedrock", d: "M855 500 L855 530" },
  { from: "runtime", to: "gateway", d: "M980 300 L1070 300", label: "MCP", lx: 1000, ly: 288 },
  { from: "gateway", to: "tools", d: "M1390 300 L1480 300", label: "", lx: 0, ly: 0 },
  { from: "tools", to: "engine", d: "M1670 370 L1670 400" },
  { from: "engine", to: "aurora", d: "M1670 510 L1670 540" },
  { from: "web", to: "tools", d: "M120 424 L120 700 L1430 700 L1430 330 L1480 330", label: "HTTP API · screens without LLM", lx: 1010, ly: 690, dashed: true },
];

const wordFrame = (v: VoicePlan | undefined, word?: string) => {
  if (!v) return 1e9;
  if (!word) return v.from;
  const i = v.text.indexOf(word);
  return i < 0 ? v.from : Math.round(v.from + (i / v.text.length) * v.len);
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const ArchScene: React.FC<{ plan: ScenePlan }> = ({ plan }) => {
  const fr = useCurrentFrame();
  const at = new Map<string, number>();
  for (const cue of CUES) {
    const t = wordFrame(plan.voice[cue.s], cue.word);
    at.set(cue.target, Math.min(at.get(cue.target) ?? 1e9, t));
  }
  // lit: 0 → 1 khi tới mốc; glow: nhấn mạnh 1,5 s sau mốc.
  const lit = (id: string) => interpolate(fr, [(at.get(id) ?? 1e9) - 4, (at.get(id) ?? 1e9) + 8], [0, 1], clamp);
  const glow = (id: string) => {
    const t = at.get(id) ?? 1e9;
    return interpolate(fr, [t - 4, t + 6, t + 40, t + 60], [0, 1, 1, 0], clamp);
  };
  const enter = interpolate(fr, [0, 14], [0, 1], clamp);

  return (
    <Night>
      <div style={{ position: "absolute", left: 60, top: 14, fontSize: 30, fontWeight: 700, color: "#cdbfd6", opacity: enter }}>
        How it runs · AWS ap-southeast-1
      </div>
      <svg width={1920} height={1080} style={{ position: "absolute", inset: 0 }}>
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0 0 L10 5 L0 10 z" fill="#ff9fd0" />
          </marker>
        </defs>
        {EDGES.map((e, i) => {
          const p = Math.min(lit(e.from), lit(e.to));
          return (
            <g key={i} opacity={0.25 + 0.75 * p}>
              <path
                d={e.d}
                fill="none"
                stroke={p > 0.01 ? "#ff9fd0" : "#ffffff55"}
                strokeWidth={3}
                strokeDasharray={e.dashed ? "10 8" : undefined}
                markerEnd="url(#arrow)"
              />
              {e.label ? (
                <text x={e.lx} y={e.ly} fill="#e9dff0" fontSize={20} fontWeight={600}>
                  {e.label}
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>
      {NODES.map((n) => {
        const l = lit(n.id);
        const g = glow(n.id);
        return (
          <div
            key={n.id}
            style={{
              position: "absolute",
              left: n.x,
              top: n.y,
              width: n.w,
              height: n.h,
              boxSizing: "border-box",
              padding: "16px 22px",
              borderRadius: 22,
              background: `rgba(255,255,255,${0.04 + 0.06 * l})`,
              border: `2px solid ${l > 0.5 ? c.brandVivid : "rgba(255,255,255,0.18)"}`,
              boxShadow: `0 0 ${40 * g}px rgba(216,45,139,${0.7 * g})`,
              color: "white",
              opacity: 0.32 + 0.68 * l,
            }}
          >
            <div style={{ fontSize: 30, fontWeight: 800, lineHeight: 1.15 }}>{n.title}</div>
            {n.sub && (
              <div style={{ fontSize: 21, color: "#cdbfd6", marginTop: 6, lineHeight: 1.3, whiteSpace: "pre-line" }}>{n.sub}</div>
            )}
            {n.items && (
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: `repeat(${n.cols ?? 1}, 1fr)`,
                  gap: 8,
                  marginTop: 14,
                }}
              >
                {n.items.map((it, i) => {
                  const id = `${n.id}.${i}`;
                  const il = at.has(id) ? lit(id) : l;
                  const ig = at.has(id) ? glow(id) : 0;
                  return (
                    <div
                      key={it}
                      style={{
                        fontSize: 22,
                        fontWeight: 600,
                        padding: "8px 14px",
                        borderRadius: 12,
                        background: `rgba(200,32,126,${0.08 + 0.3 * ig + 0.1 * il})`,
                        border: `1px solid rgba(255,159,208,${0.15 + 0.5 * il})`,
                        color: il > 0.5 ? "white" : "#cdbfd6",
                      }}
                    >
                      {it}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
      <VoiceTrack voice={plan.voice} area={{ left: 260, width: 1400, bottom: 40 }} />
    </Night>
  );
};
