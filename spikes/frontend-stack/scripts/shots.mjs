// Chụp ảnh màn hình khổ 390x844 bằng Playwright + Chrome có sẵn (channel: 'chrome').
// Chạy: node scripts/shots.mjs [baseUrl]   (cần preview ở :4173 và mock server ở :8787)
import { chromium } from 'playwright'
import path from 'node:path'
import fs from 'node:fs'

const base = process.argv[2] ?? 'http://127.0.0.1:4173'
const out = path.resolve(import.meta.dirname, '../../../docs/research/assets/frontend-spike')
fs.mkdirSync(out, { recursive: true })

const browser = await chromium.launch({ channel: 'chrome', headless: true })
const logs = []

async function run(theme) {
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
    colorScheme: theme,
    locale: 'vi-VN',
    timezoneId: 'Asia/Ho_Chi_Minh',
  })
  const page = await ctx.newPage()
  page.on('console', (m) => (m.type() === 'error' || m.type() === 'warning') && logs.push(`[${theme}] ${m.type()}: ${m.text()}`))
  page.on('pageerror', (e) => logs.push(`[${theme}] pageerror: ${e.message}`))
  await page.goto(`${base}/?theme=${theme}`)
  await page.waitForSelector('[data-testid=forecast-card] svg.recharts-surface')
  await page.waitForTimeout(1500)

  await page.screenshot({ path: `${out}/home-${theme}-top.png` })
  await page.screenshot({ path: `${out}/home-${theme}-full.png`, fullPage: true })
  // cuộn tới biểu đồ
  await page.locator('[data-testid=forecast-card]').scrollIntoViewIfNeeded()
  await page.evaluate(() => window.scrollBy(0, -20))
  await page.waitForTimeout(500)
  await page.screenshot({ path: `${out}/home-${theme}-forecast.png` })

  // chạm vào biểu đồ để hiện dòng đọc số liệu
  const box = await page.locator('[data-testid=forecast-card] svg.recharts-surface').boundingBox()
  await page.touchscreen.tap(box.x + box.width * 0.5, box.y + box.height * 0.5)
  await page.waitForTimeout(400)
  await page.screenshot({ path: `${out}/home-${theme}-forecast-readout.png` })

  // what-if: chụp giữa chừng animation và sau khi xong
  await page.locator('[data-testid=whatif-toggle]').click()
  await page.waitForTimeout(260)
  await page.screenshot({ path: `${out}/whatif-${theme}-mid.png` })
  await page.waitForTimeout(1200)
  await page.screenshot({ path: `${out}/whatif-${theme}-after.png` })

  // chat
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.locator('[data-testid=open-chat]').click()
  await page.waitForSelector('[data-testid=chat-sheet]')
  await page.waitForTimeout(800)
  await page.screenshot({ path: `${out}/chat-${theme}-open.png` })
  await page.getByRole('button', { name: 'Nếu mua tai nghe 1,2 triệu thì sao?' }).click()
  await page.waitForSelector('[data-testid=assistant-text]')
  await page.waitForTimeout(500)
  await page.screenshot({ path: `${out}/chat-${theme}-streaming.png` })
  await page.waitForSelector('[data-testid=block-skeleton]', { timeout: 8000 }).catch(() => logs.push(`[${theme}] no skeleton seen`))
  await page.screenshot({ path: `${out}/chat-${theme}-skeleton.png` })
  await page.waitForSelector('[data-block=confirm]', { timeout: 20000 })
  await page.waitForTimeout(1200)
  await page.screenshot({ path: `${out}/chat-${theme}-blocks.png` })
  const info = await page.evaluate(() => ({
    events: window.__aguiEvents,
    blocks: [...document.querySelectorAll('[data-testid=block-item]')].map((e) => `${e.getAttribute('data-via')}:${e.firstElementChild?.getAttribute('data-block')}:${e.firstElementChild?.getAttribute('data-reason') ?? ''}`),
  }))
  console.log(theme, JSON.stringify(info))
  // cuộn nội dung chat xuống cuối để chụp khối cuối
  await page.evaluate(() => {
    const v = document.querySelector('[data-slot=message-scroller-viewport]')
    if (v) v.scrollTop = v.scrollHeight
  })
  await page.waitForTimeout(500)
  await page.screenshot({ path: `${out}/chat-${theme}-bottom.png` })
  // trang khối UI từ JSON (registry) không qua mạng
  const p2 = await ctx.newPage()
  await p2.goto(`${base}/?theme=${theme}&blocks`)
  await p2.waitForSelector('[data-testid=blocks-demo] [data-block=confirm]')
  await p2.waitForTimeout(1200)
  await p2.locator('[data-testid=blocks-demo]').screenshot({ path: `${out}/blocks-${theme}.png` })
  await ctx.close()
}

for (const t of process.argv[3] ? [process.argv[3]] : ['light', 'dark']) await run(t)
await browser.close()
console.log(logs.join('\n') || 'no console errors/warnings')
