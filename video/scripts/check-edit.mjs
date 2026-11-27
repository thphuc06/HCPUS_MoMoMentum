// Kiểm dữ liệu dựng (src/demo/scenes.ts) với mốc cuộn từng bước trong public/rec/scene-<n>.events.json:
// không đoạn tua nào chồng lên đoạn cuộn {type:"scroll", stepped:true}, và không mép cắt (keep.from/to) nào rơi
// vào giữa một đoạn cuộn. In thêm thời lượng từng cảnh và giây nguồn lúc mỗi câu lời bắt đầu.
//   node scripts/check-edit.mjs        (Node 22.6+ chạy thẳng tệp .ts)
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const load = (p) => import(pathToFileURL(path.join(ROOT, p)).href);
const { SCENES } = await load("src/demo/scenes.ts");
const { buildPlan, outToSrc, FPS } = await load("src/demo/timeline.ts");

const EPS = 0.02;
let bad = 0;
for (const sc of SCENES) {
  if (sc.kind !== "app") continue;
  const ev = path.join(ROOT, "public", sc.clip.src.replace(/\.mp4$/, ".events.json"));
  if (!fs.existsSync(ev)) continue;
  const scrolls = JSON.parse(fs.readFileSync(ev, "utf8")).events.filter((e) => e.type === "scroll" && e.stepped);
  for (const s of sc.clip.speed ?? []) {
    for (const r of scrolls) {
      if (s.from < r.to - EPS && s.to > r.from + EPS) {
        console.log(`LỖI cảnh ${sc.id}: tua ${s.from}-${s.to} chồng lên cuộn ${r.from}-${r.to}`);
        bad++;
      }
    }
  }
  for (const k of sc.clip.keep ?? []) {
    for (const edge of [k.from, k.to]) {
      for (const r of scrolls) {
        if (edge > r.from + EPS && edge < r.to - EPS) {
          console.log(`LỖI cảnh ${sc.id}: mép cắt ${edge} nằm giữa cuộn ${r.from}-${r.to}`);
          bad++;
        }
      }
    }
  }
}

const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, "public/voice/manifest.json"), "utf8"));
const plan = buildPlan(SCENES, manifest, (src) => fs.existsSync(path.join(ROOT, "public", src)));
for (const p of plan.scenes) {
  const c = p.clip;
  console.log(`cảnh ${p.id}: ${(p.duration / FPS).toFixed(2)} s${c ? `, clip đã dựng ${(c.editedLen / FPS).toFixed(2)} s` : ""}`);
  for (const v of p.voice) {
    const src = c ? ` (nguồn ${outToSrc(c.segments, v.from).toFixed(1)} s)` : "";
    console.log(`   ${(v.from / FPS).toFixed(2)}${src}  ${v.text.slice(0, 60)}`);
  }
}
console.log(`tổng ${(plan.total / FPS).toFixed(2)} s; ${bad ? bad + " lỗi" : "không lỗi cuộn"}`);
process.exit(bad ? 1 : 0);
