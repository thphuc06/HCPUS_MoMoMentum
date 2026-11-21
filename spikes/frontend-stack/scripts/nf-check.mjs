// Kiểm NumberFlow: bấm "Tiền vào" (+15.000.000) rồi chụp giữa chừng + sau animation; in lỗi console.
import { chromium } from 'playwright'
import path from 'node:path'
const out = path.resolve(import.meta.dirname, '../../../docs/research/assets/frontend-spike')
const b = await chromium.launch({ channel: 'chrome' })
const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, locale: 'vi-VN' })
const p = await ctx.newPage()
const errs = []
p.on('console', (m) => m.type() === 'error' && errs.push(m.text()))
p.on('pageerror', (e) => errs.push('pageerror ' + e.message))
await p.goto('http://127.0.0.1:4173/')
await p.waitForTimeout(1500)
await p.getByRole('button', { name: 'Tiền vào' }).click()
await p.waitForTimeout(250)
await p.screenshot({ path: `${out}/numberflow-mid.png`, clip: { x: 0, y: 100, width: 390, height: 300 } })
await p.waitForTimeout(1500)
await p.screenshot({ path: `${out}/numberflow-after.png`, clip: { x: 0, y: 100, width: 390, height: 300 } })
console.log('balance aria/text:', await p.locator('[data-testid=balance]').innerText(), '| errors:', JSON.stringify(errs))
await b.close()
