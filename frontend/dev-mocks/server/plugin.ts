// CHỈ cho `npm run dev:mock` (vite --mode mock): máy chủ giả để xem giao diện bằng mắt khi backend chưa sẵn sàng.
// Không nằm trong bundle production (vite.config.ts chỉ import file này khi mode === 'mock'; tsconfig.app không include).
// Dữ liệu mẫu lấy từ contracts/fixtures. Đây KHÔNG phải agent: câu trả lời chọn theo từ khóa chỉ để thử giao diện.
import { createHash, randomUUID } from 'node:crypto'
import { readFileSync } from 'node:fs'
import type { IncomingMessage, ServerResponse } from 'node:http'
import path from 'node:path'
import type { Plugin } from 'vite'

export const MOCK_ENV: Record<string, string> = {
  VITE_AWS_REGION: 'ap-southeast-1',
  VITE_COGNITO_USER_POOL_ID: 'mock_pool',
  VITE_COGNITO_CLIENT_ID: 'mockclient',
  VITE_API_URL: '/mock-api',
  VITE_AGENT_RUNTIME_URL: '/mock-agent/invocations',
  VITE_DEMO_EMAIL: 'demo@example.invalid',
}

const FIXTURES = path.resolve(import.meta.dirname, '../../../contracts/fixtures/blocks/valid')
const fixture = (name: string) => JSON.parse(readFileSync(path.join(FIXTURES, name), 'utf8')) as Record<string, any>

type Jar = { code: string; name: string; color_key: string; icon_key: string; balance_vnd: number; split_percent: number }
const seed = (): Jar[] => fixture('jar_summary.seven_jars.json').data.jars
let jars: Jar[] = seed()
const tokens = new Map<string, { hash: string; used: boolean }>()
// Đề nghị (confirm_block_id) đã thực hiện: như server thật, mỗi đề nghị chỉ được thực hiện một lần (ALREADY_APPLIED).
const applied = new Set<string>()
const APP_DATE = '2026-11-21'

const total = () => jars.reduce((s, j) => s + j.balance_vnd, 0)
const nowIso = () => new Date().toISOString().replace(/\.\d+Z$/, 'Z')
const vnd = (n: number) => `${n.toLocaleString('vi-VN')} ₫`
const source = (tool: string) => ({ tool, as_of: nowIso(), app_date: APP_DATE })
const traceOf = (req: IncomingMessage) => (String(req.headers.traceparent ?? '').split('-')[1] ?? randomUUID().replace(/-/g, ''))

function canonical(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(canonical).join(',')}]`
  if (v && typeof v === 'object') {
    const o = v as Record<string, unknown>
    return `{${Object.keys(o).sort().map((k) => `${JSON.stringify(k)}:${canonical(o[k])}`).join(',')}}`
  }
  return JSON.stringify(v)
}
const paramsHash = (tool: string, params: unknown) => createHash('sha256').update(canonical({ tool, params })).digest('hex')

async function body(req: IncomingMessage): Promise<any> {
  const chunks: Buffer[] = []
  for await (const c of req) chunks.push(c as Buffer)
  const s = Buffer.concat(chunks).toString('utf8')
  try {
    return s ? JSON.parse(s) : {}
  } catch {
    return {}
  }
}

function json(res: ServerResponse, status: number, data: unknown) {
  res.writeHead(status, { 'content-type': 'application/json' })
  res.end(JSON.stringify(data))
}
const err = (res: ServerResponse, status: number, code: string, message: string) => json(res, status, { error: { code, message } })

function jarsBlock(trace: string) {
  return {
    v: 1,
    id: `jar_summary:${trace}`,
    type: 'jar_summary',
    trace_id: trace,
    fallback_text: `Số dư ${jars.length} hũ, tổng ${vnd(total())}.`,
    source: source('ledger___get_jar_balances'),
    data: { jars, jars_total_vnd: total() },
  }
}

function confirmBlock(trace: string, from: Jar, to: Jar, amount: number) {
  const params = { from_jar: from.code, to_jar: to.code, amount_vnd: amount }
  const hash = paramsHash('move_between_jars', params)
  return {
    v: 1,
    id: `confirm:${trace}:${hash.slice(0, 12)}`,
    type: 'confirm',
    trace_id: trace,
    fallback_text: `Chuyển ${vnd(amount)} từ ${from.name} sang ${to.name}. Cần bạn xác nhận trên ứng dụng.`,
    source: source('ledger___move_between_jars'),
    data: {
      tool: 'move_between_jars',
      params,
      params_hash: hash,
      summary: `Chuyển ${vnd(amount)} từ ${from.name} sang ${to.name}`,
      preview: {
        from: { code: from.code, name: from.name, before_vnd: from.balance_vnd, after_vnd: from.balance_vnd - amount },
        to: { code: to.code, name: to.name, before_vnd: to.balance_vnd, after_vnd: to.balance_vnd + amount },
      },
      expires_at: new Date(Date.now() + 5 * 60_000).toISOString().replace(/\.\d+Z$/, 'Z'),
    },
  }
}

const norm = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/g, 'd').toLowerCase()

function findJar(text: string, fromIdx = 0): { jar: Jar; at: number } | null {
  const t = norm(text)
  let best: { jar: Jar; at: number } | null = null
  for (const j of jars) {
    const at = t.indexOf(norm(j.name), fromIdx)
    if (at !== -1 && (!best || at < best.at)) best = { jar: j, at }
  }
  return best
}

function parseAmount(text: string): number | null {
  const t = norm(text)
  const m = /(\d+(?:[.,]\d+)?)\s*(k|nghin|trieu|tr)?/.exec(t.replace(/(\d)\.(\d{3})/g, '$1$2'))
  if (!m) return null
  const n = Number(m[1]!.replace(',', '.'))
  const unit = m[2]
  const mult = unit === 'trieu' || unit === 'tr' ? 1_000_000 : unit === 'k' || unit === 'nghin' ? 1_000 : 1
  return Math.round(n * mult)
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

async function agent(req: IncomingMessage, res: ServerResponse) {
  const auth = String(req.headers.authorization ?? '')
  if (!auth.startsWith('Bearer ')) {
    res.writeHead(401, { 'content-type': 'text/event-stream' })
    res.end(`data: ${JSON.stringify({ type: 'RUN_ERROR', message: 'Missing Authentication Token', code: 'UNAUTHORIZED' })}\n\n`)
    return
  }
  const input = await body(req)
  const msgs: Array<{ role: string; content: string }> = input.messages ?? []
  const last = [...msgs].reverse().find((m) => m.role === 'user')?.content ?? ''
  const q = norm(last)
  const trace = traceOf(req)
  if (input.forwardedProps?.warmup) {
    res.writeHead(200, { 'content-type': 'text/event-stream' })
    res.write(`data: ${JSON.stringify({ type: 'RUN_STARTED', threadId: input.threadId, runId: input.runId })}

`)
    res.end(`data: ${JSON.stringify({ type: 'RUN_FINISHED', threadId: input.threadId, runId: input.runId })}

`)
    return
  }
  console.log(`[mock-agent] ${msgs.length} tin trong lịch sử; hỏi: ${last}`)
  res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache' })
  const emit = (e: Record<string, unknown>) => res.write(`data: ${JSON.stringify(e)}\n\n`)
  const say = async (id: string, text: string) => {
    emit({ type: 'TEXT_MESSAGE_START', messageId: id, role: 'assistant' })
    for (const piece of text.match(/\S+\s*/g) ?? [text]) {
      emit({ type: 'TEXT_MESSAGE_CONTENT', messageId: id, delta: piece })
      await sleep(35)
    }
    emit({ type: 'TEXT_MESSAGE_END', messageId: id })
  }
  const tool = async (id: string, name: string, ms = 700) => {
    emit({ type: 'TOOL_CALL_START', toolCallId: id, toolCallName: name })
    emit({ type: 'TOOL_CALL_END', toolCallId: id })
    await sleep(ms)
    emit({ type: 'TOOL_CALL_RESULT', messageId: `r-${id}`, toolCallId: id, content: '{}', role: 'tool' })
  }
  const block = (b: Record<string, unknown>) => emit({ type: 'ACTIVITY_SNAPSHOT', messageId: String(b.id), activityType: 'yofina.block', content: b, replace: true })
  const start = () => emit({ type: 'RUN_STARTED', threadId: input.threadId, runId: input.runId })
  const end = () => {
    emit({ type: 'RUN_FINISHED', threadId: input.threadId, runId: input.runId })
    res.end()
  }

  // Các từ khóa thử lỗi: "loi" (RUN_ERROR), "rong" (luồng rỗng), "dut" (đứt giữa chừng), "la" (khối lạ).
  if (q.includes('rong')) return void res.end()
  start()
  if (q.includes('dut')) {
    await say('m1', 'Mình đang đọc số dư rồi thì')
    return void res.destroy()
  }
  if (q.includes('loi')) {
    emit({ type: 'RUN_ERROR', message: 'boom', code: 'INTERNAL_ERROR' })
    return void res.end()
  }
  if (q.includes('khoi la')) {
    await say('m1', 'Đây là một khối mà ứng dụng chưa biết.')
    block({ v: 1, id: `hologram:${trace}`, type: 'hologram_3d', trace_id: trace, fallback_text: 'Một khối mới mà bản này chưa hiển thị được.', source: source('agent'), data: { x: 1 } })
    return end()
  }
  if (q.includes('chuyen')) {
    const amount = parseAmount(last)
    const a = findJar(last)
    const b = a ? findJar(last, a.at + 1) : null
    // "chuyển X từ A sang B": hũ nguồn là hũ đứng sau chữ "tu"
    const tuAt = q.indexOf(' tu ')
    const sangAt = q.indexOf(' sang ')
    let from = a?.jar
    let to = b?.jar
    if (a && b && tuAt !== -1 && sangAt !== -1 && tuAt > sangAt) [from, to] = [to, from]
    if (!amount || !from || !to || from.code === to.code) {
      await say('m1', 'Bạn cho mình biết số tiền, hũ nguồn và hũ đích nhé. Ví dụ: chuyển 100 nghìn từ Giải trí sang Ăn uống.')
      return end()
    }
    await say('m1', 'Mình đã tính trước và chưa ghi gì cả. Bạn xem lại rồi quyết định nhé.')
    await tool('tc1', 'ledger___move_between_jars')
    block(confirmBlock(trace, from, to, amount))
    return end()
  }
  await tool('tc1', 'ledger___get_jar_balances')
  block(jarsBlock(trace))
  await say('m1', 'Đây là số dư các hũ của bạn.')
  return end()
}

function rest(req: IncomingMessage, res: ServerResponse, url: string) {
  return (async () => {
    if (!String(req.headers.authorization ?? '').startsWith('Bearer ')) return err(res, 401, 'UNAUTHENTICATED', 'Thiếu token.')
    const trace = traceOf(req)
    if (req.method === 'GET' && url === '/jars') {
      return json(res, 200, { app_date: APP_DATE, as_of: nowIso(), jars, jars_total_vnd: total() })
    }
    if (req.method === 'POST' && url === '/confirmations') {
      const b = await body(req)
      if (b.confirm_block_id && applied.has(b.confirm_block_id)) return err(res, 409, 'ALREADY_APPLIED', 'Đề nghị này đã được thực hiện rồi.')
      const hash = paramsHash(b.tool, b.params)
      if (b.params_hash && b.params_hash !== hash) return err(res, 409, 'PARAMS_MISMATCH', 'Tham số lệch.')
      const from = jars.find((j) => j.code === b.params?.from_jar)
      const to = jars.find((j) => j.code === b.params?.to_jar)
      if (!from || !to) return err(res, 404, 'JAR_NOT_FOUND', 'Không có hũ này.')
      if (from.balance_vnd < b.params.amount_vnd) return err(res, 422, 'INSUFFICIENT_FUNDS', 'Không đủ số dư.')
      const token = `${randomUUID().replace(/-/g, '')}.${randomUUID().replace(/-/g, '').slice(0, 16)}`
      tokens.set(token, { hash, used: false })
      return json(res, 200, { confirm_token: token, expires_at: new Date(Date.now() + 120_000).toISOString().replace(/\.\d+Z$/, 'Z'), ttl_seconds: 120, tool: b.tool, params: b.params, params_hash: hash })
    }
    if (req.method === 'POST' && url === '/actions') {
      const b = await body(req)
      if (!b.confirm_token) return err(res, 428, 'NEEDS_CONFIRMATION', 'Cần xác nhận.')
      if (b.confirm_block_id && applied.has(b.confirm_block_id)) return err(res, 409, 'ALREADY_APPLIED', 'Đề nghị này đã được thực hiện rồi.')
      const t = tokens.get(b.confirm_token)
      if (!t) return err(res, 403, 'TOKEN_INVALID', 'Token không hợp lệ.')
      if (t.used) return err(res, 409, 'TOKEN_REUSED', 'Token đã dùng.')
      if (t.hash !== paramsHash(b.tool, b.params)) return err(res, 409, 'PARAMS_MISMATCH', 'Tham số lệch.')
      const from = jars.find((j) => j.code === b.params.from_jar)!
      const to = jars.find((j) => j.code === b.params.to_jar)!
      t.used = true
      if (b.confirm_block_id) applied.add(b.confirm_block_id)
      from.balance_vnd -= b.params.amount_vnd
      to.balance_vnd += b.params.amount_vnd
      const tx = randomUUID()
      return json(res, 200, {
        v: 1,
        id: `receipt:${tx}`,
        type: 'receipt',
        trace_id: trace,
        fallback_text: `Đã chuyển ${vnd(b.params.amount_vnd)} từ ${from.name} sang ${to.name}.`,
        source: source('rest:POST /actions'),
        data: {
          tool: 'move_between_jars',
          transaction_id: tx,
          occurred_at: nowIso(),
          app_date: APP_DATE,
          amount_vnd: b.params.amount_vnd,
          summary: `Đã chuyển ${vnd(b.params.amount_vnd)} từ ${from.name} sang ${to.name}`,
          from_jar: { code: from.code, name: from.name, balance_after_vnd: from.balance_vnd },
          to_jar: { code: to.code, name: to.name, balance_after_vnd: to.balance_vnd },
        },
      })
    }
    if (req.method === 'POST' && url === '/demo/reset') {
      jars = seed()
      tokens.clear()
      applied.clear()
      return json(res, 200, { reset_at: nowIso(), app_date: APP_DATE, clock_offset_days: 0, jars_count: jars.length, transactions_count: 0 })
    }
    return err(res, 404, 'PARAMS_INVALID', 'Không có đường dẫn này.')
  })()
}

export function mockPlugin(): Plugin {
  return {
    name: 'yofina-dev-mock',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = req.url ?? ''
        if (url.startsWith('/mock-api/')) return void rest(req, res, url.slice('/mock-api'.length).split('?')[0]!).catch(() => err(res, 500, 'INTERNAL_ERROR', 'Lỗi giả.'))
        if (url.startsWith('/mock-agent/invocations')) return void agent(req, res).catch(() => res.end())
        next()
      })
    },
  }
}
