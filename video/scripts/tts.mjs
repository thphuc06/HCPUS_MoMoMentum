// Tạo giọng đọc cho composition YofinaDemo từ narration.md bằng Amazon Polly (engine generative, voice Tiffany).
//
//   node scripts/tts.mjs            tạo câu mới hoặc câu có chữ đổi (so băm nội dung), ghi public/voice/manifest.json
//   node scripts/tts.mjs --dry      chỉ in danh sách câu và số ký tự sẽ gửi, không gọi Polly
//   node scripts/tts.mjs --force    tạo lại mọi câu
//
// Quy ước của narration.md: mỗi tiêu đề `## <số> · …` là một cảnh; dòng bắt đầu bằng `>` là ghi chú, không đọc;
// dấu [ ] bị bỏ khi đọc (số trong ngoặc là số chờ thay bằng số thật trên màn hình).
// Mỗi câu một lần gọi SynthesizeSpeech; câu dưới 4 từ được gộp với câu sau trên cùng dòng (mỗi câu vẫn bọc <s>).
// Gọi qua AWS CLI (credentials mặc định của máy). Không ghi account ID hay ARN vào tệp.
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const NARRATION = path.join(ROOT, "narration.md");
const OUT_DIR = path.join(ROOT, "public", "voice");
const MANIFEST = path.join(OUT_DIR, "manifest.json");
const POLLY = { region: "ap-southeast-1", engine: "generative", voice: "Tiffany", format: "mp3", sampleRate: "24000" };
const USD_PER_MILLION_CHARS = 30;
const MIN_WORDS = 4;

const args = new Set(process.argv.slice(2));
const dry = args.has("--dry");
const force = args.has("--force");

const words = (s) => s.split(/\s+/).filter(Boolean).length;
const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

/** narration.md -> [{scene, title, units: [[câu, câu...], ...]}] */
function parse(md) {
  const scenes = [];
  let cur = null;
  for (const raw of md.split(/\r?\n/)) {
    const line = raw.trim();
    const h = /^##\s+(\d+)\s*·\s*(.*)$/.exec(line);
    if (h) {
      cur = { scene: h[1], title: h[2], units: [] };
      scenes.push(cur);
      continue;
    }
    if (!cur || !line || line.startsWith(">") || line.startsWith("#")) continue;
    const clean = line.replace(/[[\]]/g, "").replace(/\s+/g, " ").trim();
    const sentences = clean.split(/(?<=[.?!])\s+(?=[A-Z"“])/);
    let buf = [];
    for (const s of sentences) {
      buf.push(s);
      if (words(buf.join(" ")) >= MIN_WORDS) {
        cur.units.push(buf);
        buf = [];
      }
    }
    if (buf.length) cur.units.push(buf);
  }
  return scenes;
}

function findFfprobe() {
  const bundled = path.join(ROOT, "node_modules", "@remotion", "compositor-win32-x64-msvc", "ffprobe.exe");
  return fs.existsSync(bundled) ? [bundled, []] : ["npx", ["remotion", "ffprobe"]];
}
const [ffprobeBin, ffprobePre] = findFfprobe();
const durationMs = (file) => {
  const out = execFileSync(
    ffprobeBin,
    [...ffprobePre, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", file],
    { encoding: "utf8", shell: ffprobeBin === "npx" },
  );
  return Math.round(parseFloat(out.trim()) * 1000);
};

const scenes = parse(fs.readFileSync(NARRATION, "utf8"));
const old = fs.existsSync(MANIFEST) ? JSON.parse(fs.readFileSync(MANIFEST, "utf8")) : { items: [], polly: {} };
const byHash = new Map(old.items.map((it) => [it.hash, it]));
fs.mkdirSync(OUT_DIR, { recursive: true });

const items = [];
let sentChars = 0;
let calls = 0;
let reused = 0;
for (const sc of scenes) {
  sc.units.forEach((unit, i) => {
    const id = `s${sc.scene}-${String(i).padStart(2, "0")}`;
    const text = unit.join(" ");
    const ssml = `<speak>${unit.map((s) => `<s>${esc(s)}</s>`).join(" ")}</speak>`;
    const hash = createHash("sha1")
      .update(JSON.stringify([POLLY.engine, POLLY.voice, POLLY.sampleRate, ssml]))
      .digest("hex")
      .slice(0, 16);
    const file = `voice/${id}.mp3`;
    const abs = path.join(ROOT, "public", file);
    const prev = byHash.get(hash);
    let ms;
    if (!force && prev && fs.existsSync(path.join(ROOT, "public", prev.file))) {
      if (prev.file !== file) fs.copyFileSync(path.join(ROOT, "public", prev.file), abs + ".tmp");
      ms = prev.ms;
      reused++;
    } else if (dry) {
      sentChars += text.length;
      calls++;
      ms = prev?.ms ?? Math.round(words(text) / 2.6 * 1000);
    } else {
      const res = execFileSync(
        "aws",
        [
          "polly", "synthesize-speech",
          "--region", POLLY.region,
          "--engine", POLLY.engine,
          "--voice-id", POLLY.voice,
          "--output-format", POLLY.format,
          "--sample-rate", POLLY.sampleRate,
          "--text-type", "ssml",
          "--text", ssml,
          abs + ".tmp",
        ],
        { encoding: "utf8" },
      );
      const billed = JSON.parse(res).RequestCharacters ?? text.length;
      sentChars += billed;
      calls++;
      ms = null;
      process.stdout.write(`  polly ${id} (${billed} ký tự)\n`);
    }
    items.push({ id, scene: sc.scene, index: i, text, ssml, file, hash, ms });
  });
}

// Đổi tên .tmp sau cùng để câu dịch chỗ không ghi đè tệp còn được dùng làm nguồn chép.
for (const it of items) {
  const abs = path.join(ROOT, "public", it.file);
  if (fs.existsSync(abs + ".tmp")) fs.renameSync(abs + ".tmp", abs);
  if (it.ms == null && !dry) it.ms = durationMs(abs);
}
// Xóa tệp giọng không còn dùng.
if (!dry) {
  const keep = new Set(items.map((it) => path.basename(it.file)));
  for (const f of fs.readdirSync(OUT_DIR)) if (f.endsWith(".mp3") && !keep.has(f)) fs.unlinkSync(path.join(OUT_DIR, f));
}

const totalMs = items.reduce((a, it) => a + it.ms, 0);
const prevTotal = old.polly?.totalCharactersSent ?? 0;
const manifest = {
  _note: "Sinh bởi scripts/tts.mjs từ narration.md; không sửa tay. ms đo bằng ffprobe đi kèm Remotion.",
  voice: { engine: POLLY.engine, voiceId: POLLY.voice, region: POLLY.region, sampleRate: Number(POLLY.sampleRate) },
  polly: {
    lastRunCalls: calls,
    lastRunCharactersSent: sentChars,
    totalCharactersSent: prevTotal + (dry ? 0 : sentChars),
    usdPerMillionCharacters: USD_PER_MILLION_CHARS,
  },
  speechMs: totalMs,
  items,
};
if (!dry) fs.writeFileSync(MANIFEST, JSON.stringify(manifest, null, 2) + "\n");

const perScene = {};
for (const it of items) perScene[it.scene] = (perScene[it.scene] ?? 0) + it.ms;
console.log(`${items.length} câu, ${calls} lần gọi Polly${dry ? " (dry run)" : ""}, ${reused} dùng lại`);
console.log(`ký tự gửi lượt này: ${sentChars} (~${((sentChars / 1e6) * USD_PER_MILLION_CHARS).toFixed(4)} USD); tổng từ trước tới nay: ${manifest.polly.totalCharactersSent}`);
console.log(`tổng lời: ${(totalMs / 1000).toFixed(1)} s`);
for (const [s, ms] of Object.entries(perScene)) console.log(`  cảnh ${s}: ${(ms / 1000).toFixed(1)} s`);
