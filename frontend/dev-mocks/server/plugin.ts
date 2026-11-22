// CHỈ cho `npm run dev:mock` (vite --mode mock): máy chủ giả để xem giao diện bằng mắt khi backend chưa sẵn sàng.
// Không nằm trong bundle production (vite.config.ts chỉ import file này khi mode === 'mock'; tsconfig.app không include).
// Dữ liệu mẫu lấy từ contracts/fixtures. Đây KHÔNG phải agent: câu trả lời chọn theo từ khóa chỉ để thử giao diện.
import { randomUUID } from 'node:crypto'
import type { IncomingMessage, ServerResponse } from 'node:http'
import type { Plugin } from 'vite'
import { APP_DATE, forecastBlockFor, handleWallet, jarsOf, paramsHash } from './wallet.ts'
import { MOCK_S3_PREFIX, handleIngest, receiveUpload } from './ingest.ts'

export const MOCK_ENV: Record<string, string> = {
  VITE_AWS_REGION: 'ap-southeast-1',
  VITE_COGNITO_USER_POOL_ID: 'mock_pool',
  VITE_COGNITO_CLIENT_ID: 'mockclient',
  VITE_API_URL: '/mock-api',
  VITE_AGENT_RUNTIME_URL: '/mock-agent/invocations',
  VITE_DEMO_EMAIL: 'demo@example.invalid',
}

type Jar = { code: string; name: string; color_key: string; icon_key: string; balance_vnd: number; split_percent: number }
const totalOf = (jars: Jar[]) => jars.reduce((s, j) => s + j.balance_vnd, 0)
const nowIso = () => new Date().toISOString().replace(/\.\d+Z$/, 'Z')
const vnd = (n: number) => `${n.toLocaleString('vi-VN')} ₫`
const source = (tool: string) => ({ tool, as_of: nowIso(), app_date: APP_DATE })
const emailOf = (req: IncomingMessage) => {
  const t = String(req.headers.authorization ?? '').replace(/^Bearer /, '')
  return t.startsWith('mock-access-token:') ? decodeURIComponent(t.slice('mock-access-token:'.length)) : 'demo@example.invalid'
}
const traceOf = (req: IncomingMessage) => (String(req.headers.traceparent ?? '').split('-')[1] ?? randomUUID().replace(/-/g, ''))

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

function jarsBlock(trace: string, jars: Jar[]) {
  return {
    v: 1,
    id: `jar_summary:${trace}`,
    type: 'jar_summary',
    trace_id: trace,
    fallback_text: `Số dư ${jars.length} hũ, tổng ${vnd(totalOf(jars))}.`,
    source: source('ledger___get_jar_balances'),
    data: { jars, jars_total_vnd: totalOf(jars) },
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

function findJar(jars: Jar[], text: string, fromIdx = 0): { jar: Jar; at: number } | null {
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
  const email = emailOf(req)
  const jars = jarsOf(email)
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
    const a = findJar(jars, last)
    const b = a ? findJar(jars, last, a.at + 1) : null
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
  if (q.includes('du bao') || q.includes('can') || q.includes('tru duoc')) {
    const fb = forecastBlockFor(email, trace, q)
    if (fb) {
      await tool('tc1', 'forecast___get_forecast')
      block(fb)
      await say('m1', 'Đây là dự báo 30 ngày của hũ bạn hỏi.')
      return end()
    }
  }
  await tool('tc1', 'ledger___get_jar_balances')
  block(jarsBlock(trace, jars))
  await say('m1', 'Đây là số dư các hũ của bạn.')
  return end()
}

function rest(req: IncomingMessage, res: ServerResponse, url: string, query: URLSearchParams) {
  return (async () => {
    if (!String(req.headers.authorization ?? '').startsWith('Bearer ')) return err(res, 401, 'UNAUTHENTICATED', 'Thiếu token.')
    const method = req.method ?? 'GET'
    const ctx = { method, path: url, query, body: method === 'POST' ? await body(req) : {}, email: emailOf(req), trace: traceOf(req) }
    const reply = url.startsWith('/ingest/') ? handleIngest(ctx) : handleWallet(ctx)
    if (reply) return json(res, reply.status, reply.body)
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
        if (url.startsWith('/mock-api/')) {
          const rest0 = url.slice('/mock-api'.length)
          const [p0, q0] = [rest0.split('?')[0]!, new URLSearchParams(rest0.split('?')[1] ?? '')]
          return void rest(req, res, p0, q0).catch(() => err(res, 500, 'INTERNAL_ERROR', 'Lỗi giả.'))
        }
        if (url.startsWith('/mock-agent/invocations')) return void agent(req, res).catch(() => res.end())
        // Thay S3 cho presigned POST của màn Nạp dữ liệu: bỏ thân multipart, chỉ đánh dấu job đã nhận tệp.
        if (url.startsWith(MOCK_S3_PREFIX) && req.method === 'POST') {
          req.resume()
          req.on('end', () => {
            const r = receiveUpload(url.slice(MOCK_S3_PREFIX.length).split('?')[0]!)
            res.writeHead(r.status, r.status === 204 ? {} : { 'content-type': 'application/xml' })
            res.end(r.status === 204 ? undefined : String(r.body))
          })
          return
        }
        next()
      })
    },
  }
}
