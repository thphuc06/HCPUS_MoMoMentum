// Chạy kịch bản fetch từ trang http://localhost:<port> bằng Edge/Chrome thật (headless) qua playwright-core.
// Dùng: node run_browser.mjs <scenarios.json> <out.json>   Env: RT_URL, TOKEN_FILE, TOKEN_KEY (a|i), BROWSER_CHANNEL
import http from "node:http"; import fs from "node:fs"; import { chromium } from "playwright-core";
const [scenFile, outFile] = process.argv.slice(2);
const PORT = Number(process.env.PORT || 5173);
const html = fs.readFileSync(new URL("./index.html", import.meta.url));
const srv = http.createServer((q, r) => { r.setHeader("content-type", "text/html"); r.end(html); }).listen(PORT, "127.0.0.1");
const tokens = JSON.parse(fs.readFileSync(process.env.TOKEN_FILE, "utf8"));
const token = tokens[process.env.TOKEN_KEY || "a"];
const url = process.env.RT_URL;
const scen = JSON.parse(fs.readFileSync(scenFile, "utf8"));
const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || "msedge", headless: true });
const ver = browser.version();
const ctx = await browser.newContext(); const page = await ctx.newPage();
const netlog = [];
page.on("console", m => netlog.push({ console: m.type(), text: m.text().slice(0, 400) }));
page.on("requestfailed", q => netlog.push({ requestfailed: q.method() + " " + q.url().slice(0, 60), why: q.failure()?.errorText }));
page.on("response", async r => { const q = r.request(); if (q.url().includes("bedrock-agentcore"))
  netlog.push({ resp: q.method(), status: r.status(), acao: (await r.allHeaders())["access-control-allow-origin"] }); });
await page.goto(`http://localhost:${PORT}/`);
const results = { browser: browser.browserType().name() + " " + ver, origin: `http://localhost:${PORT}`, scenarios: {} };
for (const s of scen) {
  netlog.length = 0;
  const body = { threadId: s.thread || "t-" + Math.random().toString(36).slice(2, 8), runId: "r-" + Math.random().toString(36).slice(2, 8),
    state: {}, messages: [{ id: "m1", role: "user", content: s.prompt || "hi" }], tools: [], context: [], forwardedProps: s.fp || { chunks: 4, delay: 0.5 } };
  const reps = s.repeat || 1; results.scenarios[s.name] = [];
  for (let i = 0; i < reps; i++) {
    const sid = s.sid || crypto.randomUUID();
    const headers = {}; for (const [k, v] of Object.entries(s.headers || {})) headers[k] = v.replace("$TOKEN", token).replace("$SID", sid);
    const r = await page.evaluate(cfg => window.agui(cfg), { url, headers, body, credentials: s.credentials });
    r.netlog = [...netlog]; results.scenarios[s.name].push(r); netlog.length = 0;
    if (s.pause_ms) await new Promise(res => setTimeout(res, s.pause_ms));
  }
}
fs.writeFileSync(outFile, JSON.stringify(results, null, 1));
await browser.close(); srv.close();
console.log("ok ->", outFile);
